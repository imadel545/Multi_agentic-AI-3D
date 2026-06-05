import json
from pathlib import Path

from core.agents.scene_planner import ScenePlanner
from core.contracts.assets import AssetManifest
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import SceneSpec
from core.contracts.validation import ValidationReport
from core.performance import asset_manifest_hash, requirements_hash, scene_spec_hash
from core.rag import RagService
from core.services.asset_registry import AssetRegistry
from core.validation.quality_gates import evaluate_pre_blender_gate


def test_requirements_and_scene_hashes_are_stable() -> None:
    requirements, scene, _assets = _valid_scene_inputs()

    assert requirements_hash(requirements) == requirements_hash(requirements.model_copy())
    assert scene_spec_hash(scene) == scene_spec_hash(scene.model_copy())


def test_asset_manifest_hash_changes_on_manifest_change(tmp_path: Path) -> None:
    source = Path("assets/manifests/TOWER_LATTICE_30M.json")
    target = tmp_path / source.name
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    original = asset_manifest_hash(tmp_path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["version"] = "9.9.9"
    target.write_text(json.dumps(payload), encoding="utf-8")

    assert asset_manifest_hash(tmp_path) != original


def test_asset_registry_cache_hit_on_repeated_load() -> None:
    registry = AssetRegistry(Path("assets/manifests"))

    registry.list_assets()
    registry.list_assets()
    stats = registry.cache_stats()

    assert stats["asset_cache_misses"] >= 1
    assert stats["asset_cache_hits"] >= 1


def test_rag_query_cache_hit_on_repeated_query(tmp_path: Path) -> None:
    service = RagService(project_root=Path.cwd(), qdrant_path=tmp_path / "qdrant")
    service.reindex()

    first = service.search("5G lattice tower 3 sectors", limit=3)
    second = service.search("5G lattice tower 3 sectors", limit=3)
    stats = service.cache_stats()

    assert first
    assert [result.doc_id for result in second] == [result.doc_id for result in first]
    assert stats["rag_cache_misses"] >= 1
    assert stats["rag_cache_hits"] >= 1


def test_runtime_memory_collections_are_not_query_cached(tmp_path: Path) -> None:
    service = RagService(project_root=Path.cwd(), qdrant_path=tmp_path / "qdrant")
    service.upsert_runtime_document(
        collection="design_memory",
        doc_id="wf_runtime_memory",
        text="5G lattice memory summary",
        payload={"workflow_id": "wf_runtime_memory"},
    )

    first = service.search("5G lattice memory", collection="design_memory", limit=1)
    service.upsert_runtime_document(
        collection="design_memory",
        doc_id="wf_runtime_memory_2",
        text="5G lattice second memory summary",
        payload={"workflow_id": "wf_runtime_memory_2"},
    )
    second = service.search("second memory summary", collection="design_memory", limit=2)
    stats = service.cache_stats()

    assert first
    assert any(result.doc_id == "wf_runtime_memory_2" for result in second)
    assert stats == {"rag_cache_hits": 0, "rag_cache_misses": 0}


def test_cache_does_not_bypass_quality_gate_validation(tmp_path: Path) -> None:
    service = RagService(project_root=Path.cwd(), qdrant_path=tmp_path / "qdrant")
    service.reindex()
    service.search("5G lattice tower 3 sectors", limit=3)
    service.search("5G lattice tower 3 sectors", limit=3)
    requirements, scene, assets = _valid_scene_inputs()
    failed_scene_report = ValidationReport(
        design_id="wf_cache_validation",
        status="failed",
        score=0.0,
        checks={"scene_valid": False},
        errors=[],
    )

    gate = evaluate_pre_blender_gate(
        requirements=requirements,
        requirement_report=ValidationReport(
            design_id="wf_cache_validation",
            status="passed",
            score=1.0,
            checks={"requirements_valid": True},
        ),
        scene=scene,
        scene_report=failed_scene_report,
        selected_assets=assets,
        all_assets=AssetRegistry(Path("assets/manifests")).list_assets(),
        repair_attempts=0,
        max_repair_attempts=2,
    )

    assert service.cache_stats()["rag_cache_hits"] >= 1
    assert gate.passed is False
    assert gate.checks["scene_report_valid"] is False


def _valid_scene_inputs() -> tuple[RequirementSpec, SceneSpec, list[AssetManifest]]:
    requirements = RequirementSpec(
        network_type="5G",
        tower_type="lattice_tower",
        tower_height_m=30,
        sector_count=3,
        antenna_install_height_m=24,
        azimuths_deg=[0, 120, 240],
        detail_level="high",
    )
    registry = AssetRegistry(Path("assets/manifests"))
    tower = registry.select_tower("lattice_tower", "5G", 30)
    antenna = registry.select_asset("antenna", "5G", "lattice_tower")
    radio = registry.select_asset("radio", "5G", "lattice_tower")
    scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_cache_validation",
        requirements=requirements,
        tower=tower,
        antenna=antenna,
        radio=radio,
    )
    return requirements, scene, [tower, antenna, radio]
