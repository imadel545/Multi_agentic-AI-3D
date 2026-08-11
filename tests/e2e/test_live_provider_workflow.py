"""Explicit live-provider proofs for the telecom product path.

This module is excluded from every default gate. Individual probes consume the
configured providers; the complete product-flow probe also requires a qualified
local Blender runtime. A fallback is a test failure because this suite exists
specifically to prove live capability.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.config import settings
from apps.api.telecom_studio_api.main import (
    app,
    asset_selection_client,
    groq_client,
    groq_transport,
    workflow_service,
)
from core.contracts.planning_decision import (
    PlanningCandidate,
    PlanningCandidateProvenance,
    PlanningCurrentValues,
    PlanningDecisionRequest,
)

pytestmark = pytest.mark.provider_live


def test_live_groq_pool_validates_every_configured_account() -> None:
    configured_credentials = len(settings.resolved_groq_api_keys)
    assert configured_credentials >= 2, (
        "this live gate requires at least two explicitly authorized Groq accounts"
    )
    assert groq_client is not None
    assert groq_transport is not None

    for sequence in range(configured_credentials):
        result = groq_client.request_json(
            {
                "model": settings.resolved_groq_text_model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": "Return only the requested strict JSON object.",
                    },
                    {
                        "role": "user",
                        "content": f"Return ok=true and sequence={sequence}.",
                    },
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "GroqPoolCredentialProof",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "ok": {"type": "boolean"},
                                "sequence": {"type": "integer"},
                            },
                            "required": ["ok", "sequence"],
                        },
                    },
                },
            }
        )
        assert result == {"ok": True, "sequence": sequence}

    pool = groq_transport.credential_pool_status()
    assert pool["configured_credentials"] == configured_credentials
    assert pool["credentials_with_provider_response"] == configured_credentials
    assert pool["ready_credentials"] == configured_credentials
    assert pool["status"] == "operational"


def test_live_groq_bounded_asset_selection_contract_without_blender() -> None:
    assert asset_selection_client is not None, (
        "live provider gate requires the Groq asset-selection capability"
    )
    slots = [
        {
            "role_id": "tower",
            "candidates": [
                {
                    "asset_id": "LIVE_TOWER_EXACT",
                    "score": {"total_score": 91.0, "dimensional_score": 96.0},
                    "dimensions_m": {"width": 4.0, "depth": 4.0, "height": 30.0},
                    "allowed_generation_strategies": ["imported_glb_exact"],
                    "allowed_semantic_strategies": ["reuse_component"],
                },
                {
                    "asset_id": "LIVE_TOWER_PARAMETRIC",
                    "score": {"total_score": 88.0, "dimensional_score": 93.0},
                    "dimensions_m": {"width": 4.0, "depth": 4.0, "height": 30.0},
                    "allowed_generation_strategies": ["internal_project_generated"],
                    "allowed_semantic_strategies": ["compose_assets"],
                },
            ],
        }
    ]

    selections, diagnostics = asset_selection_client.decide(slots=slots)

    assert diagnostics["provider"] == "groq"
    assert "fallback_reason" not in diagnostics, diagnostics
    assert selections.keys() == {"tower"}
    selected_asset = selections["tower"]
    selected_tuple = (
        selected_asset,
        diagnostics["generation_strategies"]["tower"],
        diagnostics["semantic_strategies"]["tower"],
    )
    assert selected_tuple in {
        ("LIVE_TOWER_EXACT", "imported_glb_exact", "reuse_component"),
        (
            "LIVE_TOWER_PARAMETRIC",
            "internal_project_generated",
            "compose_assets",
        ),
    }


def test_live_groq_nvidia_blender_product_flow(tmp_path: Path) -> None:
    assert settings.resolved_groq_api_key, "live provider gate requires a Groq credential"
    assert settings.resolved_nvidia_api_key, "live provider gate requires an NVIDIA credential"
    assert settings.embedding_provider == "nvidia"
    assert settings.reranker_provider == "nvidia"

    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        result = workflow_service.create_design(
            requirements_text=(
                "Concevoir un site radio 5G sur pylône treillis de 30 m, avec trois secteurs "
                "installés à 24 m aux azimuts 0, 120 et 240 degrés. Ajouter une RRU et un "
                "câble par secteur, une armoire d'énergie au sol, une antenne GPS et les "
                "étiquettes techniques. Produire les vues de contrôle et conserver la "
                "provenance de chaque décision."
            ),
            detail_level="high",
            use_llm=True,
            _synchronous=True,
        )
        workflow_id = result["workflow_id"]
        status = client.get(f"/designs/{workflow_id}").json()

        assert status["status"] == "completed", json.dumps(status.get("errors", []))
        assert status["generation_mode"] == "real_blender"
        assert status["completion_certificate_status"] == "issued"
        assert status["llm_provider"].startswith("groq:")
        assert status["extraction_provider"] == "groq"
        assert status["llm_fallback_used"] is False
        assert status["llm_fallback_reason"] is None
        assert status["rag_reranker_provider"] == "nvidia"
        assert status["rag_reranker_status"] == "primary_nvidia_reranker"
        assert status["rag_reranker_degraded_reason"] is None

        extraction = client.get(f"/designs/{workflow_id}/artifacts/extraction_report").json()
        assert extraction["mode"] == "structured_llm"
        assert extraction["validated_schema"] is True
        assert extraction["provider"].startswith("groq:")

        planning = client.get(f"/designs/{workflow_id}/artifacts/planning_decision").json()
        assert planning["status"] == "not_needed"
        assert planning["reason"] == "no_eligible_inferred_candidates"
        assert planning["provider"] is None
        assert planning["fallback_used"] is False

        rag = client.get(f"/designs/{workflow_id}/artifacts/rag_evidence").json()
        assert rag["rag_context_count"] > 0
        assert rag["rag_reranker_provider"] == "nvidia"
        assert rag["rag_reranker_status"] == "primary_nvidia_reranker"
        assert rag["rag_reranker_degraded_reason"] is None

        bundle = client.get(f"/designs/{workflow_id}/viewer-bundle").json()
        assert bundle["primary_glb_url"]
        assert bundle["preview_url"]
        assert bundle["mesh_qa_passed"] is True
        assert bundle["human_errors_count"] == 0
        assert bundle["asset_decision_summary"]["decision_authority"] == "llm_bounded"
        assert bundle["asset_decision_summary"]["fallback_used"] is False
    finally:
        workflow_service.outputs_dir = original_outputs


def test_live_groq_bounded_planning_decision_contract() -> None:
    client = workflow_service.orchestrator.planning_decision_client
    assert client is not None, "live provider gate requires the Groq planning capability"
    request = PlanningDecisionRequest(
        current_values=PlanningCurrentValues(
            antenna_install_height_m=24.0,
            beamwidth_deg=65.0,
            mechanical_tilt_deg=3.0,
            electrical_tilt_deg=0.0,
            include_cables=True,
            include_sector_beams=True,
        ),
        protected_fields=[
            "beamwidth_deg",
            "mechanical_tilt_deg",
            "electrical_tilt_deg",
            "include_cables",
            "include_sector_beams",
        ],
        candidates=[
            PlanningCandidate(
                candidate_id="rag:hba:live:1",
                field="antenna_install_height_m",
                value=25.0,
                provenance=PlanningCandidateProvenance(
                    source="rag",
                    reference_id="live-provider-contract",
                    rank=1,
                    score=0.93,
                    collection="telecom_rules",
                    document_name="live_provider_gate",
                    excerpt="Candidate validé pour vérifier le contrat borné du provider.",
                ),
            )
        ],
    )

    result = client.decide(request)

    assert result.diagnostics.provider == "groq"
    assert result.diagnostics.status == "primary"
    assert result.diagnostics.fallback_used is False
    assert result.diagnostics.fallback_reason is None
    assert len(result.selections) == 6
    assert {selection.field for selection in result.selections} == set(
        PlanningCurrentValues.model_fields
    )
