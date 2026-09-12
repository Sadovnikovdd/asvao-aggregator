import copy
import io
import zipfile

import openpyxl
import pytest
from fastapi.testclient import TestClient

from aggregator.app import create_app
from test_engine import ROOT, asvao_profile, fixture, profile

requires_real_prices = pytest.mark.skipif(
    not (ROOT / "ASVAO.xlsx").exists() or not (ROOT / "ASVAO3.xlsx").exists(),
    reason="реальные прайсы поставщиков не входят в репозиторий",
)


def upload(client, path, source="test", name=None):
    response = client.post(
        "/api/upload",
        files={"files": (name or path.name, path.read_bytes())},
        data={"source": source},
    )
    assert response.status_code == 200, response.text
    return response.json()["results"][0]


def approve(client, file_id, p):
    preview = client.post(f"/api/files/{file_id}/preview", json=p)
    assert preview.status_code == 200 and preview.json()["valid"], preview.text
    result = client.post(f"/api/files/{file_id}/approve", json=p)
    assert result.status_code == 200 and result.json()["status"] == "accepted", (
        result.text
    )
    return result.json()


@requires_real_prices
def test_G1_G4_full_upload_and_replay(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        first = upload(client, ROOT / "ASVAO.xlsx", "ASVAO")
        assert first["status"] == "review"
        assert client.get("/api/catalog").json()["total"] == 0
        before = client.get("/api/state").json()
        preview = client.post(
            f"/api/files/{first['file_id']}/preview", json=asvao_profile()
        ).json()
        assert preview["counts"]["items"] == 100
        assert client.get("/api/state").json() == before
        saved = approve(client, first["file_id"], asvao_profile())
        assert saved["counts"]["items"] == 7874
        assert (
            client.get("/api/catalog", params={"q": "06503163"}).json()["items"][0][
                "article"
            ]
            == "06503163"
        )
        assert upload(client, ROOT / "ASVAO.xlsx", "ASVAO")["status"] == "replay"
        assert len(client.get("/api/state").json()["shipments"]) == 1
        other = upload(client, ROOT / "ASVAO3.xlsx", "ASVAO")
        assert other["status"] == "review"
        wrong = client.post(
            f"/api/files/{other['file_id']}/preview", json=asvao_profile()
        ).json()
        assert not wrong["valid"]
        p = profile(
            ROOT / "ASVAO3.xlsx",
            ["article", "name", "qty", "extra.size", "price", "extra.sum"],
            header=4,
            header_end=6,
            start=8,
            first_col=2,
            source="ASVAO3",
        )
        assert approve(client, other["file_id"], p)["counts"]["items"] == 36
        assert client.get("/api/catalog").json()["total"] == 7910


def test_V1_to_V5_zero_click_versions_and_rollback(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        v1, v2 = fixture("V01_"), fixture("V02_")
        p = profile(v1, ["article", "name", "brand", "qty", "price"], source="supplier")
        first = approve(client, upload(client, v1, "supplier")["file_id"], p)
        assert first["counts"]["items"] == 12
        second = upload(client, v2, "supplier")
        assert second["status"] == "accepted", second
        assert second["counts"]["items"] == 13
        assert second["profile_revision"] == first["profile_revision"] == 1
        assert client.get("/api/catalog").json()["total"] == 13
        assert (
            client.get(f"/api/shipments/{first['shipment_id']}").json()["total_items"]
            == 12
        )
        response = client.post(
            f"/api/shipments/{first['shipment_id']}/activate",
            json={"reason": "Проверка rollback"},
        )
        assert response.status_code == 200, response.text
        assert client.get("/api/catalog").json()["total"] == 12
        assert upload(client, v2, "supplier")["status"] == "replay"
        assert client.get("/api/catalog").json()["total"] == 12
        assert (
            client.get(f"/api/files/{second['file_id']}/raw").content == v2.read_bytes()
        )


def test_G3_unseen_layout_and_G8_atomic_profile(tmp_path):
    path = tmp_path / "unseen.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "New supplier"
    for _ in range(7):
        ws.append([])
    ws.append(["Vendor token", "Label X", "Amount alpha", "Amount beta"])
    ws.append(["00012", "Товар", 12, 15])
    ws.append(["00013", "Другой", 20, 25])
    wb.save(path)
    p = profile(
        path, ["article", "name", "price", "price"], header=8, start=9, source="unseen"
    )
    with TestClient(
        create_app(tmp_path / "data"), base_url="http://127.0.0.1"
    ) as client:
        new = upload(client, path, "unseen")
        assert new["status"] == "review"
        wrong = copy.deepcopy(p)
        wrong["tables"][0]["columns"][0]["quote"]["literal"] = "Wrong"
        response = client.post(f"/api/files/{new['file_id']}/approve", json=wrong)
        assert response.status_code == 400
        assert client.get("/api/state").json()["profiles"] == []
        saved = approve(client, new["file_id"], p)
        assert saved["counts"]["items"] == 4
        assert {i["article"] for i in client.get("/api/catalog").json()["items"]} == {
            "00012",
            "00013",
        }
        ws.cell(9, 3).value = 13
        wb.save(path)
        wb.close()
        subsequent = upload(client, path, "unseen")
        assert subsequent["status"] == "accepted"
        assert subsequent["counts"]["items"] == 4


def test_V6_partial_upload_never_auto_replaces_catalog(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        v1, v2, v8 = fixture("V01_"), fixture("V02_"), fixture("V08_")
        p = profile(v1, ["article", "name", "brand", "qty", "price"], source="F_EX")
        first = approve(client, upload(client, v1, "F_EX")["file_id"], p)
        assert first["counts"]["items"] == 12
        second = upload(client, v2, "F_EX")
        assert second["status"] == "accepted"
        assert second["counts"]["items"] == 13
        partial = upload(client, v8, "F_EX")
        assert partial["status"] == "review"
        assert "shrink" in partial["reason"]
        assert client.get("/api/catalog").json()["total"] == 13
        # The operator's explicit decision still controls the outcome.
        explicit = approve(client, partial["file_id"], p)
        assert explicit["counts"]["items"] == 4


def test_G2_24_ambiguous_profiles_require_explicit_selection(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        v1, v2, v8 = fixture("V01_"), fixture("V02_"), fixture("V08_")
        p = profile(v1, ["article", "name", "brand", "qty", "price"], source="F_EX")
        # Upload both before any profile exists, then approve each explicitly:
        # two saved profiles with the same fingerprint for the same source.
        assert upload(client, v1, "F_EX")["status"] == "review"
        assert upload(client, v2, "F_EX")["status"] == "review"
        files = client.get("/api/state").json()["files"]
        by_name = {f["original_name"]: f["id"] for f in files}
        approve(client, by_name["V01_FEX_полный_v1.xlsx"], p)
        approve(client, by_name["V02_FEX_полный_v2.xlsx"], dict(p))
        ambiguous = upload(client, v8, "F_EX")
        assert ambiguous["status"] == "review"
        assert ambiguous["reason"] == "ambiguous_profile"
        assert client.get("/api/catalog").json()["total"] == 13


def test_G2_24_V15_ambiguous_short_headers_require_wizard(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        uploaded = upload(client, fixture("V15_"), "V15")
        assert uploaded["status"] == "review"
        assert uploaded["reason"] == "unknown_layout"
        assert client.get("/api/catalog").json()["total"] == 0


def test_G2_20_file_quarantine_cannot_empty_catalog(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        path = fixture("V14_")
        fid = upload(client, path)["file_id"]
        p = profile(path, ["article", "name", "price"])
        result = client.post(f"/api/files/{fid}/approve", json=p)
        assert result.status_code == 400
        state = client.get("/api/state").json()
        assert state["profiles"] == [] and state["shipments"] == []
        assert state["files"][0]["status"] == "quarantine"


def test_G5_zip_cyrillic_extensionless_and_host_guard(tmp_path):
    path = fixture("V01_")
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("каталог/прайс.xlsx", path.read_bytes())
        archive.writestr("описание.pdf", b"%PDF-1.7\nnot pricelist")
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/upload", files={"files": ("архив.zip", bundle.getvalue())}
        )
        assert response.status_code == 200, response.text
        assert [r["status"] for r in response.json()["results"]] == [
            "review",
            "quarantine",
        ]
        direct = upload(client, fixture("V02_"), name="без_расширения")
        assert direct["status"] == "review"
        response = client.post(
            "/api/upload",
            files={"files": ("x.xlsx", path.read_bytes())},
            headers={"Origin": "https://evil.example"},
        )
        assert response.status_code == 403
        response = client.post(
            "/api/upload",
            files={"files": ("x.xlsx", path.read_bytes())},
            headers={"Origin": "null"},
        )
        assert response.status_code == 403
