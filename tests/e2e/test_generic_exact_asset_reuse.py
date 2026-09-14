"""Controlled cognitive decision, real catalog evidence and real Blender execution."""

import json
import struct
from pathlib import Path

import pytest

from core.agents.requirement_extractor import RequirementExtractor
from core.contracts.cognitive_design import CognitiveDesignPlan
from core.orchestration import DesignOrchestrator
from core.qa.assembly_constraint_inspector import _world_matrices
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner
from core.services.qualified_asset_retriever import QualifiedAssetCandidateRetriever
from tests.unit.test_cognitive_runtime_integration import FakeCognitivePlanner, GenericRoute


class CatalogReusePlanner:
    def __init__(self, registry):
        self.retriever = QualifiedAssetCandidateRetriever(registry)

    def plan(self, *, workflow_id, request):
        payload = (
            FakeCognitivePlanner()
            .plan(workflow_id=workflow_id, request=request)
            .model_dump(mode="json")
        )
        component = payload["component_graph"]["components"][0]
        component.update(
            semantic_role="antenna",
            description="Reuse the qualified panel antenna without deformation.",
            target_dimensions_m={"x": 0.42, "y": 0.169, "z": 1.4},
            minimum_detail_parts=1,
            material_intent=[],
        )
        candidates = self.retriever.search(component)
        selected = next(
            candidate for candidate in candidates if candidate.candidate_id == "ANT_PANEL_4G_001"
        )
        assert "reuse" in selected.allowed_strategies
        decision = payload["asset_decision_plan"]["decisions"][0]
        decision.update(
            strategy="reuse",
            candidates=[selected.model_dump(mode="json")],
            selected_candidate_ids=[selected.candidate_id],
            required_capability_ids=[],
            placement={"translation_m": {"x": 0, "y": 0, "z": 1}},
            rationale="Qualified source reused with explicit placement and unchanged materials.",
        )
        return CognitiveDesignPlan.model_validate(payload)


class CompleteTelecomSiteReusePlanner:
    def __init__(self, registry):
        self.retriever = QualifiedAssetCandidateRetriever(registry)

    def plan(self, *, workflow_id, request):
        payload = (
            FakeCognitivePlanner()
            .plan(workflow_id=workflow_id, request=request)
            .model_dump(mode="json")
        )
        component = payload["component_graph"]["components"][0]
        component.update(
            semantic_role="telecom_site",
            description=(
                "Reuse one complete telecom site template with its installed equipment "
                "without decomposition or deformation."
            ),
            target_dimensions_m={"x": 7.147688, "y": 8.096867, "z": 30.0},
            minimum_detail_parts=1,
            material_intent=[],
        )
        candidates = self.retriever.search(component)
        selected = next(
            candidate
            for candidate in candidates
            if candidate.candidate_id == "TELECOM_SITE_TEMPLATE_CC_BY_001"
        )
        assert "reuse" in selected.allowed_strategies
        decision = payload["asset_decision_plan"]["decisions"][0]
        decision.update(
            strategy="reuse",
            candidates=[selected.model_dump(mode="json")],
            selected_candidate_ids=[selected.candidate_id],
            required_capability_ids=[],
            placement={"translation_m": {"x": 0, "y": 0, "z": 0}},
            rationale=(
                "Reuse the admitted complete site as one unchanged exact asset; its "
                "embedded equipment is not selected as separate components."
            ),
        )
        return CognitiveDesignPlan.model_validate(payload)


@pytest.mark.blender_runtime
def test_generic_exact_reuse_reaches_real_blender_certificate(tmp_path):
    registry = AssetRegistry(Path("assets/manifests"))
    orchestrator = DesignOrchestrator(
        registry=registry,
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        blender_runner=BlenderRunner(project_root=Path.cwd()),
        design_domain_router=GenericRoute(),
        cognitive_design_planner=CatalogReusePlanner(registry),
        geometry_program_planner=None,
        allow_blender_fallback=False,
    )
    result = orchestrator.run(
        workflow_id="wf_exact_reuse_001",
        requirements_text="Place a qualified antenna panel at one metre.",
        detail_level="high",
        output_dir=tmp_path,
        use_llm=True,
    )
    assert result.status == "completed", result.report.errors
    assert result.scene.tower is None and result.scene.sectors == []
    assert result.scene.geometry_programs[0].nodes[0].kind == "exact_asset"
    assert result.generation.mode == "real_blender"
    assert result.completion_certificate.schema_version == "1.3.0"
    assert result.completion_certificate.status == "issued"
    proofs = json.loads((tmp_path / "component_proofs.json").read_text())
    proof = proofs["geometry_programs"][0]
    assert proof["strategy"] == "reuse"
    assert proof["generation_strategy"] == "imported_glb_exact"
    assert proof["asset_id"] == "ANT_PANEL_4G_001"
    assert proof["qa"]["passed"] is True
    assert proof["bounding_box_m"]["dimensions_m"] == pytest.approx([0.42, 0.169, 1.4], abs=0.001)
    metadata = json.loads((tmp_path / "scene_metadata.json").read_text())
    record = metadata["asset_imports"][0]
    assert record["asset_id"] == "ANT_PANEL_4G_001"
    assert record["asset_import_success"] is True
    assert record["import_fallback_allowed"] is False
    assert record["scale_factors"] == [1, 1, 1]
    source_vertices, source_materials = _mesh_payload(Path("assets/antennas/ant_panel_4g_001.glb"))
    output_vertices, output_materials = _mesh_payload(tmp_path / "design.glb")
    assert len(output_vertices) == len(source_vertices)
    for source, output in zip(source_vertices, output_vertices, strict=True):
        assert output == pytest.approx(source, abs=1e-6)
    assert output_materials == source_materials
    source_world = _mesh_world_transforms(Path("assets/antennas/ant_panel_4g_001.glb"))
    output_world = _mesh_world_transforms(tmp_path / "design.glb")
    assert output_world.keys() == source_world.keys()
    for name, matrix in source_world.items():
        expected = [list(row) for row in matrix]
        # glTF exports Blender Z-up placement as a translation along glTF Y.
        expected[1][3] += 1
        for actual_row, expected_row in zip(output_world[name], expected, strict=True):
            assert actual_row == pytest.approx(expected_row, abs=1e-6)
    lock = json.loads((tmp_path / "build.lock.json").read_text())
    assert lock["trusted_inputs"]["exact_assets"][0]["asset_id"] == "ANT_PANEL_4G_001"
    assert (
        lock["trusted_inputs"]["manifests"][0]["source_sha256"]
        == proof["exact_asset_sources"][0]["manifest_sha256"]
    )


@pytest.mark.blender_runtime
def test_complete_telecom_site_template_reuse_reaches_real_blender_certificate(tmp_path):
    registry = AssetRegistry(Path("assets/manifests"))
    orchestrator = DesignOrchestrator(
        registry=registry,
        extractor=RequirementExtractor(enabled=False),
        rag_service=None,
        blender_runner=BlenderRunner(project_root=Path.cwd(), catalog_only_registry=registry),
        catalog_only_generation=True,
        design_domain_router=GenericRoute(),
        cognitive_design_planner=CompleteTelecomSiteReusePlanner(registry),
        geometry_program_planner=None,
        allow_blender_fallback=False,
    )
    result = orchestrator.run(
        workflow_id="wf_complete_site_reuse_001",
        requirements_text=(
            "Reuse one complete ready-made telecom site template without changing or "
            "decomposing it."
        ),
        detail_level="high",
        output_dir=tmp_path,
        use_llm=True,
    )
    assert result.status == "completed", result.report.errors
    assert result.scene.tower is None and result.scene.sectors == []
    assert result.scene.geometry_programs[0].nodes[0].kind == "exact_asset"
    assert result.generation.mode == "real_blender"
    assert result.qa_report.status == "passed"
    assert result.completion_certificate.schema_version == "1.3.0"
    assert result.completion_certificate.status == "issued"

    proofs = json.loads((tmp_path / "component_proofs.json").read_text())
    proof = proofs["geometry_programs"][0]
    assert proof["strategy"] == "reuse"
    assert proof["generation_strategy"] == "imported_glb_exact"
    assert proof["asset_id"] == "TELECOM_SITE_TEMPLATE_CC_BY_001"
    assert proof["qa"]["passed"] is True
    assert proof["bounding_box_m"]["dimensions_m"] == pytest.approx(
        [7.147688, 8.096867, 30.0], abs=0.001
    )

    metadata = json.loads((tmp_path / "scene_metadata.json").read_text())
    record = metadata["asset_imports"][0]
    assert record["asset_id"] == "TELECOM_SITE_TEMPLATE_CC_BY_001"
    assert record["asset_import_success"] is True
    assert record["import_fallback_allowed"] is False
    assert record["scale_factors"] == [1, 1, 1]

    source_path = Path("assets/towers/tower_lattice_30m.glb")
    source_triangles, source_materials = _triangle_payload(source_path)
    output_triangles, output_materials = _triangle_payload(tmp_path / "design.glb")
    # Blender may split equivalent accessor vertices during a GLB round trip.
    # The rendered mesh remains exact only when every material-bound triangle is
    # identical, independent of that storage detail.
    assert output_triangles == source_triangles
    assert output_materials == source_materials

    source_world = _mesh_world_transforms(source_path)
    output_world = _mesh_world_transforms(tmp_path / "design.glb")
    assert output_world.keys() == source_world.keys()
    for name, matrix in source_world.items():
        for actual_row, expected_row in zip(output_world[name], matrix, strict=True):
            assert actual_row == pytest.approx(expected_row, abs=1e-6)

    lock = json.loads((tmp_path / "build.lock.json").read_text())
    assert lock["trusted_inputs"]["exact_assets"][0]["asset_id"] == (
        "TELECOM_SITE_TEMPLATE_CC_BY_001"
    )
    from copy import deepcopy

    from core.services.scene_versioning import _required_completion_checks, _valid_trusted_inputs

    assert _valid_trusted_inputs(lock, result.scene)
    tampered = deepcopy(lock)
    tampered["trusted_inputs"]["exact_assets"][0]["sha256"] = "0" * 64
    assert not _valid_trusted_inputs(tampered, result.scene)
    required = _required_completion_checks("1.3.0", constraint_evidence_required=False)
    assert set(result.completion_certificate.checks) == required

    assert (
        lock["trusted_inputs"]["manifests"][0]["source_sha256"]
        == (proof["exact_asset_sources"][0]["manifest_sha256"])
    )


def _mesh_world_transforms(path):
    raw = path.read_bytes()
    json_length = struct.unpack_from("<I", raw, 12)[0]
    document = json.loads(raw[20 : 20 + json_length])
    matrices, _ = _world_matrices(document)
    return {
        node["name"]: matrices[index]
        for index, node in enumerate(document["nodes"])
        if "mesh" in node
    }


def _mesh_payload(path):
    raw = path.read_bytes()
    json_length = struct.unpack_from("<I", raw, 12)[0]
    document = json.loads(raw[20 : 20 + json_length])
    binary_offset = 20 + json_length + 8
    vertices = []
    for mesh in document["meshes"]:
        for primitive in mesh["primitives"]:
            accessor = document["accessors"][primitive["attributes"]["POSITION"]]
            assert accessor["componentType"] == 5126 and accessor["type"] == "VEC3"
            view = document["bufferViews"][accessor["bufferView"]]
            offset = binary_offset + view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            stride = view.get("byteStride", 12)
            vertices.extend(
                struct.unpack_from("<fff", raw, offset + i * stride)
                for i in range(accessor["count"])
            )
    materials = sorted(
        json.dumps(material.get("pbrMetallicRoughness", {}), sort_keys=True)
        for material in document.get("materials", [])
    )
    return sorted(vertices), materials


def _triangle_payload(path):
    raw = path.read_bytes()
    json_length = struct.unpack_from("<I", raw, 12)[0]
    document = json.loads(raw[20 : 20 + json_length])
    binary_offset = 20 + json_length + 8

    def values(accessor_index, scalar_format, width):
        accessor = document["accessors"][accessor_index]
        view = document["bufferViews"][accessor["bufferView"]]
        offset = binary_offset + view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        scalar_size = struct.calcsize(scalar_format)
        stride = view.get("byteStride", scalar_size * width)
        return [
            struct.unpack_from(f"<{scalar_format * width}", raw, offset + index * stride)
            for index in range(accessor["count"])
        ]

    triangles = []
    for mesh in document["meshes"]:
        for primitive in mesh["primitives"]:
            assert primitive.get("mode", 4) == 4
            positions = values(primitive["attributes"]["POSITION"], "f", 3)
            index_accessor = document["accessors"][primitive["indices"]]
            index_format = {5121: "B", 5123: "H", 5125: "I"}[index_accessor["componentType"]]
            indices = [value[0] for value in values(primitive["indices"], index_format, 1)]
            assert len(indices) % 3 == 0
            material_index = primitive.get("material", -1)
            triangles.extend(
                (
                    material_index,
                    tuple(sorted(positions[index] for index in indices[offset : offset + 3])),
                )
                for offset in range(0, len(indices), 3)
            )
    materials = sorted(
        json.dumps(material.get("pbrMetallicRoughness", {}), sort_keys=True)
        for material in document.get("materials", [])
    )
    return sorted(triangles), materials
