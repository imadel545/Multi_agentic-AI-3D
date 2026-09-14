import json
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient

from apps.api.telecom_studio_api import main as api_main
from apps.api.telecom_studio_api.main import app, document_pack_service, workflow_service


def test_document_pack_events_normalize_legacy_payload(tmp_path: Path) -> None:
    original_outputs = document_pack_service.outputs_dir
    document_pack_service.outputs_dir = tmp_path
    pack_dir = tmp_path / "document_packs" / "pack_legacy"
    pack_dir.mkdir(parents=True)
    (pack_dir / "events.json").write_text(
        json.dumps(
            [
                {
                    "pack_id": "pack_legacy",
                    "event_type": "document_pack_indexed",
                    "node": "index",
                    "status": "passed",
                    "duration_ms": 3,
                    "payload": {"member_count": 1},
                }
            ]
        ),
        encoding="utf-8",
    )
    try:
        events = document_pack_service.get_events("pack_legacy")

        assert events[0]["event_id"] == "evt_pack_legacy_0000"
        assert events[0]["timestamp"] == "1970-01-01T00:00:00Z"
        assert events[0]["event_source"] == "document_pack_json"
        assert events[0]["payload"]["phase"] == "documents"
        assert events[0]["payload"]["human_label"] == "Inventaire du pack documentaire"
        assert events[0]["payload"]["progress_message"]
    finally:
        document_pack_service.outputs_dir = original_outputs


def test_document_pack_upload_binds_chat_before_success_response(monkeypatch) -> None:
    chat_id = "chat_" + "a" * 32
    pack_id = "pack_" + "b" * 12
    calls: list[tuple[str, str]] = []

    class Summary:
        def __init__(self) -> None:
            self.pack_id = pack_id

        def model_dump(self) -> dict:
            return {"pack_id": pack_id, "status": "ready"}

    monkeypatch.setattr(
        api_main.workspace_store,
        "begin_document_pack_ingest",
        lambda value: calls.append(("reserve", value)),
    )
    monkeypatch.setattr(
        document_pack_service,
        "ingest_zip",
        lambda *_args, **_kwargs: calls.append(("ingest", pack_id)) or Summary(),
    )
    monkeypatch.setattr(
        api_main.workspace_store,
        "complete_document_pack_ingest",
        lambda current_chat, current_pack: calls.append(
            ("complete", f"{current_chat}:{current_pack}")
        ),
    )
    monkeypatch.setattr(
        api_main.workspace_store,
        "cancel_document_pack_ingest",
        lambda current_chat: calls.append(("cancel", current_chat)),
    )

    response = TestClient(app).post(
        "/document-packs",
        content=b"zip",
        headers={
            "content-type": "application/zip",
            "x-chat-id": chat_id,
            "x-filename": "brief.zip",
        },
    )

    assert response.status_code == 200
    assert response.json()["pack_id"] == pack_id
    assert calls == [
        ("reserve", chat_id),
        ("ingest", pack_id),
        ("complete", f"{chat_id}:{pack_id}"),
    ]


def test_document_pack_upload_rejects_invalid_chat_identity_before_ingest(monkeypatch) -> None:
    monkeypatch.setattr(
        document_pack_service,
        "ingest_zip",
        lambda *_args, **_kwargs: pytest.fail("invalid chat must be rejected before ingest"),
    )

    response = TestClient(app).post(
        "/document-packs",
        content=b"zip",
        headers={"content-type": "application/zip", "x-chat-id": "chat_invalid"},
    )

    assert response.status_code == 422


def test_document_pack_upload_rejects_existing_attachment_before_ingest(monkeypatch) -> None:
    chat_id = "chat_" + "c" * 32

    def reject_replacement(_chat_id: str) -> None:
        from fastapi import HTTPException

        raise HTTPException(
            409,
            "Retirez les pièces jointes actuelles avant d’en importer de nouvelles.",
        )

    monkeypatch.setattr(
        api_main.workspace_store,
        "begin_document_pack_ingest",
        reject_replacement,
    )
    monkeypatch.setattr(
        document_pack_service,
        "ingest_zip",
        lambda *_args, **_kwargs: pytest.fail(
            "a replacement upload must be rejected before pack ingestion"
        ),
    )

    response = TestClient(app).post(
        "/document-packs",
        content=b"zip",
        headers={
            "content-type": "application/zip",
            "x-chat-id": chat_id,
            "x-filename": "replacement.zip",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Retirez les pièces jointes actuelles avant d’en importer de nouvelles."
    )


def test_document_pack_delete_unlinks_chat_before_removing_files(monkeypatch) -> None:
    """The workspace must never keep a reference to a successfully deleted pack."""

    chat_id = "chat_" + "c" * 32
    pack_id = "pack_" + "d" * 12
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        api_main.workspace_store,
        "chats_linked_to_document_pack",
        lambda current_pack_id: [chat_id] if current_pack_id == pack_id else [],
    )
    monkeypatch.setattr(
        api_main.workspace_store,
        "get_chat",
        lambda current_chat_id: {
            "chat_id": current_chat_id,
            "document_pack_id": pack_id,
        },
    )

    def update_chat(current_chat_id, update):
        calls.append(
            (
                "update",
                (current_chat_id, update.model_dump(exclude_unset=True)),
            )
        )
        return {"chat_id": current_chat_id, **update.model_dump(exclude_unset=True)}

    monkeypatch.setattr(api_main.workspace_store, "update_chat", update_chat)
    monkeypatch.setattr(
        document_pack_service,
        "delete_pack",
        lambda current_pack_id: (
            calls.append(("delete", current_pack_id))
            or {"pack_id": current_pack_id, "deleted": True}
        ),
    )

    response = TestClient(app).delete(
        f"/document-packs/{pack_id}",
        params={"chat_id": chat_id},
    )

    assert response.status_code == 200
    assert response.json() == {"pack_id": pack_id, "deleted": True}
    assert calls == [
        ("update", (chat_id, {"document_pack_id": None})),
        ("delete", pack_id),
    ]


def test_document_pack_delete_restores_chat_link_when_storage_delete_fails(
    monkeypatch,
) -> None:
    """A recoverable storage failure must not silently orphan an existing pack."""

    chat_id = "chat_" + "e" * 32
    pack_id = "pack_" + "f" * 12
    updates: list[dict] = []
    monkeypatch.setattr(
        api_main.workspace_store,
        "chats_linked_to_document_pack",
        lambda _pack_id: [chat_id],
    )
    monkeypatch.setattr(
        api_main.workspace_store,
        "get_chat",
        lambda current_chat_id: {
            "chat_id": current_chat_id,
            "document_pack_id": pack_id,
        },
    )
    monkeypatch.setattr(
        api_main.workspace_store,
        "update_chat",
        lambda _chat_id, update: updates.append(update.model_dump(exclude_unset=True)) or {},
    )

    def fail_delete(_pack_id: str):
        raise OSError("simulated local storage failure")

    monkeypatch.setattr(document_pack_service, "delete_pack", fail_delete)
    monkeypatch.setattr(
        document_pack_service,
        "get_summary",
        lambda current_pack_id: {"pack_id": current_pack_id},
    )

    response = TestClient(app, raise_server_exceptions=False).delete(
        f"/document-packs/{pack_id}",
        params={"chat_id": chat_id},
    )

    assert response.status_code == 500
    assert updates == [
        {"document_pack_id": None},
        {"document_pack_id": pack_id},
    ]


def test_document_pack_delete_rejects_pack_linked_to_another_chat(monkeypatch) -> None:
    requested_chat_id = "chat_" + "1" * 32
    other_chat_id = "chat_" + "2" * 32
    pack_id = "pack_" + "3" * 12
    monkeypatch.setattr(
        api_main.workspace_store,
        "chats_linked_to_document_pack",
        lambda _pack_id: [requested_chat_id, other_chat_id],
    )
    monkeypatch.setattr(
        document_pack_service,
        "delete_pack",
        lambda _pack_id: pytest.fail("shared pack must not be deleted"),
    )

    response = TestClient(app).delete(
        f"/document-packs/{pack_id}",
        params={"chat_id": requested_chat_id},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Ces pièces jointes sont encore utilisées par une autre conversation."
    )


def test_document_pack_api_endpoints_keep_generation_out_of_attachment_flow(
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
        lambda *_args, **_kwargs: pytest.fail("an attachment endpoint must never start a design"),
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
        capabilities_payload = capabilities.json()
        assert "pdf_text_extraction" in capabilities_payload
        assert capabilities_payload["pdf_layout_extraction"]["status"] in {
            "installed_import_only",
            "unavailable",
        }
        assert capabilities_payload["pdf_layout_extraction"]["status"] != "available"
        assert capabilities_payload["dwg_conversion"]["status"] in {
            "installed_import_only",
            "unsupported_without_converter",
        }
        assert capabilities_payload["limits"]["max_member_count"] == 256
        assert capabilities_payload["limits"]["max_uncompressed_size_mb"] == 200
        assert capabilities_payload["limits"]["execution"] == "thread_offloaded"
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
        assert all(event["event_id"] for event in events)
        assert all(event["timestamp"] for event in events)
        assert all(event["event_source"] == "document_pack_json" for event in events)
        required_payload_fields = {
            "phase",
            "node",
            "human_label",
            "progress_message",
            "status",
            "duration_ms",
            "warnings",
            "errors",
            "artifact_refs",
        }
        assert all(required_payload_fields.issubset(event["payload"]) for event in events)

        generation = client.post(
            f"/document-packs/{pack_id}/generate-design",
            json={"multimodal_consent": "allow_input_analysis"},
        )
        assert generation.status_code == 404
        post_generation_events = client.get(f"/document-packs/{pack_id}/events").json()
        assert not any(
            event["event_type"] == "document_pack_design_generation_started"
            for event in post_generation_events
        )
    finally:
        document_pack_service.outputs_dir = original_outputs
        document_pack_service.groq_extractor.enabled = original_groq_enabled


def test_document_pack_accepts_multiple_direct_files(tmp_path: Path) -> None:
    original_outputs = document_pack_service.outputs_dir
    original_groq_enabled = document_pack_service.groq_extractor.enabled
    document_pack_service.outputs_dir = tmp_path
    document_pack_service.groq_extractor.enabled = False
    client = TestClient(app)
    try:
        response = client.post(
            "/document-packs",
            files=[
                (
                    "files",
                    (
                        "APD_radio.txt",
                        (
                            b"Type pylone: pylone treillis\\nHauteur pylone: 30m\\n"
                            b"Azimuts: 0, 120, 240\\nHBA: 24m, 24m, 24m\\n"
                        ),
                        "text/plain",
                    ),
                ),
                (
                    "files",
                    ("fondation.txt", b"Fondation: concrete_pad\\n", "text/plain"),
                ),
            ],
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["document_count"] == 2
        assert payload["document_names"] == ["APD_radio.txt", "fondation.txt"]
        documents = client.get(f"/document-packs/{payload['pack_id']}/documents").json()
        assert {document["filename"] for document in documents} == {
            "APD_radio.txt",
            "fondation.txt",
        }
        capabilities = client.get("/document-packs/capabilities").json()
        assert capabilities["supported_upload_format"] == "zip_or_multiple_files"
        assert capabilities["supported_inputs"]["upload"] == "zip_or_multiple_files"
        assert ".pdf" in capabilities["supported_extensions"]
        assert ".tiff" not in capabilities["supported_extensions"]
        assert ".xlsx" not in capabilities["supported_extensions"]
    finally:
        document_pack_service.outputs_dir = original_outputs
        document_pack_service.groq_extractor.enabled = original_groq_enabled


def test_document_pack_api_correction_rebuilds_spec_without_starting_generation(
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
        lambda *_args, **_kwargs: pytest.fail(
            "correcting attachment metadata must not start a design"
        ),
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
        events = client.get(f"/document-packs/{pack_id}/events").json()
        correction_event = next(
            event for event in events if event["event_type"] == "document_pack_corrected"
        )
        assert correction_event["payload"]["field"] == "radio.hba_m"
        assert correction_event["payload"]["can_generate_design"] is True
        assert correction_event["payload"]["human_label"] == "Correction utilisateur"

        spec = client.get(f"/document-packs/{pack_id}/consolidated-spec").json()
        assert spec["radio_sectors"][0]["hba_m"]["sources"][0]["document_id"] == ("user_correction")
        generation = client.post(f"/document-packs/{pack_id}/generate-design")
        assert generation.status_code == 404
    finally:
        document_pack_service.outputs_dir = original_outputs
        document_pack_service.groq_extractor.enabled = original_groq_enabled


def test_document_pack_upload_runs_blocking_ingestion_off_event_loop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_outputs = document_pack_service.outputs_dir
    original_groq_enabled = document_pack_service.groq_extractor.enabled
    document_pack_service.outputs_dir = tmp_path
    document_pack_service.groq_extractor.enabled = False
    calls: list[str] = []

    async def tracked_run_in_threadpool(function, *args, **kwargs):
        calls.append(function.__name__)
        return function(*args, **kwargs)

    monkeypatch.setattr(api_main, "run_in_threadpool", tracked_run_in_threadpool)
    try:
        response = TestClient(app).post(
            "/document-packs",
            content=_pack_zip(),
            headers={"content-type": "application/zip"},
        )

        assert response.status_code == 200
        assert calls == ["ingest_zip"]
    finally:
        document_pack_service.outputs_dir = original_outputs
        document_pack_service.groq_extractor.enabled = original_groq_enabled


def test_document_pack_invalid_zip_returns_422_and_leaves_no_partial_pack(
    tmp_path: Path,
) -> None:
    original_outputs = document_pack_service.outputs_dir
    document_pack_service.outputs_dir = tmp_path
    try:
        response = TestClient(app).post(
            "/document-packs",
            content=b"not-a-zip",
            headers={"content-type": "application/zip"},
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "invalid ZIP archive"
        assert not (tmp_path / "document_packs").exists()
    finally:
        document_pack_service.outputs_dir = original_outputs


def test_document_pack_generation_endpoint_is_not_exposed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_outputs = document_pack_service.outputs_dir
    original_groq_enabled = document_pack_service.groq_extractor.enabled
    document_pack_service.outputs_dir = tmp_path
    document_pack_service.groq_extractor.enabled = False
    summary = document_pack_service.ingest_zip(_pack_zip())
    monkeypatch.setattr(
        workflow_service,
        "create_design_from_requirements",
        lambda *_args, **_kwargs: pytest.fail("a document pack alone must not start generation"),
    )
    try:
        response = TestClient(app).post(f"/document-packs/{summary.pack_id}/generate-design")

        assert response.status_code == 404
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
                "Fondation: massif béton\n"
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
            (
                "Pylône treillis H=30m\n"
                "Fondation: massif béton\n"
                "Azimuts: 0, 120, 240\n"
                "Bandes: NR3500 5G\n"
                "RRU et câbles\n"
            ),
        )
    return buffer.getvalue()
