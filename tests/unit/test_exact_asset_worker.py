import hashlib
import json

import pytest

from apps.blender_worker.exact_asset import validate_exact_program


def _fixture(tmp_path):
    manifest_dir = tmp_path / "assets/manifests"
    manifest_dir.mkdir(parents=True)
    asset = tmp_path / "assets/panel.glb"
    asset.write_bytes(b"test admission bytes only, not a renderable GLB")
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    manifest = {
        "asset_id": "panel",
        "file": "assets/panel.glb",
        "status": "validated",
        "cognitive_reuse_enabled": True,
        "import_fallback_allowed": False,
        "compatibility_rules": {"compatible_roles": ["antenna"]},
        "qualification": {
            "status": "qualified_for_generation",
            "units": "meters",
            "allowed_generation_modes": ["imported_glb_exact"],
            "verified_file_sha256": digest,
            "mesh_integrity_verified": True,
            "dimensions_verified": True,
            "pivot_verified": True,
            "orientation_verified": True,
        },
        "dimensions_m": {"width": 1, "depth": 1, "height": 2},
        "transform_permissions": {
            "translation_axes": ["x", "y", "z"],
            "rotation_axes": ["z"],
            "maximum_translation_m": 100,
            "maximum_rotation_deg": 360,
        },
    }
    path = manifest_dir / "panel.json"
    path.write_text(json.dumps(manifest))
    node = {
        "kind": "exact_asset",
        "node_id": "asset",
        "asset_id": "panel",
        "asset_file": "assets/panel.glb",
        "asset_sha256": digest,
        "manifest_file_name": path.name,
        "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_dimensions_m": {"x": 1, "y": 1, "z": 2},
    }
    program = {
        "nodes": [node],
        "requested_quantity": 1,
        "semantic_role": "antenna",
        "authorship": "deterministic_generated",
    }
    return program, manifest, path


def test_exact_worker_validates_pinned_sources(tmp_path):
    program, _, _ = _fixture(tmp_path)
    evidence = validate_exact_program(program, tmp_path)
    assert evidence[0]["asset_id"] == "panel"
    assert all(str(tmp_path) not in str(value) for value in evidence[0].values())


@pytest.mark.parametrize(
    "change,error",
    [
        ("scale", "SCALE"),
        ("parent", "PARENT"),
        ("dimensions", "DIMENSIONS"),
        ("role", "QUALIFICATION"),
        ("manifest_hash", "MANIFEST_HASH"),
        ("asset_hash", "FILE_HASH"),
        ("quantity", "SCOPE"),
        ("rotation", "TRANSFORM"),
    ],
)
def test_exact_worker_rejects_untrusted_changes(tmp_path, change, error):
    program, _, _ = _fixture(tmp_path)
    node = program["nodes"][0]
    if change == "scale":
        node["transform"] = {"scale": {"x": 2}}
    if change == "parent":
        node["parent_id"] = "other"
    if change == "dimensions":
        node["source_dimensions_m"]["x"] = 4
    if change == "role":
        program["semantic_role"] = "chair"
    if change == "manifest_hash":
        node["manifest_sha256"] = "0" * 64
    if change == "asset_hash":
        node["asset_sha256"] = "0" * 64
    if change == "quantity":
        program["requested_quantity"] = 2
    if change == "rotation":
        node["transform"] = {"rotation_deg": {"x": 20}}
    with pytest.raises(ValueError, match=error):
        validate_exact_program(program, tmp_path)


def test_exact_worker_rejects_revoked_optin_even_with_new_pin(tmp_path):
    program, manifest, path = _fixture(tmp_path)
    manifest["cognitive_reuse_enabled"] = False
    path.write_text(json.dumps(manifest))
    program["nodes"][0]["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="QUALIFICATION"):
        validate_exact_program(program, tmp_path)


@pytest.mark.parametrize(
    "field",
    ["mesh_integrity_verified", "dimensions_verified", "pivot_verified", "orientation_verified"],
)
def test_exact_worker_rechecks_each_qualification_flag(tmp_path, field):
    program, manifest, path = _fixture(tmp_path)
    manifest["qualification"][field] = False
    path.write_text(json.dumps(manifest))
    program["nodes"][0]["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="QUALIFICATION"):
        validate_exact_program(program, tmp_path)


@pytest.mark.parametrize("field", ["transform_permissions", "import_fallback_allowed"])
def test_exact_worker_requires_explicit_import_contract(tmp_path, field):
    program, manifest, path = _fixture(tmp_path)
    del manifest[field]
    path.write_text(json.dumps(manifest))
    program["nodes"][0]["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="PERMISSIONS_MISSING|QUALIFICATION"):
        validate_exact_program(program, tmp_path)


def test_exact_worker_rejects_changed_asset_bytes(tmp_path):
    program, _, _ = _fixture(tmp_path)
    (tmp_path / "assets/panel.glb").write_bytes(b"changed source")
    with pytest.raises(ValueError, match="FILE_HASH"):
        validate_exact_program(program, tmp_path)
