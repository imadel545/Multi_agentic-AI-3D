import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.telecom_studio_api import main
from core.services.asset_library import AssetLibraryService, build_asset_library_catalog


def test_asset_library_endpoints_expose_quarantine_truth(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "asset-library"
    raw = root / "raw" / "maj_des_blocs" / "3D" / "Pylone"
    raw.mkdir(parents=True)
    (raw / "Orange_Pylone_30m.dwg").write_bytes(b"AC1018tower")
    build_asset_library_catalog(root / "raw" / "maj_des_blocs", root / "index")
    monkeypatch.setattr(main, "asset_library_service", AssetLibraryService(root))
    client = TestClient(main.app)

    summary = client.get("/assets/library/summary")
    search = client.get(
        "/assets/library/search",
        params={"q": "pylone 30m", "claimed_dimension": "3d", "extension": "dwg"},
    )

    assert summary.status_code == 200
    assert summary.json()["status"] == "catalogued_quarantined"
    assert summary.json()["generation_eligible_count"] == 0
    assert search.status_code == 200
    assert search.json()["result_count"] == 1
    assert search.json()["results"][0]["qualification_status"] == "quarantined_unverified"
    assert search.json()["generation_eligible"] is False


def test_asset_library_probe_rejects_unknown_id(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "asset-library"
    raw = root / "raw" / "maj_des_blocs"
    raw.mkdir(parents=True)
    build_asset_library_catalog(raw, root / "index")
    monkeypatch.setattr(main, "asset_library_service", AssetLibraryService(root))

    response = TestClient(main.app).post("/assets/library/lib_missing/probe")

    assert response.status_code == 404
    assert "unknown library file_id" in response.json()["detail"]


def test_asset_library_probe_returns_422_for_non_utf8_json_output(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "asset-library"
    raw = root / "raw" / "maj_des_blocs" / "3D" / "Pylone"
    raw.mkdir(parents=True)
    (raw / "Pylône_30m.dwg").write_bytes(b"AC1018tower")
    build_asset_library_catalog(root / "raw" / "maj_des_blocs", root / "index")
    service = AssetLibraryService(root, dwgread_binary="dwgread")
    monkeypatch.setattr(main, "asset_library_service", service)
    file_id = service.search("pylone 30m")["results"][0]["file_id"]

    def unreadable_probe(command, **_kwargs):
        output = Path(command[command.index("-o") + 1])
        output.write_bytes(b'{"invalid":"\xe9"}')
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr("core.services.asset_library.subprocess.run", unreadable_probe)

    response = TestClient(main.app, raise_server_exceptions=False).post(
        f"/assets/library/{file_id}/probe"
    )

    assert response.status_code == 422
    assert "sortie JSON illisible" in response.json()["detail"]
    assert "UnicodeDecodeError" not in response.text
