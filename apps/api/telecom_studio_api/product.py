"""Product-oriented API layer.

Transforms technical backend status/events into user-facing responses.
The future chat-first/3D-first frontend should consume these endpoints
instead of parsing raw JSON technical reports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apps.api.telecom_studio_api.workflow import WorkflowService
from core.services.asset_inventory import AssetInventoryService


class ProductService:
    def __init__(
        self,
        workflow_service: WorkflowService,
        asset_inventory_service: AssetInventoryService,
    ) -> None:
        self.workflow_service = workflow_service
        self.asset_inventory_service = asset_inventory_service

    def studio_summary(self) -> dict:
        designs = self.workflow_service.list_designs(limit=200, offset=0)
        inventory = self.asset_inventory_service.inspect()
        inventory_status = _inventory_status(inventory)
        blender_available = _blender_available_from_inventory(inventory)
        groq_available = _groq_available_from_inventory(inventory)

        counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
        summaries = []
        for design in designs:
            status = design.get("status", "unknown")
            if status in counts:
                counts[status] += 1
            elif status == "running":
                counts["running"] += 1
            summaries.append(
                {
                    "workflow_id": design.get("workflow_id"),
                    "status": status,
                    "created_at": design.get("created_at"),
                    "qa_score": design.get("qa_score"),
                    "generation_mode": design.get("generation_mode"),
                    "current_operation": _operation_for_status(status),
                }
            )

        return {
            "designs": summaries,
            "total_designs": len(designs),
            "active_designs": counts["running"] + counts["pending"],
            "completed_designs": counts["completed"],
            "failed_designs": counts["failed"],
            "pending_designs": counts["pending"],
            "asset_inventory_status": inventory_status,
            "blender_available": blender_available,
            "groq_available": groq_available,
            "warnings": _studio_warnings(inventory),
        }

    def user_summary(self, workflow_id: str) -> dict:
        status = self._status_or_raise(workflow_id)
        issues = _collect_user_issues(status)
        qa_summary = _qa_summary(status)
        next_action = _next_recommended_action(status, issues)
        return {
            "workflow_id": workflow_id,
            "status": status.get("status", "unknown"),
            "current_operation": _current_operation(status),
            "next_recommended_action": next_action,
            "qa_summary": qa_summary,
            "human_readable_issues": issues,
            "active_version": status.get("active_version_id"),
            "generation_mode": status.get("generation_mode"),
            "asset_quality_summary": _asset_quality_summary(status),
            "limitations": _collect_limitations(status),
        }

    def current_operation(self, workflow_id: str) -> dict:
        status = self._status_or_raise(workflow_id)
        issues = _collect_user_issues(status)
        return {
            "workflow_id": workflow_id,
            "status": status.get("status", "unknown"),
            "current_operation": _current_operation(status),
            "next_recommended_action": _next_recommended_action(status, issues),
            "progress_indicator": _progress_indicator(status),
        }

    def user_issues(self, workflow_id: str) -> dict:
        status = self._status_or_raise(workflow_id)
        return {
            "workflow_id": workflow_id,
            "status": status.get("status", "unknown"),
            "human_readable_issues": _collect_user_issues(status),
        }

    def viewer_bundle(self, workflow_id: str) -> dict:
        status = self._status_or_raise(workflow_id)
        active_version = status.get("active_version_id")
        base_url = f"/designs/{workflow_id}/artifacts"
        viewer_artifacts = []

        def _artifact(name: str, content_type: str, filename: str) -> dict:
            url = f"{base_url}/{filename}"
            if active_version:
                url = f"{url}?version_id={active_version}"
            path = self._artifact_path_or_none(workflow_id, filename, active_version)
            return {
                "name": name,
                "url": url,
                "content_type": content_type,
                "available": path is not None and path.exists(),
            }

        viewer_artifacts.append(_artifact("design.glb", "model/gltf-binary", "glb"))
        viewer_artifacts.append(_artifact("preview.png", "image/png", "preview"))
        viewer_artifacts.append(
            _artifact("technical_report.md", "text/markdown", "technical_report")
        )

        return {
            "workflow_id": workflow_id,
            "status": status.get("status", "unknown"),
            "active_version": active_version,
            "viewer_artifacts": viewer_artifacts,
        }

    def timeline_summary(self, workflow_id: str) -> dict:
        status = self._status_or_raise(workflow_id)
        events = self.workflow_service.get_events(workflow_id)
        return {
            "workflow_id": workflow_id,
            "status": status.get("status", "unknown"),
            "timeline_steps": _events_to_timeline(events, status),
        }

    def _status_or_raise(self, workflow_id: str) -> dict:
        try:
            return self.workflow_service.get_status(workflow_id)
        except KeyError as exc:
            raise ProductNotFound(workflow_id) from exc

    def _artifact_path_or_none(
        self, workflow_id: str, artifact_name: str, version_id: str | None
    ) -> Path | None:
        try:
            return self.workflow_service.artifact_path(
                workflow_id, artifact_name, version_id=version_id
            )
        except KeyError:
            return None


class ProductNotFound(Exception):
    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        super().__init__(f"workflow not found: {workflow_id}")


def _inventory_status(inventory: dict) -> str:
    summaries = inventory.get("asset_summaries", [])
    if not summaries:
        return "unknown"
    total = len(summaries)
    ready = sum(1 for s in summaries if s.get("glb_ready"))
    fallback = sum(1 for s in summaries if s.get("fallback_used"))
    if ready == total and total > 0:
        return "ready"
    if fallback > 0:
        return f"partial ({fallback} fallback)"
    return "incomplete"


def _blender_available_from_inventory(inventory: dict) -> bool | None:
    return inventory.get("blender_available")


def _groq_available_from_inventory(inventory: dict) -> bool | None:
    return inventory.get("groq_available")


def _operation_for_status(status: str) -> str:
    mapping = {
        "pending": "En attente de traitement",
        "running": "Génération en cours",
        "completed": "Design terminé",
        "failed": "Échec de la génération",
    }
    return mapping.get(status, status)


def _current_operation(status: dict) -> str:
    backend_status = status.get("status", "unknown")
    metrics = status.get("metrics", {})
    if backend_status == "pending":
        return "Le design est en file d'attente et va démarrer."
    if backend_status == "failed":
        return "Le design a échoué. Consultez les problèmes pour corriger la situation."
    if backend_status == "completed":
        return "Le design est terminé. Vous pouvez l'inspecter en 3D."
    running_step = metrics.get("current_step")
    if running_step:
        return f"Étape en cours : {running_step}"
    return f"Traitement en cours ({backend_status})"


def _progress_indicator(status: dict) -> str | None:
    backend_status = status.get("status", "unknown")
    if backend_status == "pending":
        return "queued"
    if backend_status == "completed":
        return "done"
    if backend_status == "failed":
        return "failed"
    return "running"


def _qa_summary(status: dict) -> str:
    qa_score = status.get("qa_score")
    if qa_score is None:
        return "Qualité non encore évaluée."
    if qa_score >= 0.95:
        return f"Qualité excellente ({qa_score:.0%})."
    if qa_score >= 0.8:
        return f"Qualité acceptable ({qa_score:.0%}) avec quelques avertissements."
    if qa_score >= 0.5:
        return f"Qualité limitée ({qa_score:.0%}). Vérifiez les problèmes signalés."
    return f"Qualité insuffisante ({qa_score:.0%}). Un correctif est probablement nécessaire."


def _asset_quality_summary(status: dict) -> str | None:
    asset_imports = status.get("asset_imports") or []
    if not asset_imports:
        asset_summary = status.get("asset_import_summary")
        if asset_summary:
            fallback = asset_summary.get("fallback_used", False)
            source = asset_summary.get("source", "unknown")
            if fallback:
                return f"Asset source : {source} (fallback utilisé)"
            return f"Asset source : {source}"
        return None
    fallback_count = sum(1 for a in asset_imports if a.get("fallback_used"))
    internal_count = sum(1 for a in asset_imports if a.get("source") == "internal")
    if fallback_count:
        return f"{fallback_count} asset(s) en fallback, {internal_count} asset(s) interne(s)."
    return f"{len(asset_imports)} asset(s) importé(s) correctement."


def _collect_limitations(status: dict) -> list[str]:
    limitations = []
    if status.get("blender_available") is False:
        limitations.append(
            "Blender n'est pas installé : le modèle 3D est un fallback, pas un vrai GLB."
        )
    if status.get("llm_fallback_used"):
        limitations.append("L'extraction a utilisé le fallback déterministe, pas le LLM.")
    generation_mode = status.get("generation_mode")
    if generation_mode in {"fallback", "procedural_fallback"}:
        limitations.append("Le mode de génération est un fallback.")
    return limitations


def _next_recommended_action(status: dict, issues: list[dict]) -> str:
    backend_status = status.get("status", "unknown")
    if backend_status == "pending":
        return "Patientez pendant que le design démarre."
    if backend_status == "failed":
        return "Relisez le prompt ou le document pack, corrigez les problèmes, puis relancez."
    if backend_status == "completed":
        if issues:
            return "Le design est prêt, mais vérifiez les avertissements avant de valider."
        return "Le design est prêt. Vous pouvez l'inspecter, l'éditer ou télécharger les artefacts."
    return "Le traitement est en cours ; patientez ou consultez l'opération actuelle."


def _collect_user_issues(status: dict) -> list[dict]:
    issues: list[dict] = []
    for item in status.get("warnings", []):
        issue = _warning_to_user_issue(item)
        if issue:
            issues.append(issue)
    for item in status.get("errors", []):
        issue = _warning_to_user_issue(item)
        if issue:
            issue["severity"] = "error"
            issues.append(issue)

    # Add inferred limitations as issues when no explicit warning exists
    if status.get("blender_available") is False and not any(
        i.get("technical_code") == "BLENDER_NOT_AVAILABLE" for i in issues
    ):
        issues.append(
            {
                "title": "Blender non disponible",
                "severity": "warning",
                "impact": (
                    "Le modèle 3D généré est un fallback texte/procédural, pas un vrai GLB Blender."
                ),
                "recommended_action": "Installez Blender 4.5+ pour obtenir un modèle 3D réel.",
                "technical_code": "BLENDER_NOT_AVAILABLE_INFERRED",
            }
        )
    if status.get("llm_fallback_used") and not any(
        i.get("technical_code") == "LLM_FALLBACK_USED" for i in issues
    ):
        issues.append(
            {
                "title": "Extraction déterministe",
                "severity": "info",
                "impact": "Le LLM n'a pas été utilisé ; l'extraction repose sur des règles fixes.",
                "recommended_action": (
                    "Configurez GROQ_API_KEY pour activer l'extraction intelligente."
                ),
                "technical_code": "LLM_FALLBACK_USED_INFERRED",
            }
        )
    return issues


_KNOWN_ISSUE_MAPPINGS: dict[str, dict[str, Any]] = {
    "ASSET_IMPORT_INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR": {
        "title": "Asset interne minimal",
        "impact": "Le design est valide techniquement mais l'asset n'est pas vendor-grade.",
        "recommended_action": "Remplacer plus tard par un asset constructeur réaliste.",
    },
    "FALLBACK_DETERMINISTIC_EXTRACTION_USED": {
        "title": "Extraction déterministe utilisée",
        "impact": "Les exigences ont été extraites avec des règles fixes, pas par LLM.",
        "recommended_action": "Vérifiez les champs clés et corrigez si nécessaire.",
    },
    "BLENDER_NOT_AVAILABLE": {
        "title": "Blender non disponible",
        "impact": "Le modèle 3D généré est un fallback, pas un vrai GLB Blender.",
        "recommended_action": "Installez Blender 4.5+ pour obtenir un modèle 3D réel.",
    },
    "QA_FALLBACK_ARTIFACT_APPROVED": {
        "title": "QA a validé un artefact fallback",
        "impact": "Le contrôle qualité a accepté un artefact qui n'est pas un vrai rendu 3D.",
        "recommended_action": "Corrigez le pipeline QA ou installez Blender.",
    },
    "DEFAULT_SECTOR_COUNT_USED": {
        "title": "Nombre de secteurs par défaut",
        "impact": (
            "Le nombre de secteurs n'a pas été précisé ; une valeur par défaut a été utilisée."
        ),
        "recommended_action": "Précisez le nombre de secteurs dans le brief.",
    },
    "DEFAULT_TOWER_HEIGHT_USED": {
        "title": "Hauteur de pylône par défaut",
        "impact": (
            "La hauteur de pylône n'a pas été précisée ; une valeur par défaut a été utilisée."
        ),
        "recommended_action": "Précisez la hauteur de pylône dans le brief.",
    },
    "DEFAULT_AZIMUTHS_USED": {
        "title": "Azimuts par défaut",
        "impact": "Les azimuts n'ont pas été précisés ; une valeur par défaut a été utilisée.",
        "recommended_action": "Précisez les azimuts dans le brief.",
    },
    "DEFAULT_ANTENNA_HEIGHT_USED": {
        "title": "Hauteur d'antenne par défaut",
        "impact": "La hauteur d'installation des antennes n'a pas été précisée.",
        "recommended_action": "Précisez la hauteur d'antenne dans le brief.",
    },
}


def _warning_to_user_issue(item: dict) -> dict | None:
    code = item.get("code", "")
    message = item.get("message", "")
    severity = item.get("severity", "warning")
    mapping = _KNOWN_ISSUE_MAPPINGS.get(code)
    if mapping:
        return {
            "title": mapping["title"],
            "severity": severity,
            "impact": mapping["impact"],
            "recommended_action": mapping["recommended_action"],
            "technical_code": code,
        }
    # Generic fallback for unknown warnings
    return {
        "title": message.split(".")[0] if message else code,
        "severity": severity,
        "impact": message or "Un avertissement technique a été signalé.",
        "recommended_action": "Consultez le rapport technique pour plus de détails.",
        "technical_code": code,
    }


def _events_to_timeline(events: list[dict], status: dict) -> list[dict]:
    steps = []
    for event in events:
        event_type = event.get("event_type", "")
        human = _event_to_human(event_type, event.get("data", {}))
        steps.append(
            {
                "step": event_type,
                "status": _event_status(event_type, status.get("status", "unknown")),
                "timestamp": event.get("timestamp"),
                "human_readable": human,
            }
        )
    # Ensure terminal state is represented
    if not steps or steps[-1]["step"] not in {"workflow_completed", "workflow_failed"}:
        backend_status = status.get("status", "unknown")
        if backend_status == "completed":
            steps.append(
                {
                    "step": "workflow_completed",
                    "status": "completed",
                    "timestamp": None,
                    "human_readable": "Le workflow s'est terminé avec succès.",
                }
            )
        elif backend_status == "failed":
            steps.append(
                {
                    "step": "workflow_failed",
                    "status": "failed",
                    "timestamp": None,
                    "human_readable": "Le workflow a échoué.",
                }
            )
    return steps


def _event_status(event_type: str, workflow_status: str) -> str:
    terminal = {"workflow_completed": "completed", "workflow_failed": "failed"}
    if event_type in terminal:
        return terminal[event_type]
    if workflow_status in {"completed", "failed"}:
        return "completed"
    return "running"


def _event_to_human(event_type: str, data: dict) -> str:
    mapping: dict[str, str] = {
        "design_created": "Design créé",
        "blender_started": "Génération 3D démarrée",
        "validated_requirements_received": "Exigences validées reçues",
        "workflow_completed": "Workflow terminé",
        "workflow_failed": "Workflow en échec",
        "edit_patch_created": "Patch d'édition créé",
        "edit_patch_rejected": "Patch d'édition rejeté",
        "edit_patch_applied": "Patch d'édition appliqué",
        "version_created": "Nouvelle version créée",
        "version_rolled_back": "Version restaurée",
        "blender_completed": "Génération 3D terminée",
        "blender_failed": "Génération 3D en échec",
        "qa_completed": "Contrôle qualité terminé",
        "qa_failed": "Contrôle qualité en échec",
    }
    return mapping.get(event_type, event_type.replace("_", " ").capitalize())


def _studio_warnings(inventory: dict) -> list[dict]:
    warnings: list[dict] = []
    if inventory.get("blender_available") is False:
        warnings.append(
            {
                "title": "Blender non installé",
                "severity": "warning",
                "impact": (
                    "Aucun design ne produira de vrai GLB tant que Blender n'est pas installé."
                ),
                "recommended_action": "Installez Blender 4.5+ et redémarrez l'API.",
                "technical_code": "STUDIO_BLENDER_NOT_AVAILABLE",
            }
        )
    summaries = inventory.get("asset_summaries", [])
    if not any(s.get("glb_ready") for s in summaries):
        warnings.append(
            {
                "title": "Aucun asset GLB prêt",
                "severity": "error",
                "impact": "La génération 3D ne peut pas utiliser d'assets réels.",
                "recommended_action": (
                    "Vérifiez les manifests et les fichiers GLB sous assets/manifests."
                ),
                "technical_code": "STUDIO_NO_GLB_READY_ASSETS",
            }
        )
    return warnings
