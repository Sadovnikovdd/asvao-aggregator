from concurrent.futures import ThreadPoolExecutor

import openpyxl
import pytest

from aggregator.storage import Storage
from test_engine import profile


def make_file(tmp_path, name, rows, operation=False):
    path = tmp_path / (name + ".xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Артикул", "Наименование", "Цена"] + (["Операция"] if operation else []))
    for row in rows:
        ws.append(row)
    wb.save(path)
    wb.close()
    return path


def ingest(store, path, mode="replace_all", source="S", operation=False):
    p = profile(
        path,
        ["article", "name", "price"] + (["extra.operation"] if operation else []),
        source=source,
    )
    p["ingest_mode"] = mode
    if operation:
        p["delta"] = {"key_fields": ["article"], "operation_field": "extra.operation"}
    file_id = store.upload_files([(path.name, path.read_bytes())], source)[0]["file_id"]
    return store.approve_file(file_id, p), p


def test_append_reprocess_historical_base_no_duplicate_or_activation(tmp_path):
    store = Storage(tmp_path / "data")
    a = make_file(tmp_path, "a", [["A", "Первый", 10]])
    first, _ = ingest(store, a)
    # A different layout isolates the explicitly selected append profile.
    b = make_file(tmp_path, "b", [["B", "Второй", 20]], operation=False)
    p = profile(b, ["article", "name", "price"], source="S")
    p["ingest_mode"] = "append"
    # Upload before profiles exist would review; here use source scope staging to avoid automatic full import.
    bid = store.upload_files([(b.name, b.read_bytes())], "staging")[0]["file_id"]
    second = store.approve_file(bid, p)
    assert store.get_catalog()["total"] == 2
    regenerated = store.reprocess_file(bid, second["profile_id"])
    assert regenerated["counts"]["items"] == 2
    assert regenerated["generation"] == 3
    current = store.get_state()["sources"]
    assert (
        next(s for s in current if s["name"] == "S")["current_shipment_id"]
        == second["shipment_id"]
    )
    store.activate_shipment(first["shipment_id"], "test rollback")
    assert store.get_catalog()["total"] == 1
    assert store.upload_files([(b.name, b.read_bytes())], "S")[0]["status"] == "replay"
    assert store.get_catalog()["total"] == 1


def test_delta_real_patch_and_reprocess(tmp_path):
    store = Storage(tmp_path / "data")
    a = make_file(tmp_path, "a", [["A", "Первый", 10], ["B", "Второй", 20]])
    ingest(store, a)
    patch = make_file(
        tmp_path,
        "patch",
        [
            ["A", "Изменён", 15, "upsert"],
            ["B", "Удалён", None, "delete"],
            ["C", "Новый", 30, "upsert"],
        ],
        operation=True,
    )
    saved, _ = ingest(store, patch, mode="delta", operation=True)
    assert {i["article"]: i["price"] for i in store.get_catalog()["items"]} == {
        "A": "15",
        "C": "30",
    }
    rerun = store.reprocess_file(saved["file_id"], saved["profile_id"])
    assert rerun["counts"]["items"] == 2
    assert store.get_catalog()["total"] == 2


def test_ambiguous_delta_does_not_change_current_or_profiles(tmp_path):
    store = Storage(tmp_path / "data")
    a = make_file(tmp_path, "a", [["A", "Первый", 10], ["A", "Другая фасовка", 20]])
    ingest(store, a)
    patch = make_file(
        tmp_path, "patch", [["A", "Changed", 15, "upsert"]], operation=True
    )
    before = store.get_catalog()
    with pytest.raises(ValueError, match="delta_ambiguous_existing_key"):
        ingest(store, patch, mode="delta", operation=True)
    assert store.get_catalog() == before
    assert len(store.list_profiles()) == 1


def test_concurrent_commit_same_file_single_shipment(tmp_path):
    first = Storage(tmp_path / "data")
    second = Storage(tmp_path / "data")
    path = make_file(tmp_path, "a", [["A", "Первый", 10]])
    fid = first.upload_files([(path.name, path.read_bytes())], "S")[0]["file_id"]
    p = profile(path, ["article", "name", "price"], source="S")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda store: store.approve_file(fid, p), [first, second])
        )
    assert sorted(r["status"] for r in results) == ["accepted", "replay"]
    assert len(first.list_shipments()) == 1
    assert first.get_catalog()["total"] == 1
    assert len(first.list_profiles()) == 1


def test_explicit_profile_revision_preserves_old_snapshot(tmp_path):
    store = Storage(tmp_path / "data")
    path = make_file(tmp_path, "revision", [["0001", "Первый", 10]])
    first, p = ingest(store, path)
    p["id"] = first["profile_id"]
    p["name"] = "Исправленная валюта"
    p["tables"][0]["columns"][2]["currency"] = "USD"
    second = store.approve_file(first["file_id"], p)
    assert second["profile_id"] == first["profile_id"]
    assert second["profile_revision"] == 2
    assert second["shipment_id"] != first["shipment_id"]
    assert store.get_shipment(first["shipment_id"])["items"][0]["currency"] == "RUB"
    assert store.get_shipment(second["shipment_id"])["items"][0]["currency"] == "USD"
    assert (
        store.get_profile(first["profile_id"], 1)["body"]["tables"][0]["columns"][2][
            "currency"
        ]
        == "RUB"
    )
    assert len(store.list_profiles(history=True)) == 2
    before = store.get_catalog()
    store.upload_files([(path.name, path.read_bytes())], "S")
    assert store.get_catalog() == before
