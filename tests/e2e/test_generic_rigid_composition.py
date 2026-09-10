"""Controlled decisions, real catalog geometry, Blender and exported alignment QA."""

import json
from pathlib import Path

import pytest

from core.agents.requirement_extractor import RequirementExtractor
from core.contracts.cognitive_design import CognitiveDesignPlan
from core.orchestration import DesignOrchestrator
from core.qa.mesh_qa import MeshQA
from core.qa.rigid_relation_inspector import inspect_rigid_relations
from core.services.blender_runner import BlenderRunner
from tests.e2e.test_generic_exact_asset_reuse import _mesh_payload
from tests.unit.test_cognitive_composition import composition_plan
from tests.unit.test_cognitive_runtime_integration import GenericRoute


class CompositionPlanner:
    def __init__(self, payload):
        self.payload = payload

    def plan(self, *, workflow_id, request):
        return CognitiveDesignPlan.model_validate(self.payload)


@pytest.mark.blender_runtime
def test_rigid_composition_changes_exported_geometry_and_certifies(tmp_path):
    import struct

    registry, raw = composition_plan()
    orchestrator = DesignOrchestrator(
        registry=registry,
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        blender_runner=BlenderRunner(project_root=Path.cwd()),
        design_domain_router=GenericRoute(),
        cognitive_design_planner=CompositionPlanner(raw),
        geometry_program_planner=None,
        allow_blender_fallback=False,
    )
    results = []
    for version, offset in (("before", 0.8), ("after", 1.2)):
        raw["component_graph"]["relationships"][0]["parameters"]["offset_world_m"]["x"] = offset
        result = orchestrator.run(
            workflow_id=f"wf_rigid_{version}",
            requirements_text="Align two qualified internal panels.",
            detail_level="high",
            output_dir=tmp_path / version,
            use_llm=True,
        )
        assert result.status == "completed", result.report.errors
        assert result.completion_certificate.status == "issued"
        assert result.generation.mode == "real_blender"
        mesh_report = result.geometry_validation.mesh_qa
        assert any(
            check.name.startswith("rigid_relation:") and check.passed
            for check in mesh_report.checks
        )
        (tmp_path / version / "geometry_validation.json").write_text(
            result.geometry_validation.model_dump_json(indent=2)
        )
        (tmp_path / version / "completion_certificate.json").write_text(
            result.completion_certificate.model_dump_json(indent=2)
        )
        assert result.scene.geometry_programs[1].nodes[0].transform.translation_m.x == offset
        proofs = json.loads((tmp_path / version / "component_proofs.json").read_text())
        assert [p["strategy"] for p in proofs["geometry_programs"]] == ["reuse", "compose"]
        source_vertices, _ = _mesh_payload(Path("assets/antennas/ant_panel_4g_001.glb"))
        output_vertices, _ = _mesh_payload(tmp_path / version / "design.glb")
        assert len(output_vertices) == 2 * len(source_vertices)
        for actual, expected in zip(output_vertices, sorted(source_vertices * 2), strict=True):
            assert actual == pytest.approx(expected, abs=1e-6)
        glb = (tmp_path / version / "design.glb").read_bytes()
        length = struct.unpack_from("<I", glb, 12)[0]
        document = json.loads(glb[20 : 20 + length])
        checks = inspect_rigid_relations(result.scene, document)
        assert checks and all(check.passed for check in checks)
        # A real exported node displaced after generation must fail relation QA.
        source_id = result.scene.rigid_component_relations[0].source_program_id
        node = next(
            n
            for n in document["nodes"]
            if n.get("extras", {}).get("geometry_program_id") == source_id
            and n.get("extras", {}).get("geometry_program_node_id") == "catalog_asset"
        )
        node["translation"][0] += 0.05
        assert not all(check.passed for check in inspect_rigid_relations(result.scene, document))
        encoded = json.dumps(document, separators=(",", ":")).encode()
        encoded += b" " * (-len(encoded) % 4)
        binary_chunk = glb[20 + length :]
        altered = (
            struct.pack("<III", 0x46546C67, 2, 20 + len(encoded) + len(binary_chunk))
            + struct.pack("<II", len(encoded), 0x4E4F534A)
            + encoded
            + binary_chunk
        )
        altered_path = tmp_path / version / "deliberately_displaced.glb"
        altered_path.write_bytes(altered)
        failed_report = MeshQA().validate(altered_path, result.scene)
        assert failed_report.mesh_qa_passed is False
        assert any("RIGID_RELATION" in error for error in failed_report.critical_errors)
        results.append(result)
    assert results[0].scene.geometry_programs[0] == results[1].scene.geometry_programs[0]
    assert results[0].scene.cognitive_plan_sha256 != results[1].scene.cognitive_plan_sha256
