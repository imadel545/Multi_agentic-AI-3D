from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.blender_worker.generate_scene import _antenna_geometry_family
from apps.blender_worker.trusted_assembly import (
    exact_asset_boundary,
    validate_trusted_assembly,
)
from core.agents.scene_planner import ScenePlanner
from core.contracts.assembly import AssemblyPlan, BuilderProfileSnapshot, _canonical_sha256
from core.services.assembly_compiler import resolve_scene_assembly
from core.services.assembly_planner import AssetAssemblyPlanner
from core.services.asset_registry import AssetRegistry
from core.services.builder_registry import BuilderRegistry
from core.services.requirement_parser import parse_requirements_text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFESTS_DIR = PROJECT_ROOT / "assets" / "manifests"
BUILDER_CATALOG = PROJECT_ROOT / "assets" / "capabilities" / "builder_profiles.json"


def test_valid_resolved_plan_passes_independent_worker_boundary() -> None:
    scene = _complete_scene()

    evidence = validate_trusted_assembly(scene, PROJECT_ROOT)

    assert evidence["status"] == "passed"
    assert len(evidence["manifest_snapshots"]) == 7
    assert len(evidence["builder_profiles"]) == 7
    assert len(evidence["operations"]) == 5
    assert [item["asset_id"] for item in evidence["exact_imports"]] == ["GPS_ANTENNA_001"]
    assert all("resolved_asset_path" not in item for item in evidence["exact_imports"])


def test_builder_registry_and_worker_fail_closed_for_absent_or_unknown_builder(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="UNKNOWN_BUILDER_PROFILE:missing_profile"):
        BuilderRegistry(BUILDER_CATALOG).resolve("missing_profile")

    scene = _complete_scene()
    isolated_root = _copy_trust_inputs(tmp_path)
    (isolated_root / "assets" / "capabilities" / "builder_profiles.json").unlink()
    with pytest.raises(RuntimeError, match="BUILDER_PROFILE_CATALOG_INVALID"):
        validate_trusted_assembly(scene, isolated_root)

    unknown_handler = deepcopy(scene)
    builder = unknown_handler["assembly_plan"]["components"][0]["builder_profile"]
    builder["worker_handler"] = "unregistered_worker_handler"
    _rehash(builder, "profile_sha256")
    with pytest.raises(RuntimeError, match="UNKNOWN_BUILDER_HANDLER"):
        validate_trusted_assembly(unknown_handler, PROJECT_ROOT)


def test_worker_rejects_unknown_sector_geometry_family() -> None:
    scene = _complete_scene()
    component = next(
        item for item in scene["assembly_plan"]["components"] if item["role_id"] == "sector_antenna"
    )
    component["builder_profile"]["geometry_family"] = "unregistered_antenna_shape"
    _rehash(component["builder_profile"], "profile_sha256")

    with pytest.raises(RuntimeError, match="UNKNOWN_BUILDER_GEOMETRY_FAMILY"):
        validate_trusted_assembly(scene, PROJECT_ROOT)


def test_builder_profile_contract_accepts_pre_geometry_family_snapshot() -> None:
    payload = {
        "profile_id": "sector_panel_v1",
        "version": "1.0.0",
        "asset_types": ["antenna"],
        "allowed_generation_modes": ["parametric_generated", "imported_glb_exact"],
        "worker_handler": "sector_equipment",
        "instance_strategy": "per_sector",
        "allowed_parameter_ids": ["azimuth_deg", "mechanical_tilt_deg"],
    }
    payload["profile_sha256"] = _canonical_sha256(payload)

    legacy = BuilderProfileSnapshot.model_validate(payload)

    assert legacy.geometry_family is None


@pytest.mark.parametrize("geometry_family", [None, "microwave_dish"])
def test_builder_profile_contract_rejects_legacy_hash_with_explicit_modern_family(
    geometry_family: str | None,
) -> None:
    legacy_payload = {
        "profile_id": "sector_panel_v1",
        "version": "1.0.0",
        "asset_types": ["antenna"],
        "allowed_generation_modes": ["parametric_generated", "imported_glb_exact"],
        "worker_handler": "sector_equipment",
        "instance_strategy": "per_sector",
        "allowed_parameter_ids": ["azimuth_deg", "mechanical_tilt_deg"],
    }
    legacy_hash = _canonical_sha256(legacy_payload)
    modern_payload = {
        **legacy_payload,
        "geometry_family": geometry_family,
        "profile_sha256": legacy_hash,
    }

    with pytest.raises(
        ValueError,
        match=(
            "builder profile snapshot hash mismatch|"
            "sector equipment builders require a geometry family"
        ),
    ):
        BuilderProfileSnapshot.model_validate(modern_payload)


@pytest.mark.parametrize(
    ("network_type", "asset_id", "builder_profile_id", "expected_family"),
    [
        ("MW", "RENAMED_ASSET_WITH_DISH_IN_ITS_NAME", "sector_panel_v1", "panel"),
        (
            "5G",
            "RENAMED_ASSET_WITHOUT_GEOMETRY_HINT",
            "sector_microwave_dish_v1",
            "microwave_dish",
        ),
    ],
)
def test_antenna_geometry_family_is_resolved_from_builder_not_names(
    monkeypatch: pytest.MonkeyPatch,
    network_type: str,
    asset_id: str,
    builder_profile_id: str,
    expected_family: str,
) -> None:
    monkeypatch.chdir(PROJECT_ROOT)
    scene = {"network_type": network_type, "assembly_plan": None}
    sector = {
        "antenna_asset_id": asset_id,
        "antenna_asset_metadata": {"builder_profile_id": builder_profile_id},
    }

    assert _antenna_geometry_family(scene, sector) == expected_family


def test_compiler_rejects_connector_gender_incompatibility() -> None:
    requirements, planning = _declared_plan()
    payload = planning.plan.model_dump(mode="json")
    mount = next(
        component for component in payload["components"] if component["role_id"] == "antenna_mount"
    )
    antenna_rail = next(
        connector
        for connector in mount["manifest_snapshot"]["connectors"]
        if connector["connector_id"] == "antenna_rail"
    )
    antenna_rail["gender"] = "source"
    _rehash(mount["manifest_snapshot"], "snapshot_sha256")
    declared = AssemblyPlan.model_validate(payload)

    with pytest.raises(ValueError, match="ASSEMBLY_CONNECTOR_GENDER_INCOMPATIBLE"):
        _build_scene(requirements, planning.assets_by_role, declared)


def test_worker_rejects_manifest_snapshot_or_authoritative_source_alteration(
    tmp_path: Path,
) -> None:
    scene = _complete_scene()
    changed_snapshot = deepcopy(scene)
    dimensions = changed_snapshot["assembly_plan"]["components"][0]["manifest_snapshot"][
        "dimensions_m"
    ]
    dimensions["width"] += 0.5
    snapshot = changed_snapshot["assembly_plan"]["components"][0]["manifest_snapshot"]
    _rehash(snapshot, "snapshot_sha256")
    with pytest.raises(RuntimeError, match="ASSET_MANIFEST_SNAPSHOT_FIELD_MISMATCH:dimensions_m"):
        validate_trusted_assembly(changed_snapshot, PROJECT_ROOT)

    isolated_root = _copy_trust_inputs(tmp_path)
    validate_trusted_assembly(scene, isolated_root)
    source = isolated_root / "assets" / "manifests" / "GPS_ANTENNA_001.json"
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="ASSET_MANIFEST_SOURCE_HASH_MISMATCH"):
        validate_trusted_assembly(scene, isolated_root)


def test_exact_import_boundary_rejects_wrong_mode() -> None:
    scene = _complete_scene()

    with pytest.raises(RuntimeError, match="EXACT_IMPORT_MODE_NOT_AUTHORIZED"):
        exact_asset_boundary(
            scene,
            role_id="sector_antenna",
            asset_id="ANT_PANEL_5G_001",
            project_root=PROJECT_ROOT,
        )


def test_exact_import_boundary_rejects_missing_transform_permissions(tmp_path: Path) -> None:
    scene = _complete_scene()
    isolated_root = _copy_trust_inputs(tmp_path)
    snapshot, manifest_path, manifest = _exact_gps_inputs(scene, isolated_root)
    snapshot["transform_permissions"] = None
    manifest["transform_permissions"] = None
    _write_manifest_and_rehash_snapshot(manifest_path, manifest, snapshot)

    with pytest.raises(RuntimeError, match="EXACT_IMPORT_TRANSFORM_PERMISSIONS_MISSING"):
        exact_asset_boundary(
            scene,
            role_id="timing_antenna",
            asset_id="GPS_ANTENNA_001",
            project_root=isolated_root,
        )


def test_exact_import_boundary_rejects_asset_hash_mismatch(tmp_path: Path) -> None:
    scene = _complete_scene()
    isolated_root = _copy_trust_inputs(tmp_path)
    snapshot, manifest_path, manifest = _exact_gps_inputs(scene, isolated_root)
    invalid_hash = "0" * 64
    snapshot["verified_file_sha256"] = invalid_hash
    manifest["qualification"]["verified_file_sha256"] = invalid_hash
    _write_manifest_and_rehash_snapshot(manifest_path, manifest, snapshot)

    with pytest.raises(RuntimeError, match="EXACT_IMPORT_ASSET_HASH_MISMATCH"):
        exact_asset_boundary(
            scene,
            role_id="timing_antenna",
            asset_id="GPS_ANTENNA_001",
            project_root=isolated_root,
        )


def test_exact_import_boundary_rejects_replaced_glb(tmp_path: Path) -> None:
    scene = _complete_scene()
    isolated_root = _copy_trust_inputs(tmp_path)
    asset_path = isolated_root / "assets" / "antennas" / "gps_antenna_001.glb"
    asset_path.write_bytes(asset_path.read_bytes() + b"tampered")

    with pytest.raises(RuntimeError, match="EXACT_IMPORT_ASSET_HASH_MISMATCH"):
        exact_asset_boundary(
            scene,
            role_id="timing_antenna",
            asset_id="GPS_ANTENNA_001",
            project_root=isolated_root,
        )


def test_exact_import_boundary_rejects_external_asset_path(tmp_path: Path) -> None:
    scene = _complete_scene()
    isolated_root = _copy_trust_inputs(tmp_path)
    snapshot, manifest_path, manifest = _exact_gps_inputs(scene, isolated_root)
    external_path = str((tmp_path / "outside-catalog.glb").resolve())
    snapshot["asset_file"] = external_path
    manifest["file"] = external_path
    _write_manifest_and_rehash_snapshot(manifest_path, manifest, snapshot)

    with pytest.raises(RuntimeError, match="EXACT_IMPORT_ASSET_PATH_INVALID"):
        exact_asset_boundary(
            scene,
            role_id="timing_antenna",
            asset_id="GPS_ANTENNA_001",
            project_root=isolated_root,
        )


def test_worker_rejects_transform_forbidden_for_exact_asset() -> None:
    scene = _complete_scene()
    gps = next(
        item
        for item in scene["accessory_assets"]
        if item["generation_strategy"] == "imported_glb_exact"
    )
    gps["scale"] = [1.1, 1.1, 1.1]

    with pytest.raises(RuntimeError, match="EXACT_IMPORT_SCALE_NOT_AUTHORIZED"):
        validate_trusted_assembly(scene, PROJECT_ROOT)


def test_worker_rejects_connector_removed_from_snapshot_and_manifest(tmp_path: Path) -> None:
    scene = _complete_scene()
    isolated_root = _copy_trust_inputs(tmp_path)
    component = next(
        item for item in scene["assembly_plan"]["components"] if item["role_id"] == "antenna_mount"
    )
    snapshot = component["manifest_snapshot"]
    manifest_path = isolated_root / "assets" / "manifests" / snapshot["manifest_file_name"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot["connectors"] = [
        item for item in snapshot["connectors"] if item["connector_id"] != "antenna_rail"
    ]
    manifest["connectors"] = [
        item for item in manifest["connectors"] if item["connector_id"] != "antenna_rail"
    ]
    _write_manifest_and_rehash_snapshot(manifest_path, manifest, snapshot)
    scene["assembly_plan"]["manifest_catalog_sha256"] = AssetRegistry(
        isolated_root / "assets" / "manifests"
    ).manifest_hash

    with pytest.raises(RuntimeError, match="ASSEMBLY_OPERATION_CONNECTOR_MISSING:antenna_rail"):
        validate_trusted_assembly(scene, isolated_root)


def test_resolved_plan_hashes_and_declared_connection_semantics_are_immutable() -> None:
    scene = _complete_scene()
    changed_operation = deepcopy(scene["assembly_plan"])
    changed_operation["operations"][0]["instances"][0]["translation_m"][0] += 0.1
    with pytest.raises(ValidationError, match="assembly operation hash mismatch"):
        AssemblyPlan.model_validate(changed_operation)
    with pytest.raises(RuntimeError, match="ASSEMBLY_OPERATION_HASH_MISMATCH"):
        validate_trusted_assembly(
            {**scene, "assembly_plan": changed_operation},
            PROJECT_ROOT,
        )

    changed_connection = deepcopy(scene)
    connection = changed_connection["assembly_plan"]["connections"][0]
    connection["target_connector_id"] = "missing_connector"
    with pytest.raises(RuntimeError, match="ASSEMBLY_OPERATION_CONNECTION_MISMATCH"):
        validate_trusted_assembly(changed_connection, PROJECT_ROOT)


def test_component_parameter_values_enforce_manifest_contract() -> None:
    _requirements, planning = _declared_plan()
    payload = planning.plan.model_dump(mode="json")
    support = next(
        component
        for component in payload["components"]
        if component["role_id"] == "support_structure"
    )

    above_maximum = deepcopy(payload)
    _component(above_maximum, "support_structure")["parameter_values"]["height_m"] = 50.0
    with pytest.raises(
        ValidationError,
        match="ASSEMBLY_COMPONENT_PARAMETER_ABOVE_MAX:support_structure:height_m",
    ):
        AssemblyPlan.model_validate(above_maximum)

    wrong_type = deepcopy(payload)
    _component(wrong_type, "support_structure")["parameter_values"]["height_m"] = "30"
    with pytest.raises(
        ValidationError,
        match="ASSEMBLY_COMPONENT_PARAMETER_TYPE_INVALID:support_structure:height_m",
    ):
        AssemblyPlan.model_validate(wrong_type)

    widened_allowlist = deepcopy(payload)
    widened = _component(widened_allowlist, "support_structure")
    widened["allowed_parameter_ids"].append("undeclared_parameter")
    widened["parameter_values"]["undeclared_parameter"] = 1.0
    with pytest.raises(
        ValidationError,
        match="ASSEMBLY_COMPONENT_PARAMETER_ALLOWLIST_MISMATCH:support_structure",
    ):
        AssemblyPlan.model_validate(widened_allowlist)

    invalid_enum = deepcopy(payload)
    enum_component = _component(invalid_enum, "support_structure")
    enum_component["manifest_snapshot"]["allowed_parameters"].append(
        {
            "parameter_id": "finish",
            "value_type": "enum",
            "unit": "none",
            "minimum": None,
            "maximum": None,
            "enum_values": ["galvanized", "painted"],
        }
    )
    enum_component["builder_profile"]["allowed_parameter_ids"].append("finish")
    enum_component["allowed_parameter_ids"].append("finish")
    enum_component["parameter_values"]["finish"] = "unqualified"
    _rehash(enum_component["manifest_snapshot"], "snapshot_sha256")
    _rehash(enum_component["builder_profile"], "profile_sha256")
    with pytest.raises(
        ValidationError,
        match="ASSEMBLY_COMPONENT_PARAMETER_ENUM_INVALID:support_structure:finish",
    ):
        AssemblyPlan.model_validate(invalid_enum)

    support["parameter_values"]["height_m"] = 45.0
    accepted = AssemblyPlan.model_validate(payload)
    assert _typed_component(accepted, "support_structure").parameter_values["height_m"] == 45.0


def test_compiler_and_worker_reject_mutated_component_parameter_above_manifest_maximum() -> None:
    requirements, planning = _declared_plan()
    scene = _build_scene(requirements, planning.assets_by_role, planning.plan)
    support = _typed_component(scene.assembly_plan, "support_structure")
    support.parameter_values["height_m"] = 50.0

    with pytest.raises(
        ValueError,
        match="ASSEMBLY_COMPONENT_PARAMETER_ABOVE_MAX:support_structure:height_m",
    ):
        resolve_scene_assembly(scene)

    raw_scene = _complete_scene()
    _component(raw_scene["assembly_plan"], "support_structure")["parameter_values"]["height_m"] = (
        50.0
    )
    with pytest.raises(
        RuntimeError,
        match="ASSEMBLY_COMPONENT_PARAMETER_ABOVE_MAX:height_m",
    ):
        validate_trusted_assembly(raw_scene, PROJECT_ROOT)

    valid_scene = _complete_scene()
    evidence = validate_trusted_assembly(valid_scene, PROJECT_ROOT)
    assert evidence["status"] == "passed"


def _declared_plan():
    registry = AssetRegistry(MANIFESTS_DIR)
    requirements = parse_requirements_text(
        "Créer un site 5G sur pylône treillis 30m avec 3 secteurs à 24m. "
        "Azimuts : 0°, 120°, 240°. Ajouter RRU, câbles, armoire énergie et antenne GPS."
    )
    planning = AssetAssemblyPlanner(registry).plan(
        workflow_id="wf_trusted_assembly",
        requirements=requirements,
    )
    return requirements, planning


def _component(plan: dict, role_id: str) -> dict:
    return next(component for component in plan["components"] if component["role_id"] == role_id)


def _typed_component(plan: AssemblyPlan | None, role_id: str):
    assert plan is not None
    return next(component for component in plan.components if component.role_id == role_id)


def _complete_scene() -> dict:
    requirements, planning = _declared_plan()
    return _build_scene(requirements, planning.assets_by_role, planning.plan).model_dump(
        mode="json"
    )


def _build_scene(requirements, assets_by_role, assembly_plan):
    accessories = [
        assets_by_role[role]
        for role in ("ground_equipment", "timing_antenna")
        if role in assets_by_role
    ]
    return ScenePlanner().build_scene_spec(
        "wf_trusted_assembly",
        requirements,
        assets_by_role["support_structure"],
        assets_by_role["sector_antenna"],
        assets_by_role.get("remote_radio"),
        accessories,
        assembly_plan=assembly_plan,
    )


def _copy_trust_inputs(tmp_path: Path) -> Path:
    root = tmp_path / "trusted-project"
    shutil.copytree(MANIFESTS_DIR, root / "assets" / "manifests")
    (root / "assets" / "capabilities").mkdir(parents=True)
    shutil.copy2(BUILDER_CATALOG, root / "assets" / "capabilities" / BUILDER_CATALOG.name)
    gps_source = PROJECT_ROOT / "assets" / "antennas" / "gps_antenna_001.glb"
    gps_target = root / "assets" / "antennas" / gps_source.name
    gps_target.parent.mkdir(parents=True)
    shutil.copy2(gps_source, gps_target)
    return root


def _exact_gps_inputs(scene: dict, root: Path) -> tuple[dict, Path, dict]:
    component = next(
        item for item in scene["assembly_plan"]["components"] if item["role_id"] == "timing_antenna"
    )
    snapshot = component["manifest_snapshot"]
    manifest_path = root / "assets" / "manifests" / snapshot["manifest_file_name"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return snapshot, manifest_path, manifest


def _write_manifest_and_rehash_snapshot(
    manifest_path: Path,
    manifest: dict,
    snapshot: dict,
) -> None:
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    snapshot["source_manifest_sha256"] = _sha256(manifest_path)
    _rehash(snapshot, "snapshot_sha256")


def _rehash(payload: dict, field: str) -> None:
    unhashed = {key: value for key, value in payload.items() if key != field}
    payload[field] = _canonical_sha256(unhashed)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
