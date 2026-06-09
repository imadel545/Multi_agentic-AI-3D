from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.main import app, document_pack_service, workflow_service


def test_document_pack_api_endpoints_and_generate_design_mapping(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_outputs = document_pack_service.outputs_dir
    original_groq_enabled = document_pack_service.groq_extractor.enabled
    document_pack_service.outputs_dir = tmp_path
    document_pack_service.groq_extractor.enabled = False

    def fake_create_design_from_requirements(
        requirements,
        *,
        detail_level: str,
        source_label: str,
    ) -> dict:
        assert requirements.azimuths_deg == [0.0, 120.0, 240.0]
        assert detail_level == "high"
        assert source_label == "project_design_spec"
        return {"workflow_id": "wf_from_pack", "status": "pending"}

    monkeypatch.setattr(
        workflow_service,
        "create_design_from_requirements",
        fake_create_design_from_requirements,
    )
    client = TestClient(app)
    try:
        response = client.post(
            "/document-packs",
            content=_pack_zip(),
            headers={"content-type": "application/zip", "x-filename": "fixture.zip"},
        )
        assert response.status_code == 200
        summary = response.json()
        pack_id = summary["pack_id"]
        assert summary["can_generate_design"] is True

        documents = client.get(f"/document-packs/{pack_id}/documents").json()
        assert any(document["category"] == "antenna_plan" for document in documents)
        spec = client.get(f"/document-packs/{pack_id}/consolidated-spec").json()
        assert spec["tower_spec"]["tower_height_m"]["value"] == 30.0
        assert spec["radio_sectors"][0]["azimuth_deg"]["sources"]
        provenance = client.get(f"/document-packs/{pack_id}/provenance").json()
        assert "tower.tower_height_m" in provenance
        qa = client.get(f"/document-packs/{pack_id}/qa").json()
        assert qa["score"] >= 0.7
        missing = client.get(f"/document-packs/{pack_id}/missing-fields").json()
        assert not [field for field in missing if field["severity"] == "blocking"]
        capabilities = client.get("/document-packs/capabilities")
        assert capabilities.status_code == 200
        assert "pdf_text_extraction" in capabilities.json()
        processing = client.get(f"/document-packs/{pack_id}/processing").json()
        assert processing["pack_id"] == pack_id
        assert processing["documents"][0]["extraction_status"] == "extracted"
        memory = client.get(f"/document-packs/{pack_id}/memory-summary").json()
        assert memory["type"] == "document_pack_memory_summary"
        assert memory["can_generate_design"] is True
        trace = client.get(f"/document-packs/{pack_id}/trace").json()
        events = client.get(f"/document-packs/{pack_id}/events").json()
        assert [step["node"] for step in trace][:3] == [
            "index",
            "extract_pdf_ocr_cad",
            "groq_extract",
        ]
        assert any(event["event_type"] == "document_pack_qa_completed" for event in events)

        generation = client.post(f"/document-packs/{pack_id}/generate-design").json()
        assert generation["status"] == "pending"
        assert generation["workflow_id"] == "wf_from_pack"
        assert generation["mapping"]["status"] == "mapped"
        assert generation["extraction_report"]["prompt_text_reparse"] is False
    finally:
        document_pack_service.outputs_dir = original_outputs
        document_pack_service.groq_extractor.enabled = original_groq_enabled


def test_document_pack_api_correction_rebuilds_spec_and_unblocks_generation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_outputs = document_pack_service.outputs_dir
    original_groq_enabled = document_pack_service.groq_extractor.enabled
    document_pack_service.outputs_dir = tmp_path
    document_pack_service.groq_extractor.enabled = False
    monkeypatch.setattr(
        workflow_service,
        "create_design_from_requirements",
        lambda requirements, detail_level, source_label: {
            "workflow_id": "wf_after_correction",
            "status": "pending",
        },
    )
    client = TestClient(app)
    try:
        response = client.post(
            "/document-packs",
            content=_missing_hba_pack_zip(),
            headers={"content-type": "application/zip"},
        )
        pack_id = response.json()["pack_id"]
        assert response.json()["can_generate_design"] is False

        correction = client.post(
            f"/document-packs/{pack_id}/corrections",
            json={
                "field": "radio.hba_m",
                "value": [24.0, 24.0, 24.0],
                "reason": "Manual APD review confirmed HBA.",
            },
        )
        assert correction.status_code == 200
        assert correction.json()["can_generate_design"] is True
        assert correction.json()["correction_count"] == 1

        spec = client.get(f"/document-packs/{pack_id}/consolidated-spec").json()
        assert spec["radio_sectors"][0]["hba_m"]["sources"][0]["document_id"] == ("user_correction")
        generation = client.post(f"/document-packs/{pack_id}/generate-design").json()
        assert generation["workflow_id"] == "wf_after_correction"
        assert generation["mapping"]["status"] == "mapped"
    finally:
        document_pack_service.outputs_dir = original_outputs
        document_pack_service.groq_extractor.enabled = original_groq_enabled


def _pack_zip() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "APD_plan_antennes.txt",
            (
                "Code site: IMD123\n"
                "Type pylône: pylône treillis\n"
                "Hauteur pylône: 30m\n"
                "Azimuts: 0, 120, 240\n"
                "HBA: 24m, 24m, 24m\n"
                "Bandes: NR700 NR3500 5G\n"
                "RRU et câbles\n"
            ),
        )
    return buffer.getvalue()


def _missing_hba_pack_zip() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "radio_plan.txt",
            "Pylône treillis H=30m\nAzimuts: 0, 120, 240\nRRU et câbles\n",
        )
    return buffer.getvalue()
