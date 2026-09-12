"""Crash-recovery semantics of the durable import journal (jobs table)."""

import json
import os
from datetime import datetime, timezone

from aggregator.storage import Storage
from test_engine import profile
from test_storage import make_file


def _upload_uncommitted(store, tmp_path):
    path = make_file(tmp_path, "crash", [["X1", "Товар", 5]])
    p = profile(path, ["article", "name", "price"], source="S")
    p["ingest_mode"] = "replace_all"
    file_id = store.upload_files([(path.name, path.read_bytes())], "S")[0]["file_id"]
    return file_id, p


def _insert_running_job(store, job_id, file_id, p, owner_pid):
    payload = json.dumps(
        {"file_id": file_id, "profile": p, "saved": None, "reprocess": False},
        ensure_ascii=False,
    )
    now = datetime.now(timezone.utc).isoformat()
    with store.connection(write=True) as conn:
        conn.execute(
            "INSERT INTO jobs(id,file_id,payload,state,owner_pid,attempts,result,error,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (job_id, file_id, payload, "running", owner_pid, 1, None, None, now, now),
        )


def _insert_failed_job(store, job_id, file_id, p):
    payload = json.dumps(
        {"file_id": file_id, "profile": p, "saved": None, "reprocess": False},
        ensure_ascii=False,
    )
    now = datetime.now(timezone.utc).isoformat()
    with store.connection(write=True) as conn:
        conn.execute(
            "INSERT INTO jobs(id,file_id,payload,state,owner_pid,attempts,result,error,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (job_id, file_id, payload, "failed", None, 1, None, "ValueError", now, now),
        )


def test_journal_dead_owner_recovered_exactly_once(tmp_path):
    store = Storage(tmp_path / "data")
    file_id, p = _upload_uncommitted(store, tmp_path)
    # Simulates a process killed mid-import: job left running under a dead pid.
    _insert_running_job(store, "job-dead", file_id, p, owner_pid=999999)
    revived = Storage(tmp_path / "data")  # startup recovery drains the job
    assert revived.get_catalog()["total"] == 1
    jobs = revived.jobs.list()
    assert [job["state"] for job in jobs] == ["completed"]
    assert jobs[0]["result"]["status"] == "accepted"
    assert jobs[0]["result"]["counts"]["items"] == 1
    assert jobs[0]["result"]["retry_count"] == 1
    # Second startup and explicit retry of the same job do not duplicate.
    again = Storage(tmp_path / "data")
    assert again.get_catalog()["total"] == 1
    assert len(again.jobs.list()) == 1
    retried = revived.jobs.run(file_id, p, job_id="job-dead")
    assert retried["shipment_id"] == jobs[0]["result"]["shipment_id"]
    assert revived.get_catalog()["total"] == 1


def test_journal_live_owner_not_stolen(tmp_path):
    store = Storage(tmp_path / "data")
    file_id, p = _upload_uncommitted(store, tmp_path)
    _insert_running_job(store, "job-live", file_id, p, owner_pid=os.getpid())
    second = Storage(tmp_path / "data")  # same process: owner is alive
    job = second.jobs.list()[0]
    assert job["state"] == "running"
    assert job["owner_pid"] == os.getpid()
    assert second.get_catalog()["total"] == 0


def test_journal_failed_job_reclaimed_by_explicit_retry(tmp_path):
    store = Storage(tmp_path / "data")
    file_id, p = _upload_uncommitted(store, tmp_path)
    # A crashed attempt left a failed job whose persisted intent is valid.
    _insert_failed_job(store, "job-failed", file_id, p)
    assert store.get_catalog()["total"] == 0
    # Explicit retry re-claims the same job and completes it from the stored payload.
    result = store.jobs.run(file_id, p, job_id="job-failed")
    assert result["counts"]["items"] == 1
    jobs = store.jobs.list()
    assert jobs[0]["state"] == "completed"
    assert jobs[0]["attempts"] == 2
    assert jobs[0]["result"]["retry_count"] == 1
    assert store.get_catalog()["total"] == 1
    # Retrying a completed job returns the stored result without new work.
    again = store.jobs.run(file_id, p, job_id="job-failed")
    assert again["shipment_id"] == result["shipment_id"]
    assert store.get_catalog()["total"] == 1
    assert len(store.jobs.list()) == 1


def test_journal_normal_approve_records_completed_job(tmp_path):
    store = Storage(tmp_path / "data")
    file_id, p = _upload_uncommitted(store, tmp_path)
    result = store.approve_file(file_id, p)
    assert result["status"] == "accepted"
    jobs = store.jobs.list()
    assert len(jobs) == 1
    assert jobs[0]["state"] == "completed"
    assert jobs[0]["result"]["retry_count"] == 0
    assert jobs[0]["result"]["shipment_id"] == result["shipment_id"]
    assert jobs[0]["id"] == result["job_id"]
