"""Tests for product-oriented API endpoints."""

import json
import subprocess
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.telecom_studio_api.main import app, workflow_service
from apps.api.telecom_studio_api.product import (
    ProductService,
    _assembly_constraint_summary_from_path,
    _asset_quality_summary,
    _blender_available,
    _events_to_timeline,
    _geometry_fidelity_summary,
    _geometry_program_summary_from_path,
    _inventory_status,
    _probe_blender_runtime,
    _studio_warnings,
)
from apps.api.telecom_studio_api.runtime_contract import memory_status
from apps.api.telecom_studio_api.workflow import _rag_runtime_summary
from core.contracts.assembly_evidence import canonical_evidence_sha256
from core.contracts.scene import SceneAssetPlacement, SceneSpec, SectorSpec, VisualElements
from core.contracts.versioning import SceneVersion
from core.services import scene_versioning


def test_blender_availability_requires_successful_headless_smoke(
    tmp_path: Path, monkeypatch
) -> None:
    binary = tmp_path / "blender"
    binary.write_text("binary", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr(
        "apps.api.telecom_studio_api.product._resolve_blender_binary",
        lambda _configured: binary,
    )
    monkeypatch.setattr(
        "apps.api.telecom_studio_api.product._run_blender_probe",
        lambda command: subprocess.CompletedProcess(
            args=command,
            returncode=-11,
            stdout="Blender 4.5.12 LTS",
            stderr="Arch_ValidateAssumptions",
        ),
    )
    _probe_blender_runtime.cache_clear()

    assert _blender_available() is False


def test_blender_availability_rejects_a_successful_unqualified_runtime(
    tmp_path: Path, monkeypatch
) -> None:
    binary = tmp_path / "blender"
    binary.write_text("binary", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr(
        "apps.api.telecom_studio_api.product._resolve_blender_binary",
        lambda _configured: binary,
    )
    monkeypatch.setattr(
        "apps.api.telecom_studio_api.product._run_blender_probe",
        lambda command: subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="Blender 5.1.2\nTELECOM_STUDIO_BLENDER_READY",
            stderr="",
        ),
    )
    _probe_blender_runtime.cache_clear()

    assert _blender_available() is False


def test_constraint_summary_is_derived_from_valid_hashed_evidence(tmp_path: Path) -> None:
    evidence_path = tmp_path / "constraint_evidence.json"
    payload = _constraint_evidence_payload()
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    summary = _assembly_constraint_summary_from_path(evidence_path)

    assert summary == {
        "status": "passed",
        "measurement_scope": "exported_glb_anchor_frames",
        "required_connection_count": 1,
        "measured_instance_count": 1,
        "resolved_support_count": 0,
        "max_position_error_m": 0.004,
        "max_angular_error_deg": 0.0,
        "limitations": ["limit one", "limit two", "limit three"],
    }


def test_constraint_summary_rejects_tampered_evidence(tmp_path: Path) -> None:
    evidence_path = tmp_path / "constraint_evidence.json"
    payload = _constraint_evidence_payload()
    payload["measurements"][0]["position_error_m"] = 0.005
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    assert _assembly_constraint_summary_from_path(evidence_path) is None


def test_rag_runtime_summary_prefers_durable_result_diagnostics_across_threads() -> None:
    class Probe:
        _reranker = type(
            "Reranker",
            (),
            {
                "provider": "nvidia",
                "model_name": "nvidia/test",
                "status": "configured_unverified",
                "degraded_reason": None,
            },
        )()
        last_retrieval_diagnostics = type(
            "Retrieval",
            (),
            {"status": "primary_vector_cache", "degraded_reason": None},
        )()
        last_rerank_diagnostics = type(
            "Rerank",
            (),
            {"status": "degraded_passthrough", "degraded_reason": "stale_failure"},
        )()

    summary = _rag_runtime_summary(
        Probe(),
        rag_context=[
            {
                "payload": {
                    "retrieval_mode": "degraded_local_lexical",
                    "retrieval_degraded_reason": "embedding_timeout",
                    "reranker_status": "primary_nvidia_reranker",
                    "reranker_degraded_reason": None,
                }
            }
        ],
    )

    assert summary["rag_retrieval_status"] == "degraded_local_lexical"
    assert summary["rag_retrieval_degraded_reason"] == "embedding_timeout"
    assert summary["rag_reranker_status"] == "primary_nvidia_reranker"
    assert summary["rag_reranker_degraded_reason"] is None


def test_nonassembly_version_never_publishes_parasitic_constraint_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_id = "wf_123456789abc"
    version_id = "v00000001"
    artifact_dir = tmp_path / workflow_id / "versions" / version_id
    artifact_dir.mkdir(parents=True)
    evidence_path = artifact_dir / "constraint_evidence.json"
    evidence_path.write_text(json.dumps(_constraint_evidence_payload()), encoding="utf-8")
    scene = SceneSpec(
        scene_id=workflow_id,
        network_type="5G",
        tower=SceneAssetPlacement(
            asset_id="tower_01",
            position=[0, 0, 0],
            rotation_deg=[0, 0, 0],
            height_m=30,
        ),
        sectors=[
            SectorSpec(
                sector_id="S1",
                antenna_asset_id="ant_01",
                install_height_m=24,
                azimuth_deg=0,
                mechanical_tilt_deg=3,
                beamwidth_deg=65,
            )
        ],
        visual_elements=VisualElements(),
    )
    version = SceneVersion(
        version_id=version_id,
        workflow_id=workflow_id,
        scene=scene,
        created_at="2026-08-11T00:00:00Z",
        status="completed",
        artifact_dir=str(artifact_dir),
    )
    snapshot = workflow_service._viewer_snapshot_from_verified_version(version, artifact_dir)
    assert "constraint_evidence" not in snapshot.artifact_paths

    status = {
        "workflow_id": workflow_id,
        "status": "completed",
        "active_version_id": version_id,
        "completion_certificate_status": "issued",
        "warnings": [],
        "errors": [],
    }
    monkeypatch.setattr(
        workflow_service,
        "get_viewer_status_snapshot",
        lambda requested: (status, snapshot) if requested == workflow_id else (status, None),
    )
    monkeypatch.setattr(workflow_service, "get_events", lambda _workflow_id: [])
    bundle = ProductService(workflow_service, None).viewer_bundle(workflow_id)  # type: ignore[arg-type]
    assert bundle["constraint_evidence_url"] is None
    assert bundle["assembly_constraint_summary"] is None
    artifact = next(
        item for item in bundle["viewer_artifacts"] if item["name"] == "constraint_evidence.json"
    )
    assert artifact["available"] is False

    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    workflow_service._sync_output_services()
    try:
        monkeypatch.setattr(workflow_service.versioning, "get_version", lambda *_args: version)
        monkeypatch.setattr(
            workflow_service,
            "_verified_version_artifact_dir",
            lambda *_args: (version, artifact_dir),
        )
        with pytest.raises(KeyError):
            workflow_service.artifact_path(
                workflow_id,
                "constraint_evidence",
                version_id=version_id,
            )
        response = TestClient(app).get(
            f"/designs/{workflow_id}/artifacts/constraint_evidence?version_id={version_id}"
        )
        assert response.status_code == 404
        archive_path = workflow_service.artifact_path(
            workflow_id,
            "download",
            version_id=version_id,
        )
        with zipfile.ZipFile(archive_path) as archive:
            assert "constraint_evidence.json" not in archive.namelist()
    finally:
        workflow_service.outputs_dir = original_outputs
        workflow_service._sync_output_services()


def test_blender_availability_accepts_verified_headless_smoke(tmp_path: Path, monkeypatch) -> None:
    binary = tmp_path / "blender"
    binary.write_text("binary", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr(
        "apps.api.telecom_studio_api.product._resolve_blender_binary",
        lambda _configured: binary,
    )
    monkeypatch.setattr(
        "apps.api.telecom_studio_api.product._run_blender_probe",
        lambda command: subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="Blender 4.5.12 LTS\nTELECOM_STUDIO_BLENDER_READY",
            stderr="",
        ),
    )
    _probe_blender_runtime.cache_clear()

    assert _blender_available() is True


def test_blender_availability_accepts_native_banner_written_to_stderr(
    tmp_path: Path, monkeypatch
) -> None:
    """Match the qualified macOS runtime's real stdout/stderr split."""

    binary = tmp_path / "blender"
    binary.write_text("binary", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr(
        "apps.api.telecom_studio_api.product._resolve_blender_binary",
        lambda _configured: binary,
    )
    monkeypatch.setattr(
        "apps.api.telecom_studio_api.product._run_blender_probe",
        lambda command: subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="TELECOM_STUDIO_BLENDER_READY\n",
            stderr="Blender 4.5.12 LTS (hash verified)\n",
        ),
    )
    _probe_blender_runtime.cache_clear()

    assert _blender_available() is True


def test_blender_availability_accepts_banner_after_controlled_marker(
    tmp_path: Path, monkeypatch
) -> None:
    """The real 4.5.12 macOS process emits the marker before its banner."""

    binary = tmp_path / "blender"
    binary.write_text("binary", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr(
        "apps.api.telecom_studio_api.product._resolve_blender_binary",
        lambda _configured: binary,
    )
    monkeypatch.setattr(
        "apps.api.telecom_studio_api.product._run_blender_probe",
        lambda command: subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="TELECOM_STUDIO_BLENDER_READY\nBlender 4.5.12 LTS (hash verified)\n",
            stderr="",
        ),
    )
    _probe_blender_runtime.cache_clear()

    assert _blender_available() is True


@pytest.mark.blender_runtime
def test_studio_summary_returns_design_counts(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=(
                "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
                "Azimuts : 0°, 120°, 240°."
            ),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        assert response["status"] == "completed"

        summary = client.get("/studio/summary").json()
        assert summary["total_designs"] >= 1
        assert summary["completed_designs"] >= 1
        assert "asset_inventory_status" in summary
        assert summary["asset_inventory_status"] == "qualified_mixed_catalog"
        inventory = client.get("/assets/inventory").json()
        for field in (
            "asset_count",
            "real_glb_asset_count",
            "import_qualified_glb_count",
            "generation_eligible_asset_count",
            "reference_only_asset_count",
            "missing_file_count",
        ):
            assert summary[field] == inventory[field]
        assert summary["asset_count"] == len(inventory["entries"])
        assert summary["generation_eligible_asset_count"] == sum(
            entry["generation_eligible"] for entry in inventory["entries"]
        )
        assert summary["reference_only_asset_count"] == sum(
            entry["asset_import_mode"] == "reference_only" for entry in inventory["entries"]
        )
        assert not any(
            warning.get("technical_code") == "STUDIO_NO_QUALIFIED_ASSETS"
            for warning in summary["warnings"]
        )
        assert "blender_available" in summary
        assert isinstance(summary["llm_available"], bool)
        assert summary["rag_embedding_provider"]
        assert summary["rag_status"] in {
            "primary_nvidia_embedding",
            "configured_unverified",
            "configured_but_last_operation_failed",
            "deterministic_hash_fallback",
            "custom_provider",
        }
        assert isinstance(summary["rag_degraded"], bool)
        assert summary["rag_reranker_status"] in {
            "passthrough_no_rerank",
            "primary_nvidia_reranker",
            "degraded_passthrough",
            "configured_unverified",
            "not_loaded",
            "custom",
        }
        assert summary["rag_reranker_provider"] in {
            "nvidia",
            "passthrough",
            "disabled",
            None,
        }
        assert "rag_reranker_model" in summary
        assert "rag_reranker_degraded_reason" in summary
        assert summary["rag_operational_status"] in {
            "unverified",
            "operational",
            "failed",
        }
        assert "rag_last_operation" in summary
        assert summary["rag_reindex_url"] == "/rag/reindex"
        assert summary["memory_status"] in {"available", "disabled"} or summary[
            "memory_status"
        ].startswith("degraded:")
        assert isinstance(summary["workflow_memory_count"], int)
        assert "memory_vector_status" in summary
        assert isinstance(summary["memory_vector_errors"], list)
        assert summary["runtime_capabilities"]["streaming_transport"] == "push_sse"
        assert summary["runtime_capabilities"]["websocket_runtime"] is False
        assert any(action["action"] == "cancel" for action in summary["unsupported_actions"])
        assert isinstance(summary["warnings"], list)
    finally:
        workflow_service.outputs_dir = original_outputs


def test_geometry_fidelity_summary_counts_scene_components_by_declared_role() -> None:
    summary = _geometry_fidelity_summary(
        {
            "scene_id": "scene_fidelity",
            "network_type": "5G",
            "tower": {
                "asset_id": "tower",
                "asset_metadata": {"geometry_fidelity": "schematic"},
                "position": [0.0, 0.0, 0.0],
                "rotation_deg": [0.0, 0.0, 0.0],
                "height_m": 30.0,
            },
            "sectors": [
                {
                    "sector_id": "S1",
                    "antenna_asset_id": "antenna_generic",
                    "antenna_asset_metadata": {"geometry_fidelity": "technical_generic"},
                    "radio_asset_id": "radio_generic",
                    "radio_asset_metadata": {"geometry_fidelity": "technical_generic"},
                    "install_height_m": 24.0,
                    "azimuth_deg": 0.0,
                    "beamwidth_deg": 65.0,
                },
                {
                    "sector_id": "S2",
                    "antenna_asset_id": "antenna_vendor",
                    "antenna_asset_metadata": {"geometry_fidelity": "vendor_qualified"},
                    "install_height_m": 24.0,
                    "azimuth_deg": 120.0,
                    "beamwidth_deg": 65.0,
                },
            ],
            "accessory_assets": [
                {
                    "asset_id": "cabinet_vendor",
                    "asset_type": "cabinet",
                    "asset_metadata": {"geometry_fidelity": "vendor_qualified"},
                    "position": [2.0, 0.0, 0.0],
                    "rotation_deg": [0.0, 0.0, 0.0],
                }
            ],
        }
    )

    assert summary == {
        "component_count": 5,
        "counts": {
            "schematic": 1,
            "technical_generic": 2,
            "vendor_qualified": 2,
        },
        "roles": {
            "schematic": ["tower"],
            "technical_generic": ["antenna", "radio"],
            "vendor_qualified": ["antenna", "cabinet"],
        },
    }


def test_geometry_fidelity_summary_rejects_invalid_scene_instead_of_guessing() -> None:
    assert _geometry_fidelity_summary({"mesh_qa_passed": True}) is None


def test_geometry_program_summary_exposes_bounded_llm_provenance(tmp_path: Path) -> None:
    scene_path = tmp_path / "scene_spec.json"
    scene_path.write_text(
        """
        {
          "scene_id":"wf_geometry_summary",
          "network_type":"5G",
          "tower":{
            "asset_id":"TOWER_LATTICE_30M",
            "position":[0,0,0],
            "rotation_deg":[0,0,0],
            "height_m":30
          },
          "sectors":[{
            "sector_id":"S1",
            "antenna_asset_id":"ANT_PANEL_5G_001",
            "install_height_m":24,
            "azimuth_deg":0,
            "beamwidth_deg":65
          }],
          "geometry_programs":[{
            "program_id":"shelter.llm_v1",
            "semantic_role":"technical_shelter",
            "requested_quantity":1,
            "authorship":"llm_generated",
            "generator_provider":"groq",
            "generator_model":"openai/gpt-oss-120b",
            "structured_output_mode":"json_object_repaired",
            "source_prompt_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "nodes":[{
              "kind":"primitive",
              "node_id":"body",
              "primitive":"box",
              "size_m":{"x":3,"y":2.2,"z":2.5},
              "semantic_role":"technical_shelter"
            },{
              "kind":"primitive",
              "node_id":"door",
              "primitive":"box",
              "size_m":{"x":0.8,"y":0.08,"z":1.8}
            },{
              "kind":"primitive",
              "node_id":"roof",
              "primitive":"box",
              "size_m":{"x":3.2,"y":2.4,"z":0.12}
            }],
            "limitations":["No structural certification."]
          }]
        }
        """,
        encoding="utf-8",
    )

    summary = _geometry_program_summary_from_path(scene_path)

    assert summary is not None
    assert summary["program_count"] == 1
    assert summary["generated_component_count"] == 1
    assert summary["total_node_count"] == 3
    assert summary["repaired_program_count"] == 1
    assert summary["programs"][0]["generator_model"] == "openai/gpt-oss-120b"


class _MemoryStatusProbe:
    def __init__(self, latest: dict, compatibility: dict, outbox: dict | None = None) -> None:
        self.latest = latest
        self.compatibility = compatibility
        self.outbox = outbox or {}

    def stats(self) -> dict:
        return {}

    def index_health(self) -> dict:
        return {
            "latest_index_result": self.latest,
            "vector_compatibility": self.compatibility,
            "vector_outbox": self.outbox,
        }


def test_memory_status_distinguishes_migration_from_index_failure() -> None:
    migration = memory_status(
        _MemoryStatusProbe(
            {"status": "not_indexed", "errors": []},
            {"status": "migration_pending", "degraded": True},
        )
    )
    assert migration["memory_status"] == "degraded:vector_migration_pending"
    assert migration["memory_vector_status"] == "migration_pending"
    assert migration["memory_vector_errors"] == []

    failure = memory_status(
        _MemoryStatusProbe(
            {"status": "failed", "errors": ["provider_failure"]},
            {"status": "compatible", "degraded": False},
        )
    )
    assert failure["memory_status"] == "degraded:vector_index"
    assert failure["memory_vector_status"] == "failed"
    assert failure["memory_vector_errors"] == ["vector_index_write_failed"]

    pending = memory_status(
        _MemoryStatusProbe(
            {"status": "pending", "errors": []},
            {"status": "migration_pending", "degraded": True},
            {"status": "pending", "degraded": True},
        )
    )
    assert pending["memory_status"] == "degraded:vector_projection_pending"
    assert pending["memory_vector_status"] == "pending"
    assert pending["memory_vector_errors"] == ["vector_projection_pending"]


def test_studio_warnings_distinguish_unverified_and_failed_rag(monkeypatch) -> None:
    monkeypatch.setattr("apps.api.telecom_studio_api.product._blender_available", lambda: True)
    inventory = {"entries": [], "missing_file_count": 0}
    unverified = _studio_warnings(
        inventory,
        {
            "degraded": True,
            "status": "configured_unverified",
            "reranker_degraded_reason": None,
        },
    )
    assert unverified[0]["title"] == "RAG configuré mais non vérifié"
    assert "recherche de contrôle" in unverified[0]["recommended_action"]

    failed = _studio_warnings(
        inventory,
        {
            "degraded": True,
            "status": "configured_but_last_operation_failed",
            "reranker_degraded_reason": None,
        },
    )
    assert failed[0]["title"] == "RAG indisponible lors du dernier appel"
    assert "Configurer NVIDIA_API_KEY" not in failed[0]["recommended_action"]


@pytest.mark.blender_runtime
def test_user_summary_returns_human_readable_issues(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=(
                "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
                "Azimuts : 0°, 120°, 240°."
            ),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        summary = client.get(f"/designs/{workflow_id}/user-summary").json()

        assert summary["workflow_id"] == workflow_id
        assert summary["status"] == "completed"
        assert summary["current_operation"]
        assert summary["next_recommended_action"]
        assert summary["qa_summary"]
        assert isinstance(summary["human_readable_issues"], list)
        assert isinstance(summary["limitations"], list)
        assert summary["runtime_capabilities"]["workflow_id_source"] == "workflow_id"
        assert any(
            action["action"] == "websocket_runtime" for action in summary["unsupported_actions"]
        )
        for issue in summary["human_readable_issues"]:
            assert "title" in issue
            assert "severity" in issue
            assert "impact" in issue
            assert "recommended_action" in issue
    finally:
        workflow_service.outputs_dir = original_outputs


@pytest.mark.blender_runtime
def test_current_operation_for_completed_workflow(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=("Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m."),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        workflow_service._emit_workflow_event(
            workflow_id,
            "workflow_failed",
            {
                "phase": "runtime",
                "node": "stale_recovery_event",
                "status": "failed",
                "error": "STALE_EVENT_FOR_PROJECTION_TEST",
            },
        )
        operation = client.get(f"/designs/{workflow_id}/current-operation").json()

        assert operation["workflow_id"] == workflow_id
        assert operation["status"] == "completed"
        assert operation["current_operation"]
        assert operation["next_recommended_action"]
        assert operation["progress_indicator"] == "done"
        assert operation["phase"] == "workflow"
        assert operation["human_label"] == "Workflow terminé"
        assert operation["progress_message"]
        assert operation["progress_label"] == "Terminé"
        assert operation["is_running"] is False
        assert operation["is_terminal"] is True
        assert operation["last_event_at"]
        assert "open_viewer" in operation["available_actions"]
        assert operation["current_phase"] in {
            "requirements",
            "rag",
            "memory",
            "assets",
            "scene",
            "quality_gate",
            "blender",
            "qa",
            "workflow",
        }
        assert operation["current_node"]
        assert operation["event_source"] == "push_sse"
        assert operation["state_source"] == "status"
        assert operation["runtime_capabilities"]["streaming_transport"] == "push_sse"
        assert operation["runtime_capabilities"]["can_cancel"] is False
        assert any(action["action"] == "pause" for action in operation["unsupported_actions"])
    finally:
        workflow_service.outputs_dir = original_outputs


@pytest.mark.blender_runtime
def test_current_operation_prefers_persisted_edit_over_old_terminal_event(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=("Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m."),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        previous = workflow_service._begin_active_operation(
            workflow_id,
            operation_id="edit_test",
            kind="edit",
            human_label="Révision du design",
        )

        status = client.get(f"/designs/{workflow_id}").json()
        operation = client.get(f"/designs/{workflow_id}/current-operation").json()

        assert status["status"] == "running"
        assert status["active_operation"]["operation_id"] == "edit_test"
        assert operation["human_label"] == "Révision du design"
        assert operation["state_source"] == "persisted_active_operation"
        assert operation["is_running"] is True
        assert operation["is_terminal"] is False

        manifest = workflow_service.versioning.active_design_manifest(workflow_id)
        assert manifest is not None
        canonical_version_id = manifest["version_id"]
        status_path = tmp_path / workflow_id / "status.json"
        divergent_status = json.loads(status_path.read_text(encoding="utf-8"))
        divergent_status["active_version_id"] = "version_projection_diverged"
        status_path.write_text(json.dumps(divergent_status), encoding="utf-8")
        monkeypatch.setattr(workflow_service, "_is_workflow_active", lambda _workflow_id: True)
        original_verify = scene_versioning.verify_persisted_version
        verification_calls = 0

        def counted_verify(*args, **kwargs):
            nonlocal verification_calls
            verification_calls += 1
            return original_verify(*args, **kwargs)

        monkeypatch.setattr(scene_versioning, "verify_persisted_version", counted_verify)
        bundle = client.get(f"/designs/{workflow_id}/viewer-bundle").json()

        assert verification_calls == 1
        assert bundle["status"] == "running"
        assert bundle["active_version"] == canonical_version_id
        assert bundle["primary_glb_url"].endswith(f"?version_id={canonical_version_id}")
        assert "version_projection_diverged" not in bundle["primary_glb_url"]
        workflow_service._restore_status_after_operation(
            workflow_id, previous, operation_id="edit_test"
        )
        assert client.get(f"/designs/{workflow_id}").json()["status"] == "completed"
    finally:
        workflow_service.outputs_dir = original_outputs


@pytest.mark.blender_runtime
def test_viewer_bundle_returns_artifact_urls(tmp_path: Path, monkeypatch) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=("Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m."),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        original_verify = scene_versioning.verify_persisted_version
        verification_calls = 0

        def counted_verify(*args, **kwargs):
            nonlocal verification_calls
            verification_calls += 1
            return original_verify(*args, **kwargs)

        monkeypatch.setattr(
            scene_versioning,
            "verify_persisted_version",
            counted_verify,
        )
        bundle = client.get(f"/designs/{workflow_id}/viewer-bundle").json()

        assert verification_calls == 1
        assert bundle["workflow_id"] == workflow_id
        assert bundle["status"] == "completed"
        assert bundle["generation_mode"]
        assert bundle["primary_glb_url"]
        assert bundle["preview_url"]
        assert bundle["report_url"]
        assert bundle["metadata_url"]
        assert bundle["component_proofs_url"]
        assert bundle["requirements_spec_url"]
        assert bundle["extraction_report_url"]
        assert bundle["scene_spec_url"]
        assert bundle["qa_report_url"]
        assert bundle["generation_report_url"]
        assert bundle["geometry_validation_url"]
        assert bundle["requirement_coverage_url"]
        assert bundle["completion_certificate_url"]
        assert bundle["requirement_coverage_passed"] is True
        assert bundle["requirement_coverage_ratio"] == 1.0
        assert bundle["completion_certificate_status"] == "issued"
        assert bundle["rag_evidence_url"]
        assert bundle["llm_provider"] == "deterministic"
        assert bundle["extraction_provider"] == "deterministic"
        assert isinstance(bundle["llm_available"], bool)
        assert bundle["llm_fallback_used"] is True
        assert bundle["llm_fallback_reason"] == "deterministic_extraction_requested"
        assert bundle["rag_context_count"] == 0 or isinstance(bundle["rag_context_count"], int)
        assert isinstance(bundle["rag_planning_summary"], dict)
        assert bundle["rag_planning_summary"]["rag_used_for_extraction"] is False
        assert "rag_planning_mode" in bundle["rag_planning_summary"]
        assert isinstance(bundle["rag_planning_summary"]["controlled_hint_fields"], list)
        assert "rag_reranker_status" in bundle
        assert "rag_reranker_provider" in bundle
        assert "rag_reranker_model" in bundle
        assert "rag_reranker_degraded_reason" in bundle
        assert "rag_retrieval_status" in bundle
        assert "rag_retrieval_degraded_reason" in bundle
        assert bundle["memory_context_count"] == 0 or isinstance(
            bundle["memory_context_count"], int
        )
        assert bundle["qa_summary"]["mesh_qa_level"]
        assert isinstance(bundle["qa_summary"]["checks_passed"], list)
        assert isinstance(bundle["qa_summary"]["checks_failed"], list)
        fidelity = bundle["geometry_fidelity_summary"]
        assert fidelity["component_count"] == sum(fidelity["counts"].values())
        assert fidelity["counts"]["technical_generic"] >= 1
        assert "antenna" in fidelity["roles"]["technical_generic"]
        assert bundle["primary_glb_url"].startswith(f"/designs/{workflow_id}/artifacts/glb")
        assert "/Users/" not in bundle["primary_glb_url"]
        assert bundle["component_proofs_url"].startswith(
            f"/designs/{workflow_id}/artifacts/component_proofs"
        )
        assert "/Users/" not in bundle["component_proofs_url"]
        assert bundle["runtime_capabilities"]["workflow_id_source"] == "workflow_id"
        assert bundle["runtime_capabilities"]["websocket_runtime"] is False
        assert any(action["action"] == "retry" for action in bundle["unsupported_actions"])
        if bundle["mesh_qa_level"] == "mesh_level_basic":
            assert any("mesh_level_basic" in item for item in bundle["limitations"])
        assert "open_viewer" in bundle["available_actions"]
        assert isinstance(bundle["human_warnings_count"], int)
        assert isinstance(bundle["human_errors_count"], int)
        assert isinstance(bundle["viewer_artifacts"], list)
        names = {a["name"] for a in bundle["viewer_artifacts"]}
        assert len(names) == len(bundle["viewer_artifacts"])
        assert "design.glb" in names
        assert "preview.png" in names
        assert {
            "preview_front.png",
            "preview_side.png",
            "preview_top.png",
            "preview_closeup.png",
        } <= names
        assert "scene_metadata.json" in names
        assert "component_proofs.json" in names
        assert "requirements_spec.json" in names
        assert "extraction_report.json" in names
        assert "qa_report.json" in names
        assert "geometry_validation.json" in names
        assert "rag_evidence.json" in names
        for preview_name in (
            "preview_front.png",
            "preview_side.png",
            "preview_top.png",
            "preview_closeup.png",
        ):
            artifact = next(
                item for item in bundle["viewer_artifacts"] if item["name"] == preview_name
            )
            assert artifact["available"] is True
            response = client.get(artifact["url"])
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("image/png")
        component_proofs_artifact = next(
            artifact
            for artifact in bundle["viewer_artifacts"]
            if artifact["name"] == "component_proofs.json"
        )
        assert component_proofs_artifact["available"] is True
        assert component_proofs_artifact["url"] == bundle["component_proofs_url"]
        component_proofs_response = client.get(bundle["component_proofs_url"])
        assert component_proofs_response.status_code == 200
        assert component_proofs_response.headers["content-type"].startswith("application/json")
        component_proofs = component_proofs_response.json()
        assert component_proofs["workflow_id"] == workflow_id
        assert component_proofs["components"]
        assert component_proofs["operation_execution"]["passed"] is True
        for artifact in bundle["viewer_artifacts"]:
            assert artifact["url"].startswith(f"/designs/{workflow_id}/artifacts/")
            assert "/Users/" not in artifact["url"]
            assert isinstance(artifact["available"], bool)

        calls_before_rejection = verification_calls

        def rejected_verify(*_args, **_kwargs):
            nonlocal verification_calls
            verification_calls += 1
            raise ValueError("ACTIVE_VERSION_ARTIFACT_HASH_MISMATCH:glb")

        monkeypatch.setattr(
            scene_versioning,
            "verify_persisted_version",
            rejected_verify,
        )
        rejected_bundle = client.get(f"/designs/{workflow_id}/viewer-bundle").json()

        assert verification_calls == calls_before_rejection + 1
        assert rejected_bundle["status"] == "integrity_failed"
        assert rejected_bundle["primary_glb_url"] is None
        assert rejected_bundle["scene_spec_url"] is None
        assert rejected_bundle["assembly_plan_url"] is None
        assert rejected_bundle["asset_decision_summary"] is None
        assert rejected_bundle["geometry_fidelity_summary"] is None
        assert rejected_bundle["geometry_program_summary"] is None
        assert not any(artifact["available"] for artifact in rejected_bundle["viewer_artifacts"])
    finally:
        workflow_service.outputs_dir = original_outputs


def test_failed_blender_workflow_does_not_advertise_viewer_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    monkeypatch.setattr(
        workflow_service.orchestrator.blender_runner,
        "_resolve_blender_binary",
        lambda: None,
    )
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=(
                "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
                "Azimuts : 0°, 120°, 240°."
            ),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]

        assert response["status"] == "failed"
        status = client.get(f"/designs/{workflow_id}").json()
        bundle = client.get(f"/designs/{workflow_id}/viewer-bundle").json()
        events = client.get(f"/designs/{workflow_id}/events").json()

        assert "glb" not in status["artifacts"]
        assert "preview" not in status["artifacts"]
        assert bundle["primary_glb_url"] is None
        assert bundle["preview_url"] is None
        assert bundle["component_proofs_url"] is None
        assert not any(event["event_type"] == "artifact_ready" for event in events)
        availability = {
            artifact["name"]: artifact["available"] for artifact in bundle["viewer_artifacts"]
        }
        assert availability["design.glb"] is False
        assert availability["preview.png"] is False
        assert availability["component_proofs.json"] is False
    finally:
        workflow_service.outputs_dir = original_outputs


@pytest.mark.blender_runtime
def test_timeline_summary_returns_readable_steps(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=("Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m."),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        timeline = client.get(f"/designs/{workflow_id}/timeline-summary").json()

        assert timeline["workflow_id"] == workflow_id
        assert timeline["event_source"] == "push_sse"
        assert isinstance(timeline["timeline_steps"], list)
        assert len(timeline["timeline_steps"]) > 0
        step_names = {step["step"] for step in timeline["timeline_steps"]}
        assert "design_created" in step_names
        assert "retrieve_rag_context" in step_names
        assert "memory_recall" in step_names
        assert "select_assets" in step_names
        assert "plan_scene" in step_names
        assert "generate_blender" in step_names
        assert "qa_generation" in step_names
        assert timeline["timeline_steps"][-1]["step"] == "workflow_completed"
        for step in timeline["timeline_steps"]:
            assert "step" in step
            assert "node" in step
            assert "label" in step
            assert "human_label" in step
            assert "progress_message" in step
            assert "phase" in step
            assert "status" in step
            assert "started_at" in step
            assert "completed_at" in step
            assert "duration_ms" in step
            assert "warnings_count" in step
            assert "errors_count" in step
            assert "artifact_refs" in step
            assert "human_readable" in step
    finally:
        workflow_service.outputs_dir = original_outputs


@pytest.mark.blender_runtime
def test_workflow_events_expose_runtime_nodes_without_premature_blender_event(
    tmp_path: Path,
) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=("Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m."),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        events = client.get(f"/designs/{workflow_id}/events").json()

        event_types = [event["event_type"] for event in events]
        assert event_types[0] == "design_created"
        assert "blender_started" not in event_types
        node_events = [
            event
            for event in events
            if event["event_type"]
            in {"node_started", "node_completed", "node_failed", "node_skipped"}
        ]
        assert node_events
        nodes = [event["payload"]["node"] for event in node_events]
        assert "extract_requirements" in nodes
        assert "retrieve_rag_context" in nodes
        assert "select_assets" in nodes
        assert "plan_scene" in nodes
        assert "generate_blender" in nodes
        assert "qa_generation" in nodes
        assert all(event["payload"].get("phase") for event in node_events)
        assert all(event.get("workflow_id") == workflow_id for event in events)
        assert all(event.get("timestamp") for event in events)
        assert all(event.get("event_id") for event in events)
        assert all(event.get("event_source") == "workflow_events_jsonl" for event in events)
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
        assert "node_started" in event_types
        assert "artifact_ready" in event_types
        assert "qa_completed" in event_types
    finally:
        workflow_service.outputs_dir = original_outputs


@pytest.mark.blender_runtime
def test_user_issues_endpoint_returns_issues(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=("Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m."),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        issues_payload = client.get(f"/designs/{workflow_id}/user-issues").json()

        assert issues_payload["workflow_id"] == workflow_id
        assert isinstance(issues_payload["human_readable_issues"], list)
    finally:
        workflow_service.outputs_dir = original_outputs


def test_invalid_design_has_frontend_readable_failure_contract(tmp_path: Path) -> None:
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text="Créer un pylône 300m avec 20 secteurs",
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        assert response["status"] == "failed"

        status = client.get(f"/designs/{workflow_id}").json()
        operation = client.get(f"/designs/{workflow_id}/current-operation").json()
        timeline = client.get(f"/designs/{workflow_id}/timeline-summary").json()
        issues = client.get(f"/designs/{workflow_id}/user-issues").json()

        assert status["status"] == "failed"
        assert any(error["code"] == "INVALID_REQUIREMENTS" for error in status["errors"])
        assert operation["is_terminal"] is True
        assert operation["progress_label"] == "Échec"
        assert "retry_with_changes" in operation["available_actions"]
        assert operation["runtime_capabilities"]["can_retry_same_workflow"] is False
        assert any(action["action"] == "retry" for action in operation["unsupported_actions"])
        assert timeline["timeline_steps"][-1]["status"] == "failed"
        assert issues["human_readable_issues"]
        assert any(
            issue["technical_code"] == "INVALID_REQUIREMENTS"
            for issue in issues["human_readable_issues"]
        )
    finally:
        workflow_service.outputs_dir = original_outputs


def test_timeline_marks_rejected_edit_and_failed_qa_as_failed() -> None:
    events = [
        {
            "event_type": "edit_patch_rejected",
            "timestamp": "2026-07-29T00:00:00Z",
            "payload": {"status": "rejected"},
        },
        {
            "event_type": "qa_failed",
            "timestamp": "2026-07-29T00:00:01Z",
            "payload": {"status": "failed"},
        },
    ]

    timeline = _events_to_timeline(events, {"status": "completed"})

    assert [step["status"] for step in timeline[:2]] == ["failed", "failed"]


def test_document_pack_capabilities_expose_limited_frontend_contract() -> None:
    client = TestClient(app)

    payload = client.get("/document-packs/capabilities").json()

    assert payload["document_pack_status"] == "limited"
    assert payload["supported_upload_format"] == "zip_or_multiple_files"
    assert payload["supported_inputs"]["upload"] == "zip_or_multiple_files"
    assert ".pdf" in payload["supported_extensions"]
    assert payload["limits"]["max_zip_size_mb"] == 80
    assert payload["max_size"]["zip_mb"] == 80
    assert "available_tools" in payload
    assert "disabled_tools" in payload
    assert isinstance(payload["limitations"], list)
    assert payload["next_action"]
    assert payload["truth"]["advanced_ingestion"] is False
    assert payload["truth"]["docling_default_enabled"] is False
    assert "pdf_text_extraction" in payload["capabilities"]
    # Backwards-compatible flat keys are still present.
    assert "pdf_text_extraction" in payload


def test_product_endpoints_return_404_for_unknown_workflow() -> None:
    client = TestClient(app)
    endpoints = [
        "/designs/wf_000000000000/user-summary",
        "/designs/wf_000000000000/current-operation",
        "/designs/wf_000000000000/user-issues",
        "/designs/wf_000000000000/viewer-bundle",
        "/designs/wf_000000000000/timeline-summary",
    ]
    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 404, endpoint


def test_cors_allows_local_frontend_and_rejects_unknown_origin() -> None:
    client = TestClient(app)
    allowed = client.get("/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"

    rejected = client.get("/health", headers={"Origin": "https://example.invalid"})
    assert rejected.status_code == 200
    assert "access-control-allow-origin" not in rejected.headers


def test_health_exposes_only_aggregate_groq_pool_state() -> None:
    payload = TestClient(app).get("/health").json()

    pool = payload["groq_credential_pool"]
    assert pool["status"] in {
        "disabled",
        "configured_unverified",
        "operational",
        "degraded",
        "unavailable",
    }
    assert pool["configured_credentials"] >= 0
    assert pool["ready_credentials"] >= 0
    serialized = json.dumps(pool)
    assert "api_key" not in serialized
    assert "Authorization" not in serialized


def test_frontend_v1_openapi_contract_has_typed_public_surfaces() -> None:
    schema = app.openapi()

    assert (
        schema["paths"]["/designs"]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]["items"]["$ref"]
        == "#/components/schemas/DesignListSummary"
    )
    assert (
        schema["paths"]["/designs/{workflow_id}/events"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["items"]["$ref"]
        == "#/components/schemas/WorkflowEventView"
    )
    assert (
        schema["paths"]["/designs/{workflow_id}/versions"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["items"]["$ref"]
        == "#/components/schemas/PublicVersionInfo"
    )
    assert (
        schema["paths"]["/designs/{workflow_id}/versions/{version_id}/rollback"]["post"][
            "responses"
        ]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/RollbackVersionResponse"
    )
    assert (
        schema["paths"]["/document-packs/capabilities"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/DocumentPackCapabilitiesView"
    )
    assert (
        schema["paths"]["/assets/inventory"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/AssetInventoryResponse"
    )
    assert "RuntimeCapabilities" in schema["components"]["schemas"]
    assert "UnsupportedAction" in schema["components"]["schemas"]
    assert "component_proofs_url" in schema["components"]["schemas"]["ViewerBundle"]["properties"]
    assert (
        "constraint_evidence_url" in schema["components"]["schemas"]["ViewerBundle"]["properties"]
    )
    assert (
        schema["components"]["schemas"]["ViewerBundle"]["properties"][
            "assembly_constraint_summary"
        ]["anyOf"][0]["$ref"]
        == "#/components/schemas/AssemblyConstraintSummary"
    )
    assert (
        schema["paths"]["/document-packs/{pack_id}/generate-design"]["post"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/DocumentPackGenerateDesignResponse"
    )


@pytest.mark.blender_runtime
def test_frontend_does_not_need_raw_json_for_primary_ui(tmp_path: Path) -> None:
    """User-summary must expose enough structured data to render UI without status.json."""
    original_outputs = workflow_service.outputs_dir
    workflow_service.outputs_dir = tmp_path
    client = TestClient(app)
    try:
        response = workflow_service.create_design(
            requirements_text=("Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m."),
            detail_level="high",
            use_llm=False,
            _synchronous=True,
        )
        workflow_id = response["workflow_id"]
        summary = client.get(f"/designs/{workflow_id}/user-summary").json()
        bundle = client.get(f"/designs/{workflow_id}/viewer-bundle").json()
        operation = client.get(f"/designs/{workflow_id}/current-operation").json()
        issues = client.get(f"/designs/{workflow_id}/user-issues").json()

        assert summary["qa_summary"]
        assert summary["asset_quality_summary"]
        assert bundle["viewer_artifacts"]
        assert operation["current_operation"]
        assert isinstance(issues["human_readable_issues"], list)
    finally:
        workflow_service.outputs_dir = original_outputs


def test_product_issues_humanize_real_asset_warning_codes() -> None:
    status = {
        "status": "completed",
        "warnings": [
            {
                "code": "ASSET_IMPORT_INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE",
                "message": "ANT_PANEL_5G_001: INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE",
                "severity": "warning",
            },
            {
                "code": "ASSET_IMPORT_PROCEDURAL_FALLBACK",
                "message": (
                    "TOWER_MONOPOLE_30M used procedural fallback instead of a real GLB import."
                ),
                "severity": "warning",
            },
        ],
        "errors": [],
        "asset_import_summary": {"procedural_fallback_count": 1},
    }

    from apps.api.telecom_studio_api.product import _collect_user_issues

    issues = _collect_user_issues(status)
    titles = {issue["title"] for issue in issues}
    assert "Asset interne minimal" in titles
    assert "Fallback procédural d'asset" in titles
    minimal_issue = next(issue for issue in issues if issue["title"] == "Asset interne minimal")
    assert "chaîne de génération est vérifiée" in minimal_issue["impact"]
    assert "fidélité constructeur" in minimal_issue["impact"]
    assert "valide techniquement" not in minimal_issue["impact"]


def test_product_asset_summaries_recognize_exact_glb_imports() -> None:
    inventory = {
        "entries": [
            {"asset_import_mode": "imported_glb_exact"},
        ]
    }
    assert _inventory_status(inventory) == "ready_for_import"

    quality = _asset_quality_summary(
        {
            "asset_imports": [
                {
                    "asset_id": "ANT_PANEL_4G_001",
                    "import_mode": "imported_glb_exact",
                    "asset_file_exists": True,
                }
            ]
        }
    )
    assert quality == "1 mesh(es) GLB importé(s), 0 composant(s) généré(s) par profil contrôlé."


def test_product_issues_deduplicate_repeated_sector_warnings() -> None:
    from apps.api.telecom_studio_api.product import _collect_user_issues

    repeated = {
        "code": "ASSET_IMPORT_INTERNAL_PROJECT_GENERATED_ASSET_NOT_VENDOR_GRADE",
        "message": "MOUNTING_BRACKET_001: INTERNAL_PROJECT_GENERATED_ASSET_NOT_VENDOR_GRADE",
        "severity": "warning",
    }
    status = {
        "status": "completed",
        "warnings": [
            repeated,
            repeated,
            {
                **repeated,
                "message": (
                    "ANT_PANEL_5G_DUALBAND_V1: INTERNAL_PROJECT_GENERATED_ASSET_NOT_VENDOR_GRADE"
                ),
            },
            {
                "code": "ASSET_IMPORT_PROCEDURAL_FALLBACK",
                "message": "PROCEDURAL_CABLE_ROUTE used procedural fallback.",
                "severity": "warning",
            },
            {
                "code": "ASSET_IMPORT_PROCEDURAL_FALLBACK_USED",
                "message": "PROCEDURAL_CABLE_ROUTE: PROCEDURAL_FALLBACK_USED",
                "severity": "warning",
            },
        ],
        "errors": [],
        "asset_import_summary": {"procedural_fallback_count": 3},
    }

    issues = _collect_user_issues(status)

    assert [
        issue["technical_code"]
        for issue in issues
        if issue["technical_code"]
        == "ASSET_IMPORT_INTERNAL_PROJECT_GENERATED_ASSET_NOT_VENDOR_GRADE"
    ] == ["ASSET_IMPORT_INTERNAL_PROJECT_GENERATED_ASSET_NOT_VENDOR_GRADE"]
    assert (
        sum(
            issue["technical_code"].startswith("ASSET_IMPORT_PROCEDURAL_FALLBACK")
            for issue in issues
        )
        == 1
    )
    assert any(issue["title"] == "Composants internes non constructeur" for issue in issues)


def test_product_issues_humanize_ai_rf_and_tower_warning_codes() -> None:
    status = {
        "status": "completed",
        "warnings": [
            {
                "code": "LLM_FIELD_REPAIRED",
                "message": "include_gps_antenna restored from deterministic baseline.",
                "severity": "warning",
            },
            {
                "code": "RF_BEAMWIDTH_NARROW",
                "message": "Beamwidth 65.0° may be too narrow for 3 sectors.",
                "severity": "warning",
            },
            {
                "code": "TOWER_PLATFORM_RECOMMENDED",
                "message": "Tower platform recommended for equipment access.",
                "severity": "warning",
            },
            {
                "code": "TOWER_AVIATION_MARKING_REVIEW_REQUIRED",
                "message": "Applicable aviation rules require review.",
                "severity": "warning",
            },
        ],
        "errors": [],
    }

    from apps.api.telecom_studio_api.product import _collect_user_issues

    issues = _collect_user_issues(status)
    titles = {issue["title"] for issue in issues}
    assert "Champ IA réparé par le backend" in titles
    assert "Beamwidth à vérifier" in titles
    assert "Plateforme pylône recommandée" in titles
    assert "Balisage aviation à vérifier" in titles


def test_product_issues_do_not_replay_failed_runtime_nodes_after_certified_completion() -> None:
    from apps.api.telecom_studio_api.product import _collect_user_issues

    status = {"status": "completed", "warnings": [], "errors": []}
    events = [
        {
            "event_type": "node_failed",
            "payload": {
                "node": "retrieve_rag_context",
                "phase": "rag",
                "status": "failed",
                "detail": "failed: RuntimeError",
                "errors": ["Qdrant local storage is locked."],
            },
        }
    ]

    issues = _collect_user_issues(status, events)

    assert issues == []


def test_product_issues_humanize_failed_runtime_nodes_without_internal_details() -> None:
    from apps.api.telecom_studio_api.product import _collect_user_issues

    status = {"status": "failed", "warnings": [], "errors": []}
    events = [
        {
            "event_type": "node_failed",
            "payload": {
                "node": "generate_blender",
                "status": "failed",
                "errors": ["Traceback /Users/private/project.py ModuleNotFoundError: secret"],
            },
        }
    ]

    issues = _collect_user_issues(status, events)

    assert issues == [
        {
            "title": "Génération Blender en mode dégradé",
            "severity": "error",
            "impact": "Blender n'a pas produit les livrables 3D requis pour cette opération.",
            "recommended_action": (
                "Vérifiez Blender, les assets et les artefacts avant de relancer."
            ),
            "technical_code": "RUNTIME_NODE_FAILED:generate_blender",
        }
    ]
    assert "/Users/" not in str(issues)


def test_product_issues_keep_one_explicit_root_cause_instead_of_runtime_duplicates() -> None:
    from apps.api.telecom_studio_api.product import _collect_user_issues

    status = {
        "status": "failed",
        "warnings": [],
        "errors": [
            {
                "code": "GEOMETRY_PROGRAM_GENERATION_FAILED",
                "message": (
                    "La géométrie demandée n'a pas pu être produite; Blender n'a pas été lancé."
                ),
                "severity": "error",
            }
        ],
    }
    events = [
        {
            "event_type": "node_failed",
            "payload": {"node": "plan_generated_geometry", "status": "failed"},
        },
        {
            "event_type": "node_failed",
            "payload": {
                "node": "geometry_program_failure_handler",
                "status": "failed",
            },
        },
    ]

    issues = _collect_user_issues(status, events)

    assert [issue["technical_code"] for issue in issues] == ["GEOMETRY_PROGRAM_GENERATION_FAILED"]
    assert issues[0]["title"] == "Composant personnalisé non généré"
    assert "spécialiste LLM" not in str(issues[0])
    assert "Blender" in issues[0]["impact"]


def test_product_issues_humanize_and_deduplicate_geometry_qa_failures() -> None:
    from apps.api.telecom_studio_api.product import _collect_user_issues

    issues = _collect_user_issues(
        {
            "status": "failed",
            "warnings": [],
            "errors": [
                {
                    "code": "GEOMETRY_VALIDATION_VALID",
                    "message": "QA check failed: geometry_validation_valid",
                    "severity": "error",
                },
                {
                    "code": "GEOMETRY_VALIDATION_mesh_qa_passed",
                    "message": "Geometry validation failed: mesh_qa_passed",
                    "severity": "error",
                },
            ],
        }
    )

    assert issues == [
        {
            "title": "Contrôle géométrique refusé",
            "severity": "error",
            "impact": (
                "Blender a produit le modèle, mais une règle obligatoire de placement ou "
                "de géométrie a échoué. Ce résultat n'a pas été publié et la dernière "
                "version certifiée reste protégée."
            ),
            "recommended_action": (
                "Corrigez le placement ou les dimensions signalés dans Vérification, "
                "puis relancez la demande."
            ),
            "technical_code": "GEOMETRY_VALIDATION_FAILED",
        }
    ]
    assert "geometry_validation_valid" not in str(issues)


def test_viewer_qa_summary_distinguishes_upstream_failure_from_empty_qa() -> None:
    from apps.api.telecom_studio_api.product import _viewer_qa_summary

    qa = _viewer_qa_summary(
        {
            "status": "failed",
            "warnings": [],
            "errors": [
                {
                    "code": "GEOMETRY_PROGRAM_GENERATION_FAILED",
                    "message": "La génération a échoué avant Blender.",
                }
            ],
            "mesh_qa_level": None,
            "mesh_qa_passed": None,
            "qa_score": None,
        }
    )

    assert qa["qa_status"] == "not_started"
    assert qa["qa_executed"] is False
    assert qa["blocked_before_qa"] is True
    assert qa["checks_passed"] == []
    assert qa["checks_failed"] == []
    assert qa["errors"] == []
    assert qa["upstream_errors"] == ["GEOMETRY_PROGRAM_GENERATION_FAILED"]


def test_product_issues_expose_bounded_planning_fallback_without_degrading_3d() -> None:
    from apps.api.telecom_studio_api.product import _collect_user_issues

    issues = _collect_user_issues(
        {
            "status": "completed",
            "generation_mode": "real_blender",
            "warnings": [],
            "errors": [],
            "rag_planning_summary": {
                "decision_fallback_used": True,
                "decision_fallback_reason": "provider_timeout",
            },
        }
    )

    planning_issue = next(
        issue
        for issue in issues
        if issue["technical_code"] == "PLANNING_DECISION_FALLBACK_INFERRED"
    )
    assert planning_issue["severity"] == "info"
    assert "valeurs déjà validées" in planning_issue["impact"]


def _constraint_evidence_payload() -> dict:
    payload = {
        "schema_version": "1.0.0",
        "assembly_plan_schema_version": "1.1.0",
        "workflow_id": "wf_constraint_api",
        "status": "passed",
        "coordinate_space": "scenespec_z_up_meters",
        "glb_sha256": "a" * 64,
        "assembly_plan_sha256": "b" * 64,
        "angular_tolerance_deg": 1.0,
        "expected_measurement_count": 1,
        "measured_constraint_count": 1,
        "failed_constraint_count": 0,
        "measurements": [
            {
                "measurement_id": "mount-to-support:S1",
                "connection_id": "mount-to-support",
                "operation_id": "op-mount-to-support",
                "instance_id": "S1",
                "source_role_id": "sector_mount",
                "source_connector_id": "support",
                "source_anchor_id": "support_anchor",
                "target_role_id": "support_structure",
                "target_connector_id": "mount",
                "target_anchor_id": "mount_anchor",
                "source_frame": {
                    "coordinate_space": "scenespec_z_up_meters",
                    "position_m": [0.0, 0.0, 0.0],
                    "normal": [1.0, 0.0, 0.0],
                    "up": [0.0, 0.0, 1.0],
                    "source": "glb_fixed_anchor",
                    "gltf_node_index": 1,
                    "gltf_node_name": "sector_mount_S1",
                },
                "target_frame": {
                    "coordinate_space": "scenespec_z_up_meters",
                    "position_m": [0.004, 0.0, 0.0],
                    "normal": [-1.0, 0.0, 0.0],
                    "up": [0.0, 0.0, 1.0],
                    "source": "glb_resolved_anchor",
                    "gltf_node_index": 2,
                    "gltf_node_name": "support_structure_S1_target_marker",
                },
                "position_error_m": 0.004,
                "position_tolerance_m": 0.01,
                "normal_opposition_error_deg": 0.0,
                "up_alignment_error_deg": 0.0,
                "angular_tolerance_deg": 1.0,
                "position_passed": True,
                "normal_opposition_passed": True,
                "up_alignment_passed": True,
                "passed": True,
            }
        ],
        "unevaluated_required_connections": [],
        "errors": [],
        "limitations": ["limit one", "limit two", "limit three"],
    }
    payload["evidence_sha256"] = canonical_evidence_sha256(payload)
    return payload
