"""Pure event presentation and replay cursor rules for the public workflow stream."""

import json


def event_identity(event: dict) -> str:
    event_id = event.get("event_id")
    if isinstance(event_id, str) and event_id:
        return event_id
    return json.dumps(
        {
            "event_type": event.get("event_type"),
            "workflow_id": event.get("workflow_id"),
            "timestamp": event.get("timestamp"),
            "payload": event.get("payload"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def events_after(events: list[dict], after_event_id: str | None) -> list[dict]:
    if not after_event_id:
        return events
    for index, event in enumerate(events):
        if event_identity(event) == after_event_id:
            return events[index + 1 :]
    # A stale/unknown cursor must not silently hide the durable event history.
    return events


def normalized_event_payload(event_type: str, payload: dict) -> dict:
    normalized = dict(payload)
    node = str(normalized.get("node") or _event_default_node(event_type))
    phase = str(normalized.get("phase") or _event_default_phase(event_type, node))
    status = str(normalized.get("status") or _event_default_status(event_type))
    human_label = str(normalized.get("human_label") or _event_human_label(event_type, node))
    progress_message = str(
        normalized.get("progress_message")
        or _event_progress_message(event_type, status, human_label)
    )
    normalized["node"] = node
    normalized["phase"] = phase
    normalized["status"] = status
    normalized["human_label"] = human_label
    normalized["progress_message"] = progress_message
    normalized.setdefault("duration_ms", None)
    if not isinstance(normalized.get("warnings"), list):
        normalized["warnings"] = []
    if not isinstance(normalized.get("errors"), list):
        normalized["errors"] = []
    if not isinstance(normalized.get("artifact_refs"), list):
        normalized["artifact_refs"] = []
    return normalized


def _event_default_node(event_type: str) -> str:
    if event_type in {"qa_completed", "qa_failed"}:
        return "qa_generation"
    if event_type in {"blender_completed", "blender_failed", "artifact_ready"}:
        return "generate_blender"
    if event_type.startswith("edit_"):
        return "edit"
    if event_type.startswith("version_"):
        return "versioning"
    if event_type == "user_issue_created":
        return "issues"
    return "workflow"


def _event_default_phase(event_type: str, node: str) -> str:
    if node in {"generate_blender", "blender_failure_handler"}:
        return "blender" if event_type != "artifact_ready" else "viewer"
    if node == "qa_generation":
        return "qa"
    if node == "edit":
        return "edit"
    if node == "versioning":
        return "versioning"
    if node == "issues":
        return "issues"
    return "workflow"


def _event_default_status(event_type: str) -> str:
    if event_type.endswith("_failed") or event_type in {"workflow_failed", "edit_patch_rejected"}:
        return "failed"
    if event_type in {"design_created", "validated_requirements_received"}:
        return "running"
    if event_type == "user_issue_created":
        return "warning"
    return "completed"


def _event_human_label(event_type: str, node: str) -> str:
    mapping = {
        "design_created": "Design créé",
        "validated_requirements_received": "Exigences validées reçues",
        "workflow_completed": "Design prêt",
        "workflow_failed": "Workflow en échec",
        "artifact_ready": "Préparation du viewer 3D",
        "qa_completed": "Vérification géométrique terminée",
        "qa_failed": "Vérification géométrique en échec",
        "user_issue_created": "Issue utilisateur créée",
        "edit_patch_created": "Patch d'édition créé",
        "edit_patch_interpreted": "Modification comprise",
        "edit_patch_rejected": "Patch d'édition rejeté",
        "edit_patch_applied": "Édition appliquée",
        "version_created": "Version créée",
        "version_rolled_back": "Version restaurée",
        "blender_completed": "Génération Blender terminée",
        "blender_failed": "Génération Blender en échec",
    }
    return mapping.get(event_type, node.replace("_", " ").capitalize())


def _event_progress_message(event_type: str, status: str, human_label: str) -> str:
    mapping = {
        "design_created": "Le backend prépare le workflow de génération.",
        "validated_requirements_received": (
            "Le backend utilise les exigences consolidées du document pack."
        ),
        "workflow_completed": "Le design est prêt pour inspection 3D.",
        "workflow_failed": "Le design n'a pas pu être terminé.",
        "artifact_ready": "Les artefacts du viewer 3D sont disponibles.",
        "qa_completed": "Le contrôle qualité du modèle 3D est terminé.",
        "qa_failed": "Le contrôle qualité a détecté un blocage.",
        "user_issue_created": "Une limitation ou erreur est visible pour l'utilisateur.",
        "edit_patch_created": "Le backend prépare une modification de SceneSpec.",
        "edit_patch_rejected": "L'édition a été refusée avec une raison exploitable.",
        "edit_patch_applied": "La nouvelle version du design est disponible.",
        "version_created": "Une version locale a été créée.",
        "version_rolled_back": "La version active a été restaurée.",
        "blender_completed": "Blender a terminé la génération 3D.",
        "blender_failed": "Blender n'a pas produit un résultat valide.",
    }
    return mapping.get(event_type, f"{human_label} : {status}.")


def issue_event_title(issue: dict) -> str:
    code = str(issue.get("code") or "")
    if code == "WORKFLOW_EXCEPTION":
        return "Échec du workflow"
    if code.startswith("ASSET_"):
        return "Issue asset détectée"
    if code.startswith("BLENDER_"):
        return "Issue Blender détectée"
    if code.startswith("QA_") or code.startswith("GEOMETRY_"):
        return "Issue qualité détectée"
    if issue.get("severity") == "error":
        return "Erreur détectée"
    return "Avertissement détecté"
