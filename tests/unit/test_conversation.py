from pathlib import Path

from apps.api.telecom_studio_api.conversation import project_conversation
from apps.api.telecom_studio_api.workflow import _conversation_outcome_payload
from core.contracts.scene_edit import SceneEditResult
from core.services.event_log import EventLogService


def test_journal_restores_all_requests_and_failed_edits_without_duplicate_prompts(tmp_path: Path):
    log = EventLogService(tmp_path)
    wf = "wf_conversation"
    log.emit(
        wf,
        "design_created",
        {"conversation_message": {"role": "user", "text": "Un site 4G compact."}},
    )
    for index in range(6):
        edit = f"edit_{index}"
        log.emit(
            wf,
            "edit_requested",
            {
                "edit_id": edit,
                "target_semantic_root": "radio_S1",
                "conversation_message": {"role": "user", "text": f"Descendre de {index + 1} cm."},
            },
        )
        log.emit(
            wf, "edit_patch_created", {"edit_id": edit, "prompt": f"Descendre de {index + 1} cm."}
        )
        log.emit(
            wf,
            "edit_outcome",
            {
                "edit_id": edit,
                "conversation_message": {"role": "system", "text": "Modification refusée."},
            },
        )
    restored = project_conversation(wf, EventLogService(tmp_path).read_events(wf))
    assert restored.history_status == "recorded"
    assert len(restored.messages) == 13
    assert [m.role for m in restored.messages].count("user") == 7
    assert restored.messages[-2].target_semantic_root == "radio_S1"
    assert restored.messages[-1].text == "Modification refusée."


def test_legacy_history_does_not_invent_initial_prompt_or_assistant_answers(tmp_path: Path):
    log = EventLogService(tmp_path)
    log.emit("wf_old", "design_created", {"detail_level": "high"})
    log.emit("wf_old", "edit_patch_created", {"prompt": "Ajouter un support.", "edit_id": "old"})
    log.emit(
        "wf_old",
        "edit_requested",
        {
            "edit_id": "new",
            "conversation_message": {"role": "user", "text": "Déplacer le support."},
        },
    )
    restored = project_conversation("wf_old", log.read_events("wf_old"))
    assert restored.history_status == "legacy_partial"
    assert [m.text for m in restored.messages] == ["Ajouter un support.", "Déplacer le support."]


def test_corruption_is_visible_and_preserves_readable_messages(tmp_path: Path):
    log = EventLogService(tmp_path)
    log.emit(
        "wf_bad",
        "design_created",
        {"conversation_message": {"role": "user", "text": "Mon design."}},
    )
    with (tmp_path / "wf_bad/workflow_events.jsonl").open("a") as stream:
        stream.write("invalid\n")
    restored = project_conversation("wf_bad", log.read_events("wf_bad"))
    assert restored.history_status == "damaged"
    assert restored.messages[0].text == "Mon design."


def test_edit_outcome_never_claims_a_preserved_version_when_no_active_version_exists():
    failed = _conversation_outcome_payload(
        SceneEditResult(workflow_id="wf_missing", edit_id="edit_missing", status="failed"),
        "edit_missing",
    )
    applied = _conversation_outcome_payload(
        SceneEditResult(
            workflow_id="wf_applied",
            edit_id="edit_applied",
            status="applied",
            version_id="v1234abcd",
        ),
        "edit_applied",
    )

    assert failed["conversation_message"]["text"] == (
        "La modification n’a pas abouti. Vérifiez la version active avant de réessayer."
    )
    assert failed["version_id"] is None
    assert applied["version_id"] == "v1234abcd"


def test_projected_applied_edit_links_the_system_outcome_to_its_verified_version(tmp_path: Path):
    log = EventLogService(tmp_path)
    log.emit(
        "wf_applied",
        "design_created",
        {"conversation_message": {"role": "user", "text": "Créer le site."}},
    )
    log.emit(
        "wf_applied",
        "edit_outcome",
        _conversation_outcome_payload(
            SceneEditResult(
                workflow_id="wf_applied",
                edit_id="edit_applied",
                status="applied",
                version_id="v1234abcd",
            ),
            "edit_applied",
        ),
    )

    restored = project_conversation("wf_applied", log.read_events("wf_applied"))

    assert restored.messages[-1].text == "La modification a été appliquée et vérifiée."
    assert restored.messages[-1].version_id == "v1234abcd"


def test_projection_sanitizes_historical_technical_edit_failures_without_rewriting_journal(
    tmp_path: Path,
) -> None:
    log = EventLogService(tmp_path)
    failures = [
        (
            "sceneSpec does not compile blueprint intent: scene.accessory_asset_ids",
            "composants du design",
        ),
        ("fallback patch could not interpret prompt", "je n’ai pas compris"),
        (
            "platform_count must match len(platform_levels_m)",
            "nombre de plateformes",
        ),
        ("SceneSpec check failed: mount_zones_valid", "zone de montage"),
        (
            "Traceback: KeyError at /sectors/0/install_height_m in worker.py:42",
            "une erreur technique",
        ),
    ]
    for index, (raw, _expected) in enumerate(failures):
        log.emit(
            "wf_historical_failures",
            "edit_outcome",
            {
                "status": "failed",
                "edit_result_status": "failed",
                "edit_id": f"edit_{index}",
                "conversation_message": {"role": "system", "text": raw},
            },
        )

    journal = log.read_events("wf_historical_failures")
    projected = project_conversation("wf_historical_failures", journal)

    assert [event.payload["conversation_message"]["text"] for event in journal.events] == [
        raw for raw, _expected in failures
    ]
    assert all(event.payload["status"] == "failed" for event in journal.events)
    for message, (raw, expected) in zip(projected.messages, failures, strict=True):
        assert message.role == "system"
        assert expected in message.text
        assert raw not in message.text
        assert "La version précédente reste disponible." in message.text
    assert "Traceback" not in projected.messages[-1].text
    assert "/sectors/" not in projected.messages[-1].text
    assert ".py:42" not in projected.messages[-1].text
    assert projected.history_status == "legacy_partial"


def test_projection_preserves_user_text_and_clean_historical_failure_notice(tmp_path: Path) -> None:
    log = EventLogService(tmp_path)
    raw_user_text = "Pourquoi /sectors/0/install_height_m est refusé ?"
    log.emit(
        "wf_clean_notice",
        "edit_requested",
        {
            "edit_id": "edit_clean",
            "conversation_message": {"role": "user", "text": raw_user_text},
        },
    )
    log.emit(
        "wf_clean_notice",
        "edit_outcome",
        {
            "status": "failed",
            "edit_result_status": "rejected",
            "edit_id": "edit_clean",
            "conversation_message": {
                "role": "system",
                "text": "La modification a été refusée. La version précédente est conservée.",
            },
        },
    )

    projected = project_conversation("wf_clean_notice", log.read_events("wf_clean_notice"))

    assert projected.messages[0].text == raw_user_text
    assert projected.messages[1].text == (
        "La modification a été refusée. La version précédente est conservée."
    )
