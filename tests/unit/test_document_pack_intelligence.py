from io import BytesIO, StringIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from core.document_pack import DocumentPackService, ProjectDesignSpecMapper
from core.memory import MemoryService


def test_document_pack_valid_dxf_extracts_layered_cad_evidence(tmp_path: Path) -> None:
    ezdxf = pytest.importorskip("ezdxf")
    doc = ezdxf.new()
    doc.layers.add("ANTENNES")
    doc.modelspace().add_text(
        "Pylone treillis Hauteur pylone: 30m Azimuts: 0, 120, 240 "
        "HBA: 24m, 24m, 24m Bandes: NR3500 5G",
        dxfattribs={"layer": "ANTENNES"},
    )
    stream = StringIO()
    doc.write(stream)

    service = DocumentPackService(tmp_path)
    summary = service.ingest_zip(_zip({"CAD/antennes.dxf": stream.getvalue()}))
    documents = service.get_documents(summary.pack_id)
    spec = service.get_spec(summary.pack_id)

    assert any(
        document["extension"] == "dxf"
        and document["cad_status"] == "parsed"
        and document["extraction_status"] == "extracted"
        for document in documents
    )
    assert spec.provenance_map["radio.azimuths_deg"][0].source_type == "cad"
    assert spec.provenance_map["radio.azimuths_deg"][0].layer == "ANTENNES"
    assert ProjectDesignSpecMapper().map_to_requirements(spec).status == "mapped"


def test_document_pack_ocr_pdf_image_only_keeps_ocr_provenance(tmp_path: Path) -> None:
    service = DocumentPackService(tmp_path)
    if service.capabilities().ocr.status != "available":
        pytest.skip("OCR stack is not available in this environment")

    summary = service.ingest_zip(_zip({"Plans/APD_scanned.pdf": _scanned_pdf_bytes()}))
    spec = service.get_spec(summary.pack_id)
    processing = service.get_processing_report(summary.pack_id)

    assert any(document["extraction_status"] == "extracted" for document in processing["documents"])
    assert any(
        source.source_type == "ocr"
        for sources in spec.provenance_map.values()
        for source in sources
    )
    assert spec.tower_spec["tower_height_m"].value == 30.0


def test_document_pack_groq_bounded_extraction_requires_evidence(tmp_path: Path) -> None:
    service = DocumentPackService(
        tmp_path,
        groq_client=FakeGroqDocumentProvider(),
        groq_provider_name="groq:test",
        groq_bounded_extraction_enabled=True,
    )

    summary = service.ingest_zip(
        _zip(
            {
                "APD_plan.txt": (
                    "Pylone treillis\n"
                    "Hauteur pylone: 30m\n"
                    "Azimuts: 0, 120, 240\n"
                    "HBA: 24m, 24m, 24m\n"
                )
            }
        )
    )
    spec = service.get_spec(summary.pack_id)
    processing = service.get_processing_report(summary.pack_id)

    assert spec.source_mode == "mixed"
    assert spec.llm_provider == "groq:test"
    assert spec.llm_fallback_used is False
    assert spec.groq_rejected_fields[0]["reason"] == "missing_evidence"
    assert processing["groq_rejected_fields"]


def test_document_pack_groq_values_are_normalized_from_evidence(tmp_path: Path) -> None:
    service = DocumentPackService(
        tmp_path,
        groq_client=FakeGroqTypedDocumentProvider(),
        groq_provider_name="groq:test",
        groq_bounded_extraction_enabled=True,
    )

    summary = service.ingest_zip(
        _zip(
            {
                "APD/current.txt": (
                    "Type pylone: pylone treillis\n"
                    "Hauteur pylone: 30m\n"
                    "Azimuts: 0,120,240\n"
                    "HBA: 24,24,24\n"
                    "Bandes NR700 NR3500 5G\n"
                )
            }
        )
    )
    spec = service.get_spec(summary.pack_id)

    assert summary.can_generate_design is True
    assert spec.conflicts == []
    assert [sector.hba_m.value for sector in spec.radio_sectors] == [24.0, 24.0, 24.0]
    assert spec.radio_sectors[0].bands is not None
    assert spec.radio_sectors[0].bands.value == ["5G", "NR3500", "NR700"]


def test_document_pack_rejects_groq_value_not_supported_by_quote(tmp_path: Path) -> None:
    class InventedHeightProvider:
        model = "openai/gpt-oss-120b"

        def _post_raw(self, payload: dict) -> dict:
            user_content = payload["messages"][1]["content"]
            document_id = user_content.split("document_id=", 1)[1].split(" ", 1)[0]
            return {
                "fields": [
                    {
                        "field": "tower.tower_height_m",
                        "value": 45,
                        "confidence": 0.99,
                        "document_id": document_id,
                        "page": None,
                        "evidence": "Hauteur pylone: 30m",
                    }
                ]
            }

    service = DocumentPackService(
        tmp_path,
        groq_client=InventedHeightProvider(),
        groq_provider_name="groq:test",
        groq_bounded_extraction_enabled=True,
    )
    summary = service.ingest_zip(
        _zip({"APD.txt": "Pylone treillis\nHauteur pylone: 30m\nAzimuts: 0,120,240\nHBA: 24,24,24"})
    )
    spec = service.get_spec(summary.pack_id)

    assert spec.tower_spec["tower_height_m"].value == 30.0
    assert any(
        item["reason"] == "value_not_supported_by_evidence" for item in spec.groq_rejected_fields
    )


def test_document_pack_rejects_groq_boolean_without_matching_evidence(tmp_path: Path) -> None:
    class InventedGpsProvider:
        model = "openai/gpt-oss-120b"

        def _post_raw(self, payload: dict) -> dict:
            user_content = payload["messages"][1]["content"]
            document_id = user_content.split("document_id=", 1)[1].split(" ", 1)[0]
            return {
                "fields": [
                    {
                        "field": "compound.gps",
                        "value": True,
                        "confidence": 0.99,
                        "document_id": document_id,
                        "page": None,
                        "evidence": "Hauteur pylone: 30m",
                    }
                ]
            }

    service = DocumentPackService(
        tmp_path,
        groq_client=InventedGpsProvider(),
        groq_provider_name="groq:test",
        groq_bounded_extraction_enabled=True,
    )
    summary = service.ingest_zip(
        _zip({"APD.txt": "Pylone treillis\nHauteur pylone: 30m\nAzimuts: 0,120,240\nHBA: 24,24,24"})
    )
    spec = service.get_spec(summary.pack_id)

    assert any(
        item["field"] == "compound.gps" and item["reason"] == "value_not_supported_by_evidence"
        for item in spec.groq_rejected_fields
    )


def test_document_pack_memory_writeback_uses_compact_metadata(tmp_path: Path) -> None:
    memory = MemoryService(tmp_path / "memory.db")
    service = DocumentPackService(tmp_path, memory_service=memory)

    summary = service.ingest_zip(
        _zip(
            {
                "APD_plan.txt": (
                    "Pylone treillis\n"
                    "Hauteur pylone: 30m\n"
                    "Azimuts: 0, 120, 240\n"
                    "HBA: 24m, 24m, 24m\n"
                )
            }
        )
    )
    qa = service.get_qa_report(summary.pack_id)
    stats = memory.stats()

    assert stats["document_pack_memory_count"] == 1
    assert qa["memory_writeback"]["status"] == "written"
    assert qa["memory_writeback"]["qdrant"]["status"] == "skipped"


class FakeGroqDocumentProvider:
    model = "openai/gpt-oss-120b"

    def _post_raw(self, payload: dict) -> dict:
        user_content = payload["messages"][1]["content"]
        assert "document_id=" in user_content
        document_id = user_content.split("document_id=", 1)[1].split(" ", 1)[0]
        return {
            "fields": [
                {
                    "field": "tower.tower_height_m",
                    "value": 30,
                    "confidence": 0.91,
                    "document_id": document_id,
                    "page": None,
                    "evidence": "Hauteur pylone: 30m",
                },
                {
                    "field": "compound.gps",
                    "value": True,
                    "confidence": 0.7,
                    "document_id": document_id,
                    "page": None,
                    "evidence": "",
                },
            ]
        }


class FakeGroqTypedDocumentProvider:
    model = "openai/gpt-oss-120b"

    def _post_raw(self, payload: dict) -> dict:
        user_content = payload["messages"][1]["content"]
        document_id = user_content.split("document_id=", 1)[1].split(" ", 1)[0]
        return {
            "fields": [
                {
                    "field": "radio.hba_m",
                    "value": "242424",
                    "confidence": 0.9,
                    "document_id": document_id,
                    "page": None,
                    "evidence": "HBA: 24,24,24",
                },
                {
                    "field": "radio.bands",
                    "value": "NR700 NR3500 5G",
                    "confidence": 0.88,
                    "document_id": document_id,
                    "page": None,
                    "evidence": "Bandes NR700 NR3500 5G",
                },
            ]
        }


def _scanned_pdf_bytes() -> bytes:
    fitz = pytest.importorskip("fitz")
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")
    ImageFont = pytest.importorskip("PIL.ImageFont")

    image = Image.new("RGB", (760, 430), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=30)
    except TypeError:
        font = ImageFont.load_default()
    draw.multiline_text(
        (35, 35),
        ("Pylone treillis\nHauteur pylone: 30m\nAzimuts: 0, 120, 240\nHBA: 24m, 24m, 24m"),
        fill="black",
        font=font,
        spacing=10,
    )
    image_buffer = BytesIO()
    image.save(image_buffer, format="PNG")

    pdf = fitz.open()
    page = pdf.new_page(width=360, height=220)
    page.insert_image(page.rect, stream=image_buffer.getvalue())
    return pdf.tobytes()


def _zip(files: dict[str, str | bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            data = content.encode("utf-8") if isinstance(content, str) else content
            archive.writestr(name, data)
    return buffer.getvalue()
