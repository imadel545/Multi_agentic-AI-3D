import hashlib
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from apps.api.telecom_studio_api.models import EditDesignRequest
from core.agents.scene_edit_agent import SceneEditAgent
from core.services.targeted_edit import resolve_proof_scope, resolve_targeted_edit
from tests.unit.test_adaptation_capabilities import _scene, _services


def _fixture():
    scene = _scene(radio=True)
    scene.sectors.append(
        scene.sectors[0].model_copy(update={"sector_id": "S2", "azimuth_deg": 120})
    )
    _, service = _services()
    proofs = {
        "components": [
            {
                "asset_id": scene.sectors[1].antenna_asset_id,
                "qa": {"passed": True},
                "instances": [
                    {
                        "semantic_root": "antenna_S2",
                        "instance_id": "S2",
                        "object_role": "antenna",
                        "qa": {"passed": True},
                    }
                ],
            }
        ]
    }
    return scene, service, proofs


@pytest.mark.parametrize(
    "prompt,path,value",
    [
        ("Azimut à 80 degrés", "azimuth_deg", 80),
        ("Hauteur à 22 m", "install_height_m", 22),
        ("Inclinaison mécanique à 6 degrés", "mechanical_tilt_deg", 6),
    ],
)
def test_targeted_fallback_changes_only_selected_sector(prompt, path, value):
    scene, service, proofs = _fixture()
    before = scene.model_dump(mode="json")
    paths, context = resolve_proof_scope(scene, proofs, "antenna_S2", service)
    decision = SceneEditAgent(capability_service=service).create_adaptation(
        "wf_scope",
        scene,
        f"{prompt} (Sélection active : {context})",
        allowed_paths=paths,
    )
    assert decision.patch.edit_llm_fallback_used
    assert decision.patched_scene.sectors[0] == scene.sectors[0]
    assert getattr(decision.patched_scene.sectors[1], path) == value
    expected = dict(before)
    expected["sectors"] = [dict(sector) for sector in before["sectors"]]
    expected["sectors"][1][path] = value
    assert decision.patched_scene.model_dump(mode="json") == expected
    assert all(cap.path in paths for cap in decision.capabilities.capabilities)


def test_targeted_fallback_rejects_outside_scope():
    scene, service, proofs = _fixture()
    paths, _ = resolve_proof_scope(scene, proofs, "antenna_S2", service)
    with pytest.raises(ValueError, match="undeclared capability"):
        SceneEditAgent(capability_service=service).create_adaptation(
            "wf_scope",
            scene,
            "Hauteur du pylône à 35 m",
            allowed_paths=paths,
        )


@pytest.mark.parametrize("change", ["unknown", "ambiguous", "failed"])
def test_untrusted_or_ambiguous_selection_rejected(change):
    scene, service, proofs = _fixture()
    if change == "ambiguous":
        proofs["components"] *= 2
    if change == "failed":
        proofs["components"][0]["qa"]["passed"] = False
    with pytest.raises(ValueError):
        resolve_proof_scope(
            scene, proofs, "unknown" if change == "unknown" else "antenna_S2", service
        )


def test_stale_and_tampered_evidence_rejected(tmp_path):
    scene, service, proofs = _fixture()
    version = SimpleNamespace(version_id="v12345678", scene=scene, artifact_dir=str(tmp_path))
    raw = json.dumps(proofs).encode()
    (tmp_path / "component_proofs.json").write_bytes(raw)
    (tmp_path / "completion_certificate.json").write_text(
        json.dumps(
            {
                "status": "issued",
                "artifacts": [
                    {"logical_name": "component_proofs", "sha256": hashlib.sha256(raw).hexdigest()}
                ],
            }
        )
    )
    assert resolve_targeted_edit(version, "antenna_S2", version.version_id, service)[0]
    with pytest.raises(ValueError, match="design a changé"):
        resolve_targeted_edit(version, "antenna_S2", "v87654321", service)
    (tmp_path / "component_proofs.json").write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="certifiées"):
        resolve_targeted_edit(version, "antenna_S2", version.version_id, service)


def test_target_requires_version_and_legacy_request_unchanged():
    assert EditDesignRequest(edit_prompt="Tour à 35 m").target_semantic_root is None
    for payload in ({"target_semantic_root": "antenna_S2"}, {"expected_version_id": "v12345678"}):
        with pytest.raises(ValidationError):
            EditDesignRequest(edit_prompt="Azimut à 80", **payload)


def test_workflow_independent_boundary_rejects_agent_escape(monkeypatch):
    from apps.api.telecom_studio_api.workflow import WorkflowService
    from core.contracts.scene_edit import PatchOperation, ScenePatch
    from core.services.patch_applier import PatchApplier

    scene, capabilities, _ = _fixture()
    patch = ScenePatch(
        edit_description="escape",
        operations=[
            PatchOperation(op="replace", path="/tower/height_m", value=35),
        ],
    )
    patched, report = PatchApplier().apply(scene, patch)
    service = object.__new__(WorkflowService)
    service._sync_output_services = lambda: None
    service.get_status = lambda _: {}
    service._emit_workflow_event = lambda *args: None
    service.versioning = SimpleNamespace(
        get_verified_active_version=lambda _: SimpleNamespace(
            scene=scene,
            version_id="v12345678",
        )
    )
    service.scene_edit_agent = SimpleNamespace(
        capability_service=capabilities,
        create_adaptation=lambda *args, **kwargs: SimpleNamespace(
            patch=patch,
            patched_scene=patched,
            validation_report=report,
        ),
    )
    monkeypatch.setattr(
        "apps.api.telecom_studio_api.workflow.resolve_targeted_edit",
        lambda *args: ({"/sectors/1/azimuth_deg"}, "antenne secteur 2"),
    )
    result = service._edit_design(
        "wf_scope",
        "Azimut à 80",
        target_semantic_root="antenna_S2",
        expected_version_id="v12345678",
    )
    assert result.status == "failed"
    assert "dépasse" in result.errors[0].message
    assert scene.tower.height_m == 30


def test_measurement_angle_uses_normalized_vectors_without_relaxing_tolerance():
    import math

    from core.contracts.assembly_evidence import _angle_deg as contract_angle
    from core.qa.assembly_constraint_inspector import _angle_deg as measured_angle

    direction = (math.sin(math.radians(80)), math.cos(math.radians(80)), 0.0)
    residual = tuple(value * (1 - 1e-15) for value in direction)
    assert contract_angle(residual, direction) == measured_angle(residual, direction)
    tilted = (math.sin(math.radians(82)), math.cos(math.radians(82)), 0.0)
    assert contract_angle(residual, tilted) == pytest.approx(2.0)
