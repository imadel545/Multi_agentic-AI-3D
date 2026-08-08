import json
import subprocess
from pathlib import Path

import pytest

from core.services.asset_library import (
    AssetLibraryError,
    AssetLibraryService,
    build_asset_library_catalog,
)


def test_catalog_preserves_files_and_marks_duplicates_and_quarantine(tmp_path: Path) -> None:
    raw = tmp_path / "library" / "raw" / "maj_des_blocs"
    (raw / "3D" / "Pylone").mkdir(parents=True)
    (raw / "2D" / "Radio").mkdir(parents=True)
    (raw / "3D" / "Pylone" / "Tower_30m.dwg").write_bytes(b"AC1018payload")
    (raw / "2D" / "Radio" / "Tower_copy.dwg").write_bytes(b"AC1018payload")
    (raw / "3D" / "Pylone" / "preview.jpg").write_bytes(b"jpeg")

    summary = build_asset_library_catalog(raw, tmp_path / "library" / "index")

    assert summary["file_count"] == 3
    assert summary["unique_content_count"] == 2
    assert summary["duplicate_file_count"] == 1
    assert summary["generation_eligible_count"] == 0
    entries = [
        json.loads(line)
        for line in (tmp_path / "library" / "index" / "catalog.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert all(entry["qualification_status"] == "quarantined_unverified" for entry in entries)
    assert all(entry["generation_eligible"] is False for entry in entries)
    assert sum(entry["duplicate_of"] is not None for entry in entries) == 1
    assert all("reference_preview_file_ids" in entry for entry in entries)


def test_search_is_metadata_driven_and_never_claims_generation_ready(tmp_path: Path) -> None:
    root = tmp_path / "library"
    raw = root / "raw" / "maj_des_blocs" / "3D" / "Pylone"
    raw.mkdir(parents=True)
    (raw / "Orange_Pylone_Treillis_30m.dwg").write_bytes(b"AC1018tower")
    build_asset_library_catalog(root / "raw" / "maj_des_blocs", root / "index")
    service = AssetLibraryService(root)

    result = service.search("pylone treillis 30m", claimed_dimension="3d")

    assert result["result_count"] == 1
    assert result["results"][0]["category"] == "Pylone"
    assert result["results"][0]["license_status"] == "unknown_requires_review"
    assert result["generation_eligible"] is False
    assert result["selection_policy"] == "metadata_retrieval_only"


def test_probe_rejects_non_dwg_without_inventing_geometry(tmp_path: Path) -> None:
    root = tmp_path / "library"
    raw = root / "raw" / "maj_des_blocs" / "3D" / "Pylone"
    raw.mkdir(parents=True)
    (raw / "tower.jpg").write_bytes(b"jpeg")
    build_asset_library_catalog(root / "raw" / "maj_des_blocs", root / "index")
    service = AssetLibraryService(root, dwgread_binary="dwgread")
    file_id = service.search("tower")["results"][0]["file_id"]

    with pytest.raises(AssetLibraryError, match="limité aux fichiers DWG"):
        service.probe(file_id)


def test_probe_handles_non_utf8_tool_diagnostic_without_leaking_decode_error(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "library"
    raw = root / "raw" / "maj_des_blocs" / "3D" / "Pylone"
    raw.mkdir(parents=True)
    (raw / "Pylône_30m.dwg").write_bytes(b"AC1018tower")
    build_asset_library_catalog(root / "raw" / "maj_des_blocs", root / "index")
    service = AssetLibraryService(root, dwgread_binary="dwgread")
    file_id = service.search("pylone 30m")["results"][0]["file_id"]

    def failed_probe(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["dwgread"], returncode=1, stdout=b"", stderr=b"\xe9chec\xff"
        )

    monkeypatch.setattr("core.services.asset_library.subprocess.run", failed_probe)

    with pytest.raises(AssetLibraryError, match="reste en quarantaine") as captured:
        service.probe(file_id)

    assert "UnicodeDecodeError" not in str(captured.value)


def test_probe_accepts_real_dwgread_latin1_and_non_finite_json_dialect(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "library"
    raw = root / "raw" / "maj_des_blocs" / "3D" / "Pylone"
    raw.mkdir(parents=True)
    (raw / "Pylône_36m.dwg").write_bytes(b"AC1032tower")
    build_asset_library_catalog(root / "raw" / "maj_des_blocs", root / "index")
    service = AssetLibraryService(root, dwgread_binary="dwgread")
    file_id = service.search("pylone 36m")["results"][0]["file_id"]

    def completed_probe(args, **_kwargs):
        output_path = Path(args[args.index("-o") + 1])
        output_path.write_bytes(
            (
                '{"FILEHEADER":{"version":"AC1032"},'
                '"HEADER":{"INSUNITS":4,"unit1_name":"m"},'
                '"objects":[{"entity":"3DSOLID","name":"Pyl\xf4ne",'
                '"align_angles":[nan,nan],"note":"nan,Infinity"}]}'
            ).encode("latin-1")
        )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("core.services.asset_library.subprocess.run", completed_probe)

    result = service.probe(file_id)

    assert result["probe_status"] == "completed"
    assert result["dwg_version"] == "AC1032"
    assert result["declared_unit"] == "millimeters"
    assert result["unit_scale_to_meters"] == 0.001
    assert result["insunits_code"] == 4
    assert result["display_unit_name"] == "m"
    assert result["unit_metadata_conflict"] is True
    assert result["entity_counts"] == {"3DSOLID": 1}
    assert result["contains_acis_3d_solids"] is True
    assert result["conversion_route"] == "requires_acis_brep_bridge"
    assert result["parser_mode"] == "latin1_non_finite_normalized"
    assert result["sanitized_non_finite_values"] == 2


def test_probe_maps_timeout_to_controlled_quarantine_error(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "library"
    raw = root / "raw" / "maj_des_blocs" / "3D" / "Pylone"
    raw.mkdir(parents=True)
    (raw / "Tower_30m.dwg").write_bytes(b"AC1018tower")
    build_asset_library_catalog(root / "raw" / "maj_des_blocs", root / "index")
    service = AssetLibraryService(root, dwgread_binary="dwgread")
    file_id = service.search("tower 30m")["results"][0]["file_id"]

    def timed_out(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="dwgread", timeout=60)

    monkeypatch.setattr("core.services.asset_library.subprocess.run", timed_out)

    with pytest.raises(AssetLibraryError, match="dépassé le délai autorisé"):
        service.probe(file_id)


def test_catalog_links_nearby_numbered_reference_previews_to_longest_cad_stem(
    tmp_path: Path,
) -> None:
    root = tmp_path / "library"
    raw = root / "raw" / "maj_des_blocs" / "3D" / "Pylone"
    raw.mkdir(parents=True)
    (raw / "Orange_Pylone_30m.dwg").write_bytes(b"AC1018base")
    (raw / "Orange_Pylone_30m_Galva.dwg").write_bytes(b"AC1018galva")
    (raw / "Orange_Pylone_30m_Galva1.JPG").write_bytes(b"preview-one")
    (raw / "Orange_Pylone_30m_Galva2.JPG").write_bytes(b"preview-two")
    (raw / "unrelated.JPG").write_bytes(b"unrelated")

    summary = build_asset_library_catalog(root / "raw" / "maj_des_blocs", root / "index")
    service = AssetLibraryService(root)
    galva = service.search("orange pylone 30m galva", extension="dwg")["results"][0]

    assert summary["cad_with_reference_preview_count"] == 1
    assert summary["reference_preview_link_count"] == 2
    assert len(galva["reference_preview_file_ids"]) == 2
