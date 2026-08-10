from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.telecom_studio_api.main import app, registry, settings
from apps.api.telecom_studio_api.models import DesignOptions
from apps.api.telecom_studio_api.product import (
    _asset_decision_summary_from_path,
    _visual_review_summary,
)
from apps.api.telecom_studio_api.runtime_contract import (
    configure_multimodal_intelligence,
    runtime_capabilities,
)
from core.contracts.assets import AssetPreview
from core.contracts.requirements import (
    RequirementCandidateEvidence,
    RequirementFieldEvidence,
)


def test_multimodal_consent_is_disabled_by_default_and_strictly_typed() -> None:
    assert DesignOptions().multimodal_consent == "disabled"
    assert (
        DesignOptions(multimodal_consent="allow_input_analysis").multimodal_consent
        == "allow_input_analysis"
    )
    with pytest.raises(ValidationError):
        DesignOptions(multimodal_consent="always_send_images")


def test_runtime_vision_health_requires_validated_capabilities() -> None:
    configure_multimodal_intelligence(
        enabled=True,
        key_configured=True,
        max_images_per_request=3,
        max_image_bytes=20_000_000,
        health_provider=lambda: {
            "multimodal_interpretation": {"status": "operational"},
            "asset_visual_review": {"status": "configured_unverified"},
        },
    )
    try:
        capability = runtime_capabilities()["multimodal_intelligence"]
        assert capability["status"] == "configured_unverified"
        assert capability["enabled"] is True
        assert capability["max_image_bytes"] == 20_000_000
    finally:
        configure_multimodal_intelligence(
            enabled=False,
            key_configured=False,
            max_images_per_request=3,
            max_image_bytes=20_000_000,
            health_provider=None,
        )


def test_vision_only_requirement_evidence_stays_inferred() -> None:
    candidate = RequirementCandidateEvidence(
        value="panel antenna",
        source="vision",
        mechanism="bounded_visual_observation",
        confidence=0.82,
        visual_source_id="image_1",
        visual_input_sha256="a" * 64,
        selected=True,
    )
    evidence = RequirementFieldEvidence(
        field="antenna_type",
        selected_value="panel antenna",
        selected_source="vision",
        confidence=0.82,
        explicit=False,
        defaulted=False,
        candidates=[candidate],
        requires_confirmation=True,
        rationale="Observed in a supplied raster; user confirmation remains required.",
    )

    assert evidence.requires_confirmation is True
    with pytest.raises(ValidationError, match="remain inferred"):
        RequirementFieldEvidence.model_validate({**evidence.model_dump(), "explicit": True})


def test_public_asset_decision_and_visual_review_shapes_match_frontend(
    tmp_path: Path,
) -> None:
    assembly_path = tmp_path / "assembly_plan.json"
    assembly_path.write_text(
        json.dumps(
            {
                "selection_authority": "llm_bounded",
                "llm_fallback_used": False,
                "components": [
                    {
                        "role_id": "sector_antenna",
                        "selected_asset_id": "ANT_REAL",
                        "generation_strategy": "imported_glb_exact",
                        "semantic_strategy": "reuse_component",
                        "selection_reason": "Best compatible bounded candidate.",
                        "selection_risks": [
                            "Professional asset QA has not passed.",
                            "Five QA-passed qualification previews are not published.",
                        ],
                        "candidate_scores": [{"asset_id": "ANT_REAL"}, {"asset_id": "ANT_ALT"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    decision = _asset_decision_summary_from_path(assembly_path)
    review = _visual_review_summary({}, {"status": "configured_unverified"})

    assert decision is not None
    assert decision["components"][0]["strategy"] == "reuse_component"
    assert decision["components"][0]["considered_count"] == 2
    assert decision["components"][0]["rejected_count"] == 1
    assert decision["components"][0]["risks"] == [
        "Professional asset QA has not passed.",
        "Five QA-passed qualification previews are not published.",
    ]
    assert review["status"] == "not_requested"
    assert review["advisory_only"] is True


def test_asset_inventory_exposes_only_public_preview_and_provenance_urls() -> None:
    client = TestClient(app)
    inventory = client.get("/assets/inventory")
    assert inventory.status_code == 200
    entries = inventory.json()["entries"]
    assert entries
    assert sum(bool(item["milestone_evidence_eligible"]) for item in entries) == 0
    for item in entries:
        assert item["provenance_url"] == f"/assets/{item['asset_id']}/provenance"
        assert not any("/Users/" in preview["url"] for preview in item["preview_set"])

    provenance = client.get(f"/assets/{entries[0]['asset_id']}/provenance")
    assert provenance.status_code == 200
    assert "/Users/" not in provenance.text
    assert "file" not in {
        key for representation in provenance.json()["representations"] for key in representation
    }


def test_asset_preview_endpoint_verifies_the_published_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preview_path = tmp_path / "qualified" / "front.png"
    preview_path.parent.mkdir(parents=True)
    content = b"bounded-preview-fixture"
    preview_path.write_bytes(content)
    preview = AssetPreview(
        view="front",
        file="qualified/front.png",
        sha256=hashlib.sha256(content).hexdigest(),
        width_px=128,
        height_px=128,
        qa_status="passed",
    )
    asset = registry.get("ANT_PANEL_4G_001").model_copy(update={"preview_set": [preview]})
    monkeypatch.setattr(registry, "get", lambda asset_id: asset)
    monkeypatch.setattr(settings, "project_root", tmp_path)

    client = TestClient(app)
    published = client.get(f"/assets/{asset.asset_id}/previews/front")
    assert published.status_code == 200
    assert published.content == content

    preview_path.write_bytes(b"tampered-preview")
    rejected = client.get(f"/assets/{asset.asset_id}/previews/front")
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "asset preview integrity check failed"
