import json
import sqlite3
import threading
from dataclasses import dataclass, replace
from pathlib import Path

from core.agents.scene_planner import ScenePlanner
from core.contracts.memory import MemoryIndexResult
from core.contracts.requirements import RequirementSpec
from core.contracts.validation import ValidationIssue, ValidationReport
from core.memory import MemoryService
from core.rag import RagService
from core.services.asset_registry import AssetRegistry


@dataclass(frozen=True)
class _GenerationResult:
    status: str
    mode: str
    blender_available: bool
    duration_ms: int
    artifacts: dict[str, str]

    def model_copy(self, *, update: dict) -> "_GenerationResult":
        return replace(self, **update)


def test_memory_index_diagnostics_are_isolated_per_thread(tmp_path: Path) -> None:
    service = MemoryService(tmp_path / "thread-local.db")
    barrier = threading.Barrier(2)
    observed: dict[str, str] = {}

    def set_and_read(name: str) -> None:
        service.last_index_result = MemoryIndexResult(status=name)
        barrier.wait(timeout=5)
        observed[name] = service.last_index_result.status

    threads = [threading.Thread(target=set_and_read, args=(name,)) for name in ("first", "second")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert observed == {"first": "first", "second": "second"}
    assert service.last_index_result.status == "not_indexed"
    assert service.index_health()["latest_index_result"]["status"] in {"first", "second"}


def test_memory_writeback(tmp_path: Path) -> None:
    service = MemoryService(tmp_path / "telecom_memory.db")
    requirements, scene, report, generation = _memory_inputs("wf_memory")

    summary = service.write_workflow_summary(
        workflow_id="wf_memory",
        requirements=requirements,
        scene=scene,
        report=report,
        generation=generation,
        scene_spec_path=tmp_path / "scene_spec.json",
        validation_report_path=tmp_path / "validation_report.json",
    )

    assert summary is not None
    assert summary.validation_report_path.endswith("validation_report.json")
    with sqlite3.connect(tmp_path / "telecom_memory.db") as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT workflow_id, network_type, tower_type, sector_count, generation_mode,
                   qa_score, warnings_json, scene_spec_path, validation_report_path,
                   reusable_pattern, created_at
            FROM workflow_memory
            WHERE workflow_id = ?
            """,
            ("wf_memory",),
        ).fetchone()
    payload = dict(row)
    assert payload["workflow_id"] == "wf_memory"
    assert payload["network_type"] == "5G"
    assert payload["tower_type"] == "lattice_tower"
    assert payload["sector_count"] == 3
    assert payload["generation_mode"] == "fallback_no_blender"
    assert payload["qa_score"] == 1.0
    assert json.loads(payload["warnings_json"])[0]["code"] == "FALLBACK_GENERATION"
    assert payload["scene_spec_path"].endswith("scene_spec.json")
    assert payload["validation_report_path"].endswith("validation_report.json")
    assert payload["reusable_pattern"] == 0
    assert summary.reusable_pattern is False
    assert payload["created_at"] > 0


def test_memory_recall(tmp_path: Path) -> None:
    service = MemoryService(tmp_path / "telecom_memory.db")
    requirements, scene, report, generation = _memory_inputs("wf_reusable")
    report = report.model_copy(update={"warnings": []})
    generation = _real_generation()
    different_sector_requirements = requirements.model_copy(
        update={"sector_count": 2, "azimuths_deg": [0, 180]}
    )
    different_scene = ScenePlanner().build_scene_spec(
        workflow_id="wf_different_sector",
        requirements=different_sector_requirements,
        tower=AssetRegistry(Path("assets/manifests")).select_tower("lattice_tower", "5G", 30),
        antenna=AssetRegistry(Path("assets/manifests")).select_asset(
            "antenna", "5G", "lattice_tower"
        ),
        radio=AssetRegistry(Path("assets/manifests")).select_asset("radio", "5G", "lattice_tower"),
    )

    service.write_workflow_summary(
        workflow_id="wf_reusable",
        requirements=requirements,
        scene=scene,
        report=report,
        generation=generation,
        scene_spec_path=tmp_path / "wf_reusable_scene.json",
        validation_report_path=tmp_path / "wf_reusable_validation.json",
    )
    service.write_workflow_summary(
        workflow_id="wf_different_sector",
        requirements=different_sector_requirements,
        scene=different_scene,
        report=report,
        generation=generation,
        scene_spec_path=tmp_path / "wf_different_scene.json",
        validation_report_path=tmp_path / "wf_different_validation.json",
    )

    recall = service.recall(requirements)
    assert recall.memory_hits == 1
    assert recall.memory_context_count == 1
    assert [row["workflow_id"] for row in recall.similar_workflows] == ["wf_reusable"]
    assert recall.similar_workflows[0]["reusable_pattern"] is True
    assert "scene_spec_path" not in recall.similar_workflows[0]
    assert "validation_report_path" not in recall.similar_workflows[0]


def test_memory_init_invalidates_legacy_fallback_reusable_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "telecom_memory.db"
    service = MemoryService(db_path)
    requirements, scene, report, generation = _memory_inputs("wf_legacy_fallback")
    service.write_workflow_summary(
        workflow_id="wf_legacy_fallback",
        requirements=requirements,
        scene=scene,
        report=report,
        generation=generation,
        scene_spec_path=tmp_path / "scene.json",
        validation_report_path=tmp_path / "validation.json",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE workflow_memory SET reusable_pattern = 1 WHERE workflow_id = ?",
            ("wf_legacy_fallback",),
        )

    reloaded = MemoryService(db_path)

    with sqlite3.connect(db_path) as conn:
        reusable = conn.execute(
            "SELECT reusable_pattern FROM workflow_memory WHERE workflow_id = ?",
            ("wf_legacy_fallback",),
        ).fetchone()[0]
    assert reusable == 0
    assert reloaded.recall(requirements).similar_workflows == []


def test_memory_does_not_store_large_artifacts(tmp_path: Path) -> None:
    rag_service = RagService(
        project_root=Path.cwd(),
        qdrant_path=tmp_path / "qdrant",
        embedding_provider_name="deterministic",
    )
    service = MemoryService(tmp_path / "telecom_memory.db", rag_service=rag_service)
    requirements, scene, report, generation = _memory_inputs("wf_no_large_outputs")
    generation = _real_generation().model_copy(
        update={
            "artifacts": {
                "glb": str(tmp_path / "design.glb"),
                "preview": str(tmp_path / "preview.png"),
                "download": str(tmp_path / "artifacts.zip"),
            }
        }
    )

    service.write_workflow_summary(
        workflow_id="wf_no_large_outputs",
        requirements=requirements,
        scene=scene,
        report=report,
        generation=generation,
        scene_spec_path=tmp_path / "scene_spec.json",
        validation_report_path=tmp_path / "validation_report.json",
    )

    with sqlite3.connect(tmp_path / "telecom_memory.db") as conn:
        sqlite_dump = "\n".join(conn.iterdump())
    qdrant_results = rag_service.search(
        query="wf_no_large_outputs 5G lattice",
        collection="design_memory",
        limit=1,
    )
    indexed_dump = json.dumps(
        [result.model_dump() for result in qdrant_results],
        ensure_ascii=False,
    )
    for forbidden in ["design.glb", "preview.png", "artifacts.zip"]:
        assert forbidden not in sqlite_dump
        assert forbidden not in indexed_dump
    assert str(tmp_path) not in indexed_dump
    assert service.last_index_result.status == "indexed"
    assert service.last_index_result.indexed_collections["design_memory"] == 1


def test_failed_workflow_is_diagnostic_only_and_issues_are_deduplicated(tmp_path: Path) -> None:
    rag_service = RagService(
        project_root=Path.cwd(),
        qdrant_path=tmp_path / "qdrant",
        embedding_provider_name="deterministic",
    )
    service = MemoryService(tmp_path / "telecom_memory.db", rag_service=rag_service)
    requirements, scene, report, generation = _memory_inputs("wf_failed_memory")
    duplicate = ValidationIssue(
        code="BLENDER_FALLBACK_USED",
        message="Blender fallback is not reusable.",
        severity="warning",
    )
    report = report.model_copy(
        update={
            "status": "failed",
            "score": 0.4,
            "warnings": [duplicate, duplicate],
        }
    )

    summary = service.write_workflow_summary(
        workflow_id="wf_failed_memory",
        requirements=requirements,
        scene=scene,
        report=report,
        generation=generation,
        scene_spec_path=tmp_path / "scene_spec.json",
        validation_report_path=tmp_path / "validation_report.json",
    )

    assert summary is not None
    assert summary.reusable_pattern is False
    assert len(summary.warnings) == 1
    assert service.stats()["design_memory_count"] == 0
    assert service.stats()["error_memory_count"] == 1
    assert service.last_index_result.indexed_collections["design_memory"] == 0
    assert service.last_index_result.indexed_collections["error_memory"] == 1


def _memory_inputs(
    workflow_id: str,
) -> tuple[RequirementSpec, object, ValidationReport, _GenerationResult]:
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
        workflow_id=workflow_id,
        requirements=requirements,
        tower=tower,
        antenna=antenna,
        radio=radio,
    )
    report = ValidationReport(
        design_id=workflow_id,
        status="passed",
        score=1.0,
        checks={"qa": True},
        warnings=[
            ValidationIssue(
                code="FALLBACK_GENERATION",
                message="Fallback generation used.",
                severity="warning",
            )
        ],
    )
    generation = _GenerationResult(
        status="fallback",
        mode="fallback_no_blender",
        blender_available=False,
        duration_ms=1,
        artifacts={},
    )
    return requirements, scene, report, generation


def _real_generation() -> _GenerationResult:
    return _GenerationResult(
        status="generated",
        mode="real_blender",
        blender_available=True,
        duration_ms=1,
        artifacts={},
    )
