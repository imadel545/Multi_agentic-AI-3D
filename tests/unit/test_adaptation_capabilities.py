from pathlib import Path

import pytest

from core.agents.scene_edit_agent import SceneEditAgent
from core.contracts.adaptation import AdaptationOperation, AssetAdaptationPlan
from core.contracts.scene import (
    SceneAccessoryPlacement,
    SceneAssetPlacement,
    SceneSpec,
    SectorSpec,
    VisualElements,
)
from core.orchestration.langgraph_orchestrator import _scene_with_revision_dependencies
from core.services.adaptation_capabilities import AdaptationCapabilityService
from core.services.asset_registry import AssetRegistry

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _services() -> tuple[AssetRegistry, AdaptationCapabilityService]:
    registry = AssetRegistry(PROJECT_ROOT / "assets/manifests")
    return registry, AdaptationCapabilityService(PROJECT_ROOT, registry)


def _scene(*, accessory: bool = False, tower_strategy: str = "parametric_generated") -> SceneSpec:
    accessories = []
    visuals = VisualElements()
    if accessory:
        visuals = VisualElements(include_gps_antenna=True)
        accessories = [
            SceneAccessoryPlacement(
                asset_id="GPS_ANTENNA_001",
                asset_type="gps",
                dimensions_m={"width": 0.32, "depth": 0.32, "height": 0.22},
                position=[0.0, 0.8, 29.5],
                rotation_deg=[0.0, 0.0, 0.0],
                scale=[1.0, 1.0, 1.0],
            )
        ]
    return SceneSpec(
        scene_id="wf_adaptation",
        network_type="5G",
        tower=SceneAssetPlacement(
            asset_id="TOWER_LATTICE_30M",
            position=[0.0, 0.0, 0.0],
            rotation_deg=[0.0, 0.0, 0.0],
            height_m=30.0,
            generation_strategy=tower_strategy,
        ),
        sectors=[
            SectorSpec(
                sector_id="S1",
                antenna_asset_id="ANT_PANEL_5G_001",
                install_height_m=24.0,
                azimuth_deg=0.0,
                beamwidth_deg=65.0,
            )
        ],
        visual_elements=visuals,
        accessory_assets=accessories,
    )


def test_capabilities_are_resolved_from_manifest_profiles() -> None:
    registry, service = _services()
    capabilities = service.resolve(_scene(accessory=True))
    paths = capabilities.allowed_paths

    assert "/tower/height_m" in paths
    assert "/sectors/0/azimuth_deg" in paths
    assert "/accessory_assets/0/scale" in paths
    assert "/visual_elements/include_sector_beams" in paths
    assert "/tower/characteristics/vendor_secret" not in paths
    assert not capabilities.missing_profiles
    assert all(asset.adaptation_profile_id for asset in registry.list_assets())


def test_non_parametric_tower_does_not_claim_geometry_editing() -> None:
    _, service = _services()
    capabilities = service.resolve(_scene(tower_strategy="imported_glb_exact"))

    assert "/tower/height_m" not in capabilities.allowed_paths
    assert any("GLB non paramétrique" in item for item in capabilities.unsupported_operations)


def test_plan_validator_rejects_wrong_tool_and_unknown_capability() -> None:
    _, service = _services()
    capabilities = service.resolve(_scene())
    invalid = AssetAdaptationPlan(
        edit_description="invalid",
        operations=[
            AdaptationOperation(
                capability_id="scene:tower_height",
                path="/tower/height_m",
                value=40,
                execution_tool="scene_visibility",
                rationale="wrong tool",
            )
        ],
    )

    with pytest.raises(ValueError, match="requires parametric_rebuild"):
        service.validate_plan(capabilities, invalid)


def test_langgraph_adaptation_uses_strict_groq_schema_and_executes_scene_spec() -> None:
    class RecordingGroq:
        model = "openai/gpt-oss-120b"

        def __init__(self) -> None:
            self.payload = None

        def _post_raw(self, payload):
            self.payload = payload
            return {
                "edit_description": "Passer le pylône à 40 m",
                "operations": [
                    {
                        "op": "replace",
                        "capability_id": "scene:tower_height",
                        "path": "/tower/height_m",
                        "value": 40,
                        "execution_tool": "parametric_rebuild",
                        "rationale": "La demande fixe explicitement 40 m.",
                    }
                ],
                "unsupported_requests": [],
                "assumptions": [],
            }

    _, service = _services()
    groq = RecordingGroq()
    agent = SceneEditAgent(groq_client=groq, capability_service=service)  # type: ignore[arg-type]
    decision = agent.create_adaptation("wf_adaptation", _scene(), "mets la tour à 40 m")

    assert decision.patched_scene.tower.height_m == 40
    assert decision.planner_fallback_used is False
    assert [item["node"] for item in decision.graph_trace] == [
        "discover_capabilities",
        "plan_adaptation",
        "validate_adaptation",
        "execute_adaptation",
    ]
    response_format = groq.payload["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    path_schema = response_format["json_schema"]["schema"]["properties"]["operations"]["items"][
        "properties"
    ]["path"]
    assert "/tower/height_m" in path_schema["enum"]
    operation_properties = response_format["json_schema"]["schema"]["properties"]["operations"][
        "items"
    ]["properties"]
    assert "value_json" in operation_properties
    assert "value" not in operation_properties


def test_invalid_llm_plan_falls_back_before_scene_mutation() -> None:
    class InvalidGroq:
        model = "openai/gpt-oss-120b"

        def _post_raw(self, _payload):
            return {
                "edit_description": "unsafe",
                "operations": [
                    {
                        "op": "replace",
                        "capability_id": "scene:tower_height",
                        "path": "/visual_elements/include_labels",
                        "value": 99,
                        "execution_tool": "parametric_rebuild",
                        "rationale": "invented",
                    }
                ],
                "unsupported_requests": [],
                "assumptions": [],
            }

    _, service = _services()
    agent = SceneEditAgent(
        groq_client=InvalidGroq(),  # type: ignore[arg-type]
        capability_service=service,
    )
    decision = agent.create_adaptation("wf_adaptation", _scene(), "mets la tour à 40 m")

    assert decision.patched_scene.tower.height_m == 40
    assert decision.planner_fallback_used is True
    assert decision.planner_fallback_reason == "groq_edit_failed:ValueError"


def test_accessory_vector_transform_is_bounded_and_applied() -> None:
    class AccessoryGroq:
        model = "openai/gpt-oss-120b"

        def _post_raw(self, _payload):
            return {
                "edit_description": "Agrandir le GPS",
                "operations": [
                    {
                        "op": "replace",
                        "capability_id": "accessory_1:accessory_scale",
                        "path": "/accessory_assets/0/scale",
                        "value": [1.5, 1.5, 1.5],
                        "execution_tool": "asset_transform",
                        "rationale": "Échelle explicite de 1.5 sur XYZ.",
                    }
                ],
                "unsupported_requests": [],
                "assumptions": [],
            }

    _, service = _services()
    agent = SceneEditAgent(
        groq_client=AccessoryGroq(),  # type: ignore[arg-type]
        capability_service=service,
    )
    decision = agent.create_adaptation(
        "wf_adaptation",
        _scene(accessory=True),
        "change la taille GPS avec une échelle 1.5, 1.5, 1.5",
    )

    assert decision.patched_scene.accessory_assets[0].scale == [1.5, 1.5, 1.5]
    assert decision.patch.adaptation_tools == ["asset_transform"]


def test_bounded_fallback_applies_explicit_gps_scale_without_toggling_visibility() -> None:
    _, service = _services()
    agent = SceneEditAgent(groq_client=None, capability_service=service)

    decision = agent.create_adaptation(
        "wf_adaptation",
        _scene(accessory=True),
        "change la taille GPS avec une échelle 1.2, 1.2, 1.2",
    )

    assert [operation.path for operation in decision.patch.operations] == [
        "/accessory_assets/0/scale"
    ]
    assert decision.patched_scene.accessory_assets[0].scale == [1.2, 1.2, 1.2]


def test_revision_dependency_rebind_preserves_scale_and_follows_tower_height() -> None:
    registry, _ = _services()
    original = _scene(accessory=True)
    gps = original.accessory_assets[0].model_copy(update={"scale": [1.2, 1.2, 1.2]})
    raised = original.model_copy(
        update={
            "tower": original.tower.model_copy(update={"height_m": 34.0}),
            "accessory_assets": [gps],
        }
    )

    rebound = _scene_with_revision_dependencies(raised, registry)

    assert rebound.accessory_assets[0].scale == [1.2, 1.2, 1.2]
    assert rebound.accessory_assets[0].position[2] == 33.5


def test_user_defined_accessory_position_survives_dependency_rebind() -> None:
    registry, _ = _services()
    original = _scene(accessory=True)
    gps = original.accessory_assets[0].model_copy(
        update={"position": [2.0, 3.0, 4.0], "placement_policy": "user_defined"}
    )
    moved = original.model_copy(update={"accessory_assets": [gps]})

    rebound = _scene_with_revision_dependencies(moved, registry)

    assert rebound.accessory_assets[0].position == [2.0, 3.0, 4.0]
    assert rebound.accessory_assets[0].placement_policy == "user_defined"
