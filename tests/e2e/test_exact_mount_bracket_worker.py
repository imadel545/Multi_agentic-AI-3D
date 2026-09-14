"""Real Blender regression for a test-only, exact imported mounting bracket."""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from apps.blender_worker.generate_scene import _validate_exact_mount_bracket_connections
from core.agents.scene_planner import ScenePlanner
from core.contracts.requirements import RequirementSpec
from core.qa.assembly_constraint_inspector import _node_matrix
from core.services.assembly_planner import AssetAssemblyPlanner
from core.services.asset_registry import AssetRegistry
from core.services.blender_runner import BlenderRunner
from core.services.requirement_parser import parse_requirements_text

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_exact_mount_rejects_operation_resolved_support_geometry() -> None:
    scene = {
        "assembly_plan": {
            "operations": [
                {
                    "connection_id": "radio-to-mount",
                    "target_anchor": {
                        "anchor_id": "radio_rail",
                        "placement_policy": "resolved_from_operation",
                    },
                    "instances": [{"instance_id": "S1"}],
                }
            ]
        }
    }

    with pytest.raises(
        RuntimeError,
        match="EXACT_MOUNT_BRACKET_RESOLVED_SUPPORT_UNSUPPORTED:BRACKET_TEST:S1",
    ):
        _validate_exact_mount_bracket_connections(
            scene,
            sector_id="S1",
            asset_id="BRACKET_TEST",
        )


@pytest.mark.blender_runtime
def test_exact_mount_preserves_source_and_measures_fixed_relations(tmp_path: Path) -> None:
    blender_path = BlenderRunner(PROJECT_ROOT)._resolve_blender_binary()
    if blender_path is None:
        pytest.skip("qualified Blender runtime unavailable")

    isolated_root = _copy_isolated_worker_inputs(tmp_path)
    source_path, source_dimensions = _create_control_source(
        blender_path,
        isolated_root / "assets" / "brackets" / "mounting_bracket_001.glb",
        tmp_path,
    )
    _qualify_isolated_mount(isolated_root, source_path, source_dimensions)
    scene = _build_mount_only_scene(
        isolated_root,
        expected_mount_strategy="imported_glb_exact",
    )
    mount_operation = next(
        operation
        for operation in scene.assembly_plan.operations
        if operation.connection_id == "mount-to-support"
    )
    mount_instance = mount_operation.instances[0]

    output_dir = tmp_path / "output"
    result = BlenderRunner(project_root=isolated_root, timeout_s=180).generate(
        scene,
        output_dir,
    )

    assert result.status == "generated", result.error
    assert result.mode == "real_blender"
    metadata = json.loads((output_dir / "scene_metadata.json").read_text(encoding="utf-8"))
    mount_records = [
        record for record in metadata["asset_imports"] if record["object_role"] == "mount_bracket"
    ]
    assert len(mount_records) == 1
    record = mount_records[0]
    assert record["asset_import_success"] is True
    assert record["effective_geometry_source"] == "imported_glb_exact"
    assert record["import_fallback_allowed"] is False
    assert record["asset_dimensions_checked"] is True
    assert record["scale_factors"] == [1.0, 1.0, 1.0]
    assert record["generated_object_count"] == 0

    proofs = json.loads((output_dir / "component_proofs.json").read_text(encoding="utf-8"))
    mount_proof = next(
        component for component in proofs["components"] if component["role_id"] == "antenna_mount"
    )
    assert mount_proof["strategy"] == "reuse"
    assert mount_proof["generation_strategy"] == "imported_glb_exact"
    assert mount_proof["qa"]["passed"] is True
    instance_proof = mount_proof["instances"][0]
    assert instance_proof["geometry_source"] == "imported_glb_exact"
    assert instance_proof["mesh_object_count"] == 2
    assert instance_proof["transform"]["translation_m"] == pytest.approx(
        mount_instance.translation_m,
        abs=1e-6,
    )
    assert instance_proof["transform"]["rotation_deg"] == pytest.approx(
        mount_instance.rotation_deg,
        abs=1e-5,
    )
    assert instance_proof["transform"]["scale"] == [1.0, 1.0, 1.0]

    source_document, source_binary = _read_glb(source_path)
    output_document, output_binary = _read_glb(output_dir / "design.glb")
    source_chain = _linear_chain(source_document, set(range(len(source_document["nodes"]))))
    bracket_indices = {
        index
        for index, node in enumerate(output_document["nodes"])
        if (node.get("extras") or {}).get("semantic_root") == "mount_bracket_S1"
    }
    output_chain = _linear_chain(output_document, bracket_indices)
    assert len(output_chain) == len(source_chain) + 1
    assert "mesh" not in output_document["nodes"][output_chain[0]]
    for source_index, output_index in zip(source_chain, output_chain[1:], strict=True):
        for source_row, output_row in zip(
            _node_matrix(source_document["nodes"][source_index]),
            _node_matrix(output_document["nodes"][output_index]),
            strict=True,
        ):
            assert output_row == pytest.approx(source_row, abs=1e-6)

    source_vertices, source_materials = _mesh_payload(
        source_document,
        source_binary,
        set(source_chain),
    )
    output_vertices, output_materials = _mesh_payload(
        output_document,
        output_binary,
        bracket_indices,
    )
    assert len(output_vertices) == len(source_vertices)
    for source_vertex, output_vertex in zip(source_vertices, output_vertices, strict=True):
        assert output_vertex == pytest.approx(source_vertex, abs=1e-6)
    assert output_materials == source_materials

    constraints = json.loads((output_dir / "constraint_evidence.json").read_text(encoding="utf-8"))
    assert constraints["status"] == "passed"
    assert constraints["expected_measurement_count"] == 2
    assert constraints["measured_constraint_count"] == 2
    assert constraints["failed_constraint_count"] == 0
    assert {measurement["connection_id"] for measurement in constraints["measurements"]} == {
        "mount-to-support",
        "antenna-to-mount",
    }
    measurements = {
        measurement["connection_id"]: measurement for measurement in constraints["measurements"]
    }
    assert all(
        measurement["passed"] is True
        and measurement["position_error_m"] <= measurement["position_tolerance_m"]
        for measurement in measurements.values()
    )
    assert measurements["mount-to-support"]["source_frame"]["source"] == "glb_fixed_anchor"
    assert measurements["mount-to-support"]["source_frame"]["gltf_node_name"] == "mount_bracket_S1"
    assert measurements["antenna-to-mount"]["target_frame"]["source"] == "glb_fixed_anchor"
    assert measurements["antenna-to-mount"]["target_frame"]["gltf_node_name"] == "mount_bracket_S1"


@pytest.mark.blender_runtime
def test_parametric_mount_without_radio_reaches_real_blender(tmp_path: Path) -> None:
    if BlenderRunner(PROJECT_ROOT)._resolve_blender_binary() is None:
        pytest.skip("qualified Blender runtime unavailable")

    isolated_root = _copy_isolated_worker_inputs(tmp_path)
    scene = _build_mount_only_scene(
        isolated_root,
        expected_mount_strategy="internal_project_generated",
    )
    output_dir = tmp_path / "parametric-output"

    result = BlenderRunner(project_root=isolated_root, timeout_s=180).generate(
        scene,
        output_dir,
    )

    assert result.status == "generated", result.error
    assert result.mode == "real_blender"
    metadata = json.loads((output_dir / "scene_metadata.json").read_text(encoding="utf-8"))
    mount_records = [
        record for record in metadata["asset_imports"] if record["object_role"] == "mount_bracket"
    ]
    assert len(mount_records) == 1
    assert mount_records[0]["generation_success"] is True
    assert mount_records[0]["effective_geometry_source"] == "internal_project_generated"
    constraints = json.loads((output_dir / "constraint_evidence.json").read_text(encoding="utf-8"))
    assert constraints["status"] == "passed"
    assert constraints["expected_measurement_count"] == 2
    assert constraints["failed_constraint_count"] == 0


def _copy_isolated_worker_inputs(tmp_path: Path) -> Path:
    root = tmp_path / "isolated-project"
    shutil.copytree(PROJECT_ROOT / "apps" / "blender_worker", root / "apps" / "blender_worker")
    service_dir = root / "core" / "services"
    service_dir.mkdir(parents=True)
    shutil.copy2(
        PROJECT_ROOT / "core" / "services" / "professional_asset_worker_gate.py",
        service_dir / "professional_asset_worker_gate.py",
    )
    shutil.copytree(PROJECT_ROOT / "assets" / "manifests", root / "assets" / "manifests")
    shutil.copytree(
        PROJECT_ROOT / "assets" / "capabilities",
        root / "assets" / "capabilities",
    )
    return root


def _create_control_source(
    blender_path: Path,
    asset_path: Path,
    tmp_path: Path,
) -> tuple[Path, dict[str, float]]:
    asset_path.parent.mkdir(parents=True)
    dimensions_path = tmp_path / "source_dimensions.json"
    script_path = tmp_path / "create_exact_mount_source.py"
    script_path.write_text(
        """
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

asset_path = Path(sys.argv[sys.argv.index('--') + 1])
dimensions_path = Path(sys.argv[sys.argv.index('--') + 2])
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

root = bpy.data.objects.new('control_source_root', None)
bpy.context.collection.objects.link(root)

def cube(name, dimensions, color):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    material = bpy.data.materials.new(f'{name}_material')
    material.diffuse_color = color
    obj.data.materials.append(material)
    return obj

arm = cube('control_arm', (0.8, 0.1, 0.1), (0.2, 0.3, 0.4, 1.0))
arm.parent = root
clamp = cube('control_clamp', (0.18, 0.18, 0.18), (0.7, 0.35, 0.1, 1.0))
clamp.parent = arm
clamp.location = (0.3, 0.0, 0.0)
clamp.rotation_euler = (0.2, 0.0, 0.15)
bpy.context.view_layer.update()

objects = [arm, clamp]
corners = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
minimum = [min(float(corner[index]) for corner in corners) for index in range(3)]
maximum = [max(float(corner[index]) for corner in corners) for index in range(3)]
dimensions = [maximum[index] - minimum[index] for index in range(3)]
dimensions_path.write_text(json.dumps({
    'width': dimensions[0],
    'depth': dimensions[1],
    'height': dimensions[2],
}))
bpy.ops.export_scene.gltf(filepath=str(asset_path), export_format='GLB')
""".strip()
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            str(blender_path),
            "--background",
            "--factory-startup",
            "--python-exit-code",
            "97",
            "--python",
            str(script_path),
            "--",
            str(asset_path),
            str(dimensions_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return asset_path, json.loads(dimensions_path.read_text(encoding="utf-8"))


def _qualify_isolated_mount(
    root: Path,
    source_path: Path,
    dimensions: dict[str, float],
) -> None:
    manifest_path = root / "assets" / "manifests" / "MOUNTING_BRACKET_001.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dimensions_m"] = dimensions
    manifest["height_m"] = dimensions["height"]
    manifest["import_fallback_allowed"] = False
    manifest["transform_permissions"] = {
        "translation_axes": ["x", "y", "z"],
        "rotation_axes": ["x", "y", "z"],
        "maximum_translation_m": 150.0,
        "maximum_rotation_deg": 360.0,
        "uniform_scale_allowed": False,
        "non_uniform_scale_allowed": False,
    }
    qualification = manifest["qualification"]
    qualification.update(
        {
            "allowed_generation_modes": ["imported_glb_exact"],
            "verified_file_sha256": _sha256(source_path),
            "mesh_integrity_verified": True,
            "dimensions_verified": True,
            "pivot_verified": True,
            "orientation_verified": True,
            "qualification_method": "Isolated Blender runtime regression fixture.",
            "limitations": [
                "Test-only controlled geometry; no product asset or professional claim."
            ],
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _build_mount_only_scene(root: Path, *, expected_mount_strategy: str):
    registry = AssetRegistry(root / "assets" / "manifests")
    parsed = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 1 secteur à 24m. Azimut : 0°."
    )
    requirements = RequirementSpec.model_validate(
        {
            **parsed.model_dump(mode="json"),
            "include_rru": False,
            "include_cables": False,
            "include_beams": False,
            "include_labels": False,
            "include_power_cabinet": False,
            "include_gps_antenna": False,
        }
    )
    planning = AssetAssemblyPlanner(registry).plan(
        workflow_id="wf_exact_mount_control",
        requirements=requirements,
    )
    strategies = {
        component.role_id: component.generation_strategy for component in planning.plan.components
    }
    assert strategies["support_structure"] == "internal_project_generated"
    assert strategies["sector_antenna"] == "internal_project_generated"
    assert strategies["antenna_mount"] == expected_mount_strategy
    return ScenePlanner().build_scene_spec(
        "wf_exact_mount_control",
        requirements,
        planning.assets_by_role["support_structure"],
        planning.assets_by_role["sector_antenna"],
        None,
        [],
        planning_resolution={
            "antenna_install_height_m": requirements.antenna_install_height_m,
            "beamwidth_deg": requirements.beamwidth_deg,
            "mechanical_tilt_deg": requirements.mechanical_tilt_deg,
            "electrical_tilt_deg": requirements.electrical_tilt_deg,
            "include_cables": False,
            "include_sector_beams": False,
            "decisions": [],
        },
        assembly_plan=planning.plan,
    )


def _read_glb(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    json_length = struct.unpack_from("<I", raw, 12)[0]
    document = json.loads(raw[20 : 20 + json_length])
    binary_start = 20 + json_length + 8
    return document, raw[binary_start:]


def _linear_chain(document: dict, selected: set[int]) -> list[int]:
    parents = {
        child: parent
        for parent, node in enumerate(document["nodes"])
        for child in node.get("children", [])
    }
    roots = [index for index in selected if parents.get(index) not in selected]
    assert len(roots) == 1
    chain = [roots[0]]
    while True:
        children = [
            child for child in document["nodes"][chain[-1]].get("children", []) if child in selected
        ]
        if not children:
            return chain
        assert len(children) == 1
        chain.append(children[0])


def _mesh_payload(
    document: dict,
    binary: bytes,
    node_indices: set[int],
) -> tuple[list[tuple[float, float, float]], list[str]]:
    vertices: list[tuple[float, float, float]] = []
    material_indices: set[int] = set()
    for node_index in sorted(node_indices):
        mesh_index = document["nodes"][node_index].get("mesh")
        if mesh_index is None:
            continue
        for primitive in document["meshes"][mesh_index]["primitives"]:
            accessor = document["accessors"][primitive["attributes"]["POSITION"]]
            assert accessor["componentType"] == 5126 and accessor["type"] == "VEC3"
            view = document["bufferViews"][accessor["bufferView"]]
            offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            stride = view.get("byteStride", 12)
            vertices.extend(
                struct.unpack_from("<fff", binary, offset + index * stride)
                for index in range(accessor["count"])
            )
            if "material" in primitive:
                material_indices.add(primitive["material"])
    materials = sorted(
        json.dumps(document["materials"][index].get("pbrMetallicRoughness", {}), sort_keys=True)
        for index in material_indices
    )
    return sorted(vertices), materials


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
