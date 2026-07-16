import importlib.util
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

import core.document_pack.service as document_pack_service_module
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


def test_document_pack_does_not_invent_foundation_or_vendor_antenna(tmp_path: Path) -> None:
    service = DocumentPackService(tmp_path)
    summary = service.ingest_zip(
        _zip(
            {
                "APD/radio.txt": (
                    "Type pylône: pylône treillis\n"
                    "Hauteur pylône: 30m\n"
                    "Azimuts: 0, 120, 240\n"
                    "HBA: 24m, 24m, 24m\n"
                    "Bandes: NR3500 5G\n"
                )
            }
        )
    )

    mapping = ProjectDesignSpecMapper().map_to_requirements(service.get_spec(summary.pack_id))

    assert mapping.status == "mapped"
    assert mapping.requirements is not None
    assert mapping.requirements["tower_characteristics"]["foundation_type"] == "unknown"
    warning_codes = {warning["code"] for warning in mapping.requirements["warnings"]}
    assert "DOC_FOUNDATION_UNSPECIFIED_NO_GEOMETRY" in warning_codes
    assert "DOC_GENERIC_ANTENNA_FAMILY_USED" in warning_codes
    field_statuses = {
        item["project_field"]: item["status"] for item in mapping.mapping_loss_report["fields"]
    }
    assert field_statuses["foundation.foundation_type"] == "fallback"
    assert field_statuses["radio.antenna_model"] == "fallback"


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


def test_document_pack_unknown_radio_blocks_instead_of_defaulting_to_5g(
    tmp_path: Path,
) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "APD/radio.txt": (
                    "Type pylône: pylône treillis\n"
                    "Hauteur pylône: 30m\n"
                    "Azimuts: 0, 120, 240\n"
                    "HBA: 24m, 24m, 24m\n"
                )
            }
        )
    )
    mapping = ProjectDesignSpecMapper().map_to_requirements(service.get_spec(summary.pack_id))
    qa = service.get_qa_report(summary.pack_id)

    assert summary.can_generate_design is False
    assert mapping.status == "blocked"
    assert "radio.network_type" in mapping.blocking_fields
    assert mapping.network_type is None
    assert mapping.mapping_loss_report["blocking_losses"][0]["code"] == (
        "UNKNOWN_OR_MIXED_NETWORK_TYPE"
    )
    assert qa["ready_to_generate"] is False
    assert "requirements_mapping_representable" in qa["warnings"]


def test_document_pack_maps_explicit_microwave_radio_without_5g_default(
    tmp_path: Path,
) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "APD/microwave.txt": (
                    "Type pylône: pylône treillis\n"
                    "Hauteur pylône: 30m\n"
                    "Azimuts: 45, 225\n"
                    "HBA: 25m, 25m\n"
                    "Bandes: MW\n"
                )
            }
        )
    )
    mapping = ProjectDesignSpecMapper().map_to_requirements(service.get_spec(summary.pack_id))

    assert summary.can_generate_design is True
    assert mapping.status == "mapped"
    assert mapping.network_type == "MW"
    assert mapping.requirements is not None
    assert mapping.requirements["network_type"] == "MW"
    assert mapping.requirements["antenna_type"] == "microwave_dish"


def test_document_pack_blocks_non_uniform_sector_geometry_instead_of_flattening(
    tmp_path: Path,
) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "APD/radio.txt": (
                    "Type pylône: pylône treillis\n"
                    "Hauteur pylône: 30m\n"
                    "Azimuts: 0, 120, 240\n"
                    "HBA: 24m, 23m, 24m\n"
                    "Mechanical tilt: 2, 3, 4\n"
                    "RET: 1, 2, 3\n"
                    "Bandes: NR700 NR3500 5G\n"
                )
            }
        )
    )
    spec = service.get_spec(summary.pack_id)
    mapping = ProjectDesignSpecMapper().map_to_requirements(spec)

    assert [sector.hba_m.value for sector in spec.radio_sectors] == [24.0, 23.0, 24.0]
    assert [sector.mechanical_tilt_deg.value for sector in spec.radio_sectors] == [
        2.0,
        3.0,
        4.0,
    ]
    assert [sector.electrical_tilt_deg.value for sector in spec.radio_sectors] == [
        1.0,
        2.0,
        3.0,
    ]
    assert summary.can_generate_design is False
    assert mapping.status == "blocked"
    assert {
        "radio.hba_m",
        "radio.mechanical_tilt_deg",
        "radio.electrical_tilt_deg",
    }.issubset(mapping.blocking_fields)
    assert all(
        item["code"] == "NON_UNIFORM_SECTOR_VALUES"
        for item in mapping.mapping_loss_report["blocking_losses"]
    )


def test_document_pack_blocks_partial_sector_values_instead_of_repeating_first(
    tmp_path: Path,
) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "APD/radio.txt": (
                    "Type pylône: pylône treillis\n"
                    "Hauteur pylône: 30m\n"
                    "Azimuts: 0, 120, 240\n"
                    "HBA: 24m, 23m\n"
                    "Mechanical tilt: 2, 3\n"
                    "Bandes: NR3500 5G\n"
                )
            }
        )
    )
    spec = service.get_spec(summary.pack_id)
    mapping = ProjectDesignSpecMapper().map_to_requirements(spec)

    assert spec.radio_sectors[2].hba_m.status == "missing"
    assert spec.radio_sectors[2].mechanical_tilt_deg is None
    assert mapping.status == "blocked"
    blocker_codes = {
        item["field"]: item["code"] for item in mapping.mapping_loss_report["blocking_losses"]
    }
    assert blocker_codes["radio.hba_m"] == "PARTIAL_SECTOR_VALUES"
    assert blocker_codes["radio.mechanical_tilt_deg"] == "PARTIAL_SECTOR_VALUES"


def test_document_pack_rejects_archive_limits_before_processing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = DocumentPackService(tmp_path)
    monkeypatch.setattr(document_pack_service_module, "MAX_MEMBER_COUNT", 1)

    with pytest.raises(ValueError, match="file limit"):
        service.ingest_zip(_zip({"one.txt": "one", "two.txt": "two"}))

    assert not service.packs_dir.exists()


def test_document_pack_rejects_compressed_and_uncompressed_size_limits(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = DocumentPackService(tmp_path)
    archive = _zip({"radio.txt": "Bandes: 5G"})
    monkeypatch.setattr(document_pack_service_module, "MAX_PACK_SIZE_BYTES", len(archive) - 1)

    with pytest.raises(ValueError, match="compressed size limit"):
        service.ingest_zip(archive)

    monkeypatch.setattr(document_pack_service_module, "MAX_PACK_SIZE_BYTES", len(archive) + 1)
    monkeypatch.setattr(document_pack_service_module, "MAX_UNCOMPRESSED_SIZE_BYTES", 5)
    with pytest.raises(ValueError, match="uncompressed size limit"):
        service.ingest_zip(archive)

    assert not service.packs_dir.exists()


def test_document_pack_rejects_oversized_member(tmp_path: Path, monkeypatch) -> None:
    service = DocumentPackService(tmp_path)
    monkeypatch.setattr(document_pack_service_module, "MAX_MEMBER_SIZE_BYTES", 5)

    with pytest.raises(ValueError, match="member limit"):
        service.ingest_zip(_zip({"radio.txt": "Bandes: 5G"}))

    assert not service.packs_dir.exists()


def test_document_pack_rejects_invalid_zip_with_no_partial_pack(tmp_path: Path) -> None:
    service = DocumentPackService(tmp_path)

    with pytest.raises(ValueError, match="invalid ZIP archive"):
        service.ingest_zip(b"this is not a zip")

    assert not service.packs_dir.exists()


def test_document_pack_cleans_partial_pack_when_processing_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = DocumentPackService(tmp_path)

    def fail_after_partial_write(state):
        pack_dir = Path(state["pack_dir"])
        (pack_dir / "partial.json").write_text("{}", encoding="utf-8")
        raise RuntimeError("forced processing failure")

    monkeypatch.setattr(service.orchestrator, "run", fail_after_partial_write)

    with pytest.raises(RuntimeError, match="forced processing failure"):
        service.ingest_zip(_zip({"APD/radio.txt": "Bandes: 5G"}))

    assert service.packs_dir.exists()
    assert list(service.packs_dir.iterdir()) == []


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
