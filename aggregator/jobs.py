"""Durable synchronous import journal (jobs table) — not a queue daemon.

- ``run()``: a fresh job is persisted as ``running`` (owned by the current pid)
  in one transaction, then executed synchronously. A crash between persist and
  commit leaves a ``running`` job owned by a dead pid.
- ``recover()``: startup-only. Claims ``pending``/``running`` jobs whose owner
  pid is dead (CAS UPDATE under the caller's BEGIN IMMEDIATE transaction) and
  re-executes them. Same-process live jobs are never stolen. Per-job failures
  are recorded and do not crash startup.
- ``finish()``: called by Storage *inside* its shipment commit transaction, so
  job completion is atomic with the shipment. ``retry_count = attempts - 1``.
- Failed jobs never auto-loop; an explicit ``run(job_id=<failed>)`` re-claims
  them. Exceptions persist only the exception TYPE (no secrets) and re-raise.
"""

import datetime
import json
import logging
import os
import uuid

logger = logging.getLogger(__name__)


class JobJournal:
    def __init__(self, connection, runner):
        self.connection = connection
        self.runner = runner
        self._create_table()

    def _create_table(self):
        with self.connection(write=True) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    file_id TEXT,
                    payload TEXT,
                    state TEXT CHECK(state IN ('pending','running','completed','failed')),
                    owner_pid INTEGER,
                    attempts INTEGER DEFAULT 0,
                    result TEXT,
                    error TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated_at)"
            )

    def _now(self):
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    def _is_owner_alive(self, pid):
        if pid is None:
            return False
        if pid == os.getpid():
            return True
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # process exists but no signal permission
        except OSError:
            return False

    def run(self, file_id, profile, saved=None, reprocess=False, job_id=None):
        if job_id is not None:
            return self._claim_and_execute(job_id)
        job_id = str(uuid.uuid4())
        payload = json.dumps(
            {
                "file_id": file_id,
                "profile": profile,
                "saved": saved,
                "reprocess": reprocess,
            },
            ensure_ascii=False,
            allow_nan=False,
        )
        now = self._now()
        with self.connection(write=True) as conn:
            conn.execute(
                "INSERT INTO jobs(id,file_id,payload,state,owner_pid,attempts,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (job_id, file_id, payload, "running", os.getpid(), 1, now, now),
            )
        return self._execute(job_id, file_id, payload)

    def _claim_and_execute(self, job_id):
        claimed = False
        with self.connection(write=True) as conn:
            row = conn.execute(
                "SELECT state, owner_pid, result FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if row is None:
                return None
            if row["state"] == "completed":
                return json.loads(row["result"]) if row["result"] else None
            if row["state"] == "running" and self._is_owner_alive(row["owner_pid"]):
                return None  # live owner still working; never steal
            owner_clause = (
                "owner_pid=?" if row["owner_pid"] is not None else "owner_pid IS NULL"
            )
            params = [os.getpid(), self._now(), job_id, row["state"]]
            if row["owner_pid"] is not None:
                params.append(row["owner_pid"])
            cur = conn.execute(
                f"UPDATE jobs SET state='running', owner_pid=?, attempts=attempts+1, updated_at=?"
                f" WHERE id=? AND state=? AND {owner_clause}",
                params,
            )
            claimed = cur.rowcount == 1
        if not claimed:
            # lost the race: surface the completed result if one exists
            with self.connection(write=False) as conn:
                row = conn.execute(
                    "SELECT state, result FROM jobs WHERE id=?", (job_id,)
                ).fetchone()
            if row and row["state"] == "completed" and row["result"]:
                return json.loads(row["result"])
            return None
        file_id, payload = self._payload(job_id)
        return self._execute(job_id, file_id, payload)

    def _payload(self, job_id):
        with self.connection(write=False) as conn:
            row = conn.execute(
                "SELECT file_id, payload FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
        return row["file_id"], row["payload"]

    def _execute(self, job_id, file_id, payload_json):
        payload = json.loads(payload_json)
        try:
            return self.runner(
                file_id,
                payload.get("profile"),
                payload.get("saved"),
                payload.get("reprocess", False),
                job_id=job_id,
            )
        except Exception as exc:
            with self.connection(write=True) as conn:
                conn.execute(
                    "UPDATE jobs SET state='failed', error=?, updated_at=? WHERE id=? AND state!='completed'",
                    (type(exc).__name__, self._now(), job_id),
                )
            logger.error("Job %s failed: %s", job_id, type(exc).__name__)
            raise

    def finish(self, conn, job_id, result):
        """Called by Storage inside its shipment commit transaction."""
        row = conn.execute("SELECT attempts FROM jobs WHERE id=?", (job_id,)).fetchone()
        attempts = row["attempts"] if row else 0
        enriched = dict(result) if isinstance(result, dict) else {}
        enriched["job_id"] = job_id
        enriched["retry_count"] = max(0, attempts - 1)
        conn.execute(
            "UPDATE jobs SET state='completed', result=?, updated_at=? WHERE id=?",
            (
                json.dumps(enriched, ensure_ascii=False, allow_nan=False),
                self._now(),
                job_id,
            ),
        )
        return enriched

    def recover(self):
        """Startup-only recovery: drain jobs whose owners are dead."""
        with self.connection(write=False) as conn:
            rows = conn.execute(
                "SELECT id, owner_pid FROM jobs WHERE state IN ('pending','running')"
            ).fetchall()
        for row in rows:
            job_id, owner_pid = row["id"], row["owner_pid"]
            if self._is_owner_alive(owner_pid):
                continue
            claimed = False
            with self.connection(write=True) as conn:
                owner_clause = (
                    "owner_pid=?" if owner_pid is not None else "owner_pid IS NULL"
                )
                params = [os.getpid(), self._now(), job_id]
                if owner_pid is not None:
                    params.append(owner_pid)
                cur = conn.execute(
                    f"UPDATE jobs SET state='running', owner_pid=?, attempts=attempts+1, updated_at=?"
                    f" WHERE id=? AND state IN ('pending','running') AND {owner_clause}",
                    params,
                )
                claimed = cur.rowcount == 1
            if not claimed:
                continue
            file_id, payload = self._payload(job_id)
            data = json.loads(payload)
            try:
                self.runner(
                    file_id,
                    data.get("profile"),
                    data.get("saved"),
                    data.get("reprocess", False),
                    job_id=job_id,
                )
            except Exception as exc:
                with self.connection(write=True) as conn:
                    conn.execute(
                        "UPDATE jobs SET state='failed', error=?, updated_at=? WHERE id=?",
                        (type(exc).__name__, self._now(), job_id),
                    )
                logger.error("Recovery job %s failed: %s", job_id, type(exc).__name__)

    def list(self, limit=100):
        with self.connection(write=False) as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        out = []
        for row in rows:
            record = dict(row)
            for field in ("payload", "result"):
                if record.get(field):
                    try:
                        record[field] = json.loads(record[field])
                    except (TypeError, ValueError):
                        pass
            out.append(record)
        return out
