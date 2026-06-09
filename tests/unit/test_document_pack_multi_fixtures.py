from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from core.contracts.document_pack import DocumentPackCorrection
from core.document_pack import DocumentPackService, ProjectDesignSpecMapper


@pytest.mark.parametrize(
    ("pack_name", "files", "expected_tower_type", "expected_height"),
    [
        (
            "pack_text_apd_complete",
            {
                "notes/APD_inconnu.txt": (
                    "Support: pylône treillis\n"
                    "Hauteur totale: 30m\n"
                    "Secteurs radio\n"
                    "Azimuts: 0, 120, 240\n"
                    "HBA: 24m, 24m, 24m\n"
                    "Bandes: NR700 NR3500 5G\n"
                    "RRU et chemin de câble\n"
                )
            },
            "lattice_tower",
            30.0,
        ),
        (
            "pack_rooftop_site",
            {
                "clientA/fiche_radio.txt": (
                    "Support: mât rooftop en toiture\n"
                    "Hauteur totale: 12m\n"
                    "Fondation: ancrage toiture\n"
                    "S1 azimuth=30 HBA=10\n"
                    "S2 azimuth=210 HBA=10\n"
                    "Bandes: L800 L1800 4G\n"
                )
            },
            "rooftop_mast",
            12.0,
        ),
        (
            "pack_monopole_site",
            {
                "operatorB/design_note.txt": (
                    "Type support: monotube\n"
                    "H=30m\n"
                    "AZ: 20, 140, 260\n"
                    "HMA: 25m, 25m, 25m\n"
                    "RRU remote radio unit\n"
                )
            },
            "monopole",
            30.0,
        ),
    ],
)
def test_document_pack_maps_multiple_site_layouts(
    tmp_path: Path,
    pack_name: str,
    files: dict[str, str | bytes],
    expected_tower_type: str,
    expected_height: float,
) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(_zip(files), filename=f"{pack_name}.zip")
    spec = service.get_spec(summary.pack_id)
    mapping = ProjectDesignSpecMapper().map_to_requirements(spec)

    assert summary.can_generate_design is True
    assert mapping.status == "mapped"
    assert mapping.requirements is not None
    assert mapping.requirements["tower_type"] == expected_tower_type
    assert mapping.requirements["tower_height_m"] == expected_height
    assert mapping.requirements["sector_count"] >= 2


def test_irrelevant_admin_files_are_recorded_but_ignored(tmp_path: Path) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "Admin/bail.txt": "Bail administratif et conditions de location.",
                "Admin/cerfa.txt": "Document administratif.",
                "Photos/vue_site.jpg": b"\xff\xd8\xff\x00",
                "Plan_radio.txt": "Pylône treillis H=30m Azimuts: 0,120,240 HBA: 24m,24m,24m",
            }
        )
    )
    documents = service.get_documents(summary.pack_id)

    assert summary.can_generate_design is True
    assert any(doc["purpose"] == "administrative_reference" for doc in documents)
    assert any(doc["purpose"] == "visual_reference" for doc in documents)
    assert all(
        not doc["used_for_design"]
        for doc in documents
        if doc["purpose"] in {"administrative_reference", "visual_reference"}
    )


def test_document_pack_parses_comma_separated_azimuths_without_spaces(tmp_path: Path) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "APD/radio.txt": (
                    "Type pylone: pylone treillis\n"
                    "Hauteur pylone: 30m\n"
                    "Azimuts: 0,120,240\n"
                    "HBA: 24,24,24\n"
                    "Bandes NR700 NR3500 5G\n"
                )
            }
        )
    )
    mapping = ProjectDesignSpecMapper().map_to_requirements(service.get_spec(summary.pack_id))

    assert summary.can_generate_design is True
    assert mapping.status == "mapped"
    assert mapping.requirements is not None
    assert mapping.requirements["sector_count"] == 3
    assert mapping.requirements["azimuths_deg"] == [0.0, 120.0, 240.0]


def test_document_pack_mapping_preserves_confirmed_accessories(tmp_path: Path) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "APD/accessoires.txt": (
                    "Pylône treillis H=30m\n"
                    "Azimuts: 0, 120, 240\n"
                    "HBA: 24m, 24m, 24m\n"
                    "Bandes NR700 NR3500 5G\n"
                    "Ajouter une antenne GPS GNSS au sommet.\n"
                    "Prévoir une armoire énergie 48V au pied du pylône.\n"
                )
            }
        )
    )
    spec = service.get_spec(summary.pack_id)
    mapping = ProjectDesignSpecMapper().map_to_requirements(spec)

    assert summary.can_generate_design is True
    assert spec.compound_spec["gps"].status == "confirmed"
    assert spec.compound_spec["power_cabinet"].status == "confirmed"
    assert mapping.status == "mapped"
    assert mapping.requirements is not None
    assert mapping.requirements["include_gps_antenna"] is True
    assert mapping.requirements["include_power_cabinet"] is True
    warning_codes = {warning["code"] for warning in mapping.requirements["warnings"]}
    assert "DOC_ACCESSORY_GPS_ENABLED_FROM_EVIDENCE" in warning_codes
    assert "DOC_ACCESSORY_POWER_CABINET_ENABLED_FROM_EVIDENCE" in warning_codes
    fields = {
        field["project_field"]: field["status"] for field in mapping.mapping_loss_report["fields"]
    }
    assert fields["compound.gps"] == "mapped"
    assert fields["compound.power_cabinet"] == "mapped"
    assert "lost_field" not in mapping.mapping_loss_report["counts"]


def test_document_pack_mapping_preserves_confirmed_mechanical_tilt(tmp_path: Path) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "APD/tilt.txt": (
                    "Pylône treillis H=30m\nAzimuts: 0, 120, 240\nHBA: 24m, 24m, 24m\nTilt: 5\n"
                )
            }
        )
    )
    spec = service.get_spec(summary.pack_id)
    mapping = ProjectDesignSpecMapper().map_to_requirements(spec)

    assert summary.can_generate_design is True
    assert spec.radio_sectors[0].mechanical_tilt_deg is not None
    assert spec.radio_sectors[0].mechanical_tilt_deg.value == 5.0
    assert mapping.status == "mapped"
    assert mapping.requirements is not None
    assert mapping.requirements["mechanical_tilt_deg"] == 5.0
    warning_codes = {warning["code"] for warning in mapping.requirements["warnings"]}
    assert "DOC_DEFAULT_MECHANICAL_TILT_USED" not in warning_codes
    fields = {
        field["project_field"]: field["status"] for field in mapping.mapping_loss_report["fields"]
    }
    assert fields["radio.mechanical_tilt_deg"] == "mapped"


def test_document_pack_mapping_respects_explicit_rru_false_correction(tmp_path: Path) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "APD/radio.txt": (
                    "Pylône treillis H=30m\n"
                    "Azimuts: 0, 120, 240\n"
                    "HBA: 24m, 24m, 24m\n"
                    "RRU remote radio unit mentionnée dans une ancienne note\n"
                )
            }
        )
    )
    service.apply_correction(
        summary.pack_id,
        DocumentPackCorrection(
            field="radio.include_rru",
            value=False,
            reason="Current APD confirms that RRU is not installed on the tower.",
        ),
    )
    mapping = ProjectDesignSpecMapper().map_to_requirements(service.get_spec(summary.pack_id))

    assert mapping.status == "mapped"
    assert mapping.requirements is not None
    assert mapping.requirements["include_rru"] is False


def test_dwg_and_scanned_pdf_are_inventory_only_without_hallucination(tmp_path: Path) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "CAD/implantation.dwg": b"DWG bytes",
                "Plans/scanned_plan.pdf": b"%PDF-1.4 scanned placeholder",
            }
        )
    )
    documents = service.get_documents(summary.pack_id)
    spec = service.get_spec(summary.pack_id)

    assert summary.can_generate_design is False
    assert any(
        doc["category"] == "cad_dwg" and doc["cad_status"] == "unsupported" for doc in documents
    )
    assert any(doc["extension"] == "pdf" for doc in documents)
    processing = service.get_processing_report(summary.pack_id)
    assert any(
        document["extension"] == "pdf"
        and document["extraction_status"] in {"unavailable", "failed", "no_text"}
        and document["processing_warnings"]
        for document in processing["documents"]
    )
    assert any(field.field == "tower.tower_height_m" for field in spec.missing_fields)
    assert not spec.radio_sectors


def test_dxf_remains_inventory_only_when_ezdxf_is_missing(tmp_path: Path) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "CAD/radio_layers.dxf": (
                    "0\nSECTION\n2\nENTITIES\n0\nTEXT\n8\nANTENNES\n1\nAzimuts 0 120 240\n"
                )
            }
        )
    )
    documents = service.get_documents(summary.pack_id)
    processing = service.get_processing_report(summary.pack_id)

    assert summary.can_generate_design is False
    assert any(doc["cad_status"] == "inventory_only" for doc in documents)
    assert any(
        document["extension"] == "dxf"
        and document["extraction_status"] in {"inventory_only", "extracted", "failed"}
        for document in processing["documents"]
    )
    if service.capabilities().dxf_parsing.status == "unavailable":
        assert any(
            "ezdxf" in warning
            for document in processing["documents"]
            for warning in document["processing_warnings"]
        )


def test_user_correction_resolves_missing_hba_and_enables_mapping(tmp_path: Path) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "radio_note.txt": (
                    "Type support: pylône treillis\nHauteur pylône: 30m\nAzimuts: 0, 120, 240\n"
                )
            }
        )
    )
    assert summary.can_generate_design is False

    corrected = service.apply_correction(
        summary.pack_id,
        DocumentPackCorrection(
            field="radio.hba_m",
            value=[24.0, 24.0, 24.0],
            reason="HBA confirmed by user from APD page not machine-readable.",
        ),
    )
    spec = service.get_spec(summary.pack_id)
    mapping = ProjectDesignSpecMapper().map_to_requirements(spec)

    assert corrected.can_generate_design is True
    assert corrected.correction_count == 1
    assert mapping.status == "mapped"
    assert spec.radio_sectors[0].hba_m.sources[0].document_id == "user_correction"


def test_user_correction_resolves_conflicting_azimuths(tmp_path: Path) -> None:
    service = DocumentPackService(tmp_path)

    summary = service.ingest_zip(
        _zip(
            {
                "APD_radio.txt": (
                    "Pylône treillis H=30m\nAzimuts: 0, 120, 240\nHBA: 24m, 24m, 24m\n"
                ),
                "old_plan.txt": "AZ: 10, 130, 250\n",
            }
        )
    )
    assert summary.can_generate_design is False
    assert service.get_conflicts(summary.pack_id)

    corrected = service.apply_correction(
        summary.pack_id,
        DocumentPackCorrection(
            field="radio.azimuths_deg",
            value=[0.0, 120.0, 240.0],
            reason="User selected current APD antenna plan values.",
        ),
    )
    spec = service.get_spec(summary.pack_id)
    mapping = ProjectDesignSpecMapper().map_to_requirements(spec)

    assert corrected.can_generate_design is True
    assert service.get_conflicts(summary.pack_id) == []
    assert mapping.status == "mapped"
    assert mapping.requirements is not None
    assert mapping.requirements["azimuths_deg"] == [0.0, 120.0, 240.0]


def _zip(files: dict[str, str | bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            archive.writestr(name, data)
    return buffer.getvalue()
