import importlib.util
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from core.document_pack import DocumentPackService, ProjectDesignSpecMapper


def test_document_pack_ingestion_classifies_extracts_and_maps(tmp_path: Path) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(_complete_pack_zip(), filename="soler_like_fixture.zip")
    spec = service.get_spec(summary.pack_id)
    documents = service.get_documents(summary.pack_id)

    assert summary.document_count == 6
    assert summary.can_generate_design is True
    assert summary.missing_blocking_count == 0
    assert any(doc["category"] == "antenna_plan" for doc in documents)
    assert any(doc["category"] == "lease_or_bail" and doc["priority"] == "low" for doc in documents)
    assert any(
        doc["category"] == "cad_dwg" and doc["cad_status"] == "unsupported" for doc in documents
    )
    assert any(doc["duplicate_of"] for doc in documents)
    assert spec.tower_spec["tower_height_m"].value == 30.0
    assert spec.tower_spec["tower_height_m"].sources[0].file.endswith("APD_plan_antennes.txt")
    assert spec.radio_sectors[0].azimuth_deg.value == 0.0
    assert spec.radio_sectors[1].azimuth_deg.value == 120.0
    assert spec.radio_sectors[2].hba_m.value == 24.0
    assert spec.provenance_map["radio.azimuths_deg"]
    assert spec.coordinate_info["conversion_status"].value == "missing_xy"

    mapping = ProjectDesignSpecMapper().map_to_requirements(spec)

    assert mapping.status == "mapped"
    assert mapping.requirements is not None
    assert mapping.requirements["tower_type"] == "lattice_tower"
    assert mapping.requirements["tower_height_m"] == 30.0
    assert mapping.requirements["azimuths_deg"] == [0.0, 120.0, 240.0]


def test_document_pack_exposes_processing_capabilities_and_memory_summary(
    tmp_path: Path,
) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(_complete_pack_zip(), filename="fixture.zip")
    processing = service.get_processing_report(summary.pack_id)
    memory = service.get_memory_summary(summary.pack_id)

    assert "pdf_text_extraction" in summary.tool_status
    assert processing["tool_status"]["dxf_parsing"] in {"available", "unavailable"}
    assert any(
        document["extension"] == "dwg"
        and document["extraction_status"] == "unsupported"
        and document["processing_warnings"]
        for document in processing["documents"]
    )
    assert any(
        document["extension"] == "jpg"
        and document["extraction_status"] == "unsupported"
        and document["processing_warnings"]
        for document in processing["documents"]
    )
    assert memory["type"] == "document_pack_memory_summary"
    assert memory["tower_type"] == "lattice_tower"
    assert memory["azimuths_deg"] == [0.0, 120.0, 240.0]
    assert summary.memory_summary_available is True


def test_document_pack_missing_blocking_field_blocks_mapping_without_hallucination(
    tmp_path: Path,
) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "APD_plan_antennes.txt": (
                    "Code site: IMD123\n"
                    "Type pylône: pylône treillis\n"
                    "Hauteur pylône: 30m\n"
                    "Azimuts: 0, 120, 240\n"
                )
            }
        )
    )
    spec = service.get_spec(summary.pack_id)
    mapping = ProjectDesignSpecMapper().map_to_requirements(spec)

    assert summary.can_generate_design is False
    assert any(field.field == "radio.hba_m" for field in spec.missing_fields)
    assert mapping.status == "blocked"
    assert "radio.hba_m" in mapping.blocking_fields


def test_coordinate_conversion_is_explicitly_unavailable_without_pyproj(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args, **kwargs):
        if name == "pyproj":
            return None
        return original_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "APD_coordonnees.txt": (
                    "Type pylône: pylône treillis\n"
                    "Hauteur pylône: 30m\n"
                    "Azimuts: 0, 120, 240\n"
                    "HBA: 24m, 24m, 24m\n"
                    "Projection: Lambert 93\n"
                    "X=652345.12\n"
                    "Y=6865123.45\n"
                )
            }
        )
    )
    spec = service.get_spec(summary.pack_id)

    assert spec.coordinate_info["conversion_available"].value is False
    assert spec.coordinate_info["conversion_status"].value == "unavailable_pyproj"
    assert spec.coordinate_info["conversion_status"].sources


def test_document_pack_detects_cross_document_conflict(tmp_path: Path) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "APD_plan_antennes.txt": (
                    "Type pylône: pylône treillis\n"
                    "Hauteur pylône: 30m\n"
                    "Azimuts: 0, 120, 240\n"
                    "HBA: 24m, 24m, 24m\n"
                ),
                "Plan_elevation.txt": "Hauteur pylône: 32m\n",
            }
        )
    )
    spec = service.get_spec(summary.pack_id)

    assert summary.can_generate_design is False
    conflict = next(field for field in spec.conflicts if field.field == "tower.tower_height_m")
    assert conflict.status == "conflict"
    assert sorted(conflict.values) == [30.0, 32.0]
    assert conflict.resolution == "needs_user_review"


def _complete_pack_zip() -> bytes:
    apd = (
        "Code site: IMD123\n"
        "Nom site: SOLER TEST\n"
        "Adresse: 12 rue du Pylone, 75000 Paris\n"
        "Commune: Paris\n"
        "Système: Lambert II étendu\n"
        "Altitude: 85m NGF\n"
        "Type pylône: pylône treillis\n"
        "Hauteur pylône: 30m\n"
        "Fondation: massif béton\n"
        "RAL 7035\n"
    )
    antenna_plan = (
        "Plan antennes\n"
        "Azimuts: 0°, 120°, 240°\n"
        "HBA: 24m, 24m, 24m\n"
        "Bandes: NR700 L800 L1800 L2100 L2600 NR3500 5G\n"
        "RRU Huawei\n"
        "Chemins de câbles prévus\n"
        "GPS et baie énergie\n"
    )
    return _zip(
        {
            "APD/APD_plan_antennes.txt": apd,
            "Plans/Plan_antennes.txt": antenna_plan,
            "Admin/Bail_administratif.txt": "Bail administratif sans valeur 3D critique.",
            "Photos/site_photo.jpg": b"\xff\xd8\xff\x00",
            "CAD/plan_antennes.dwg": b"DWG placeholder bytes",
            "Duplicates/APD_copy.txt": apd,
        }
    )


def _zip(files: dict[str, str | bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            archive.writestr(name, data)
    return buffer.getvalue()
