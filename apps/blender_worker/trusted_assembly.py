"""Independent worker-side validation of trusted assembly and exact imports."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

_KNOWN_HANDLERS = {
    "tower_structure",
    "sector_equipment",
    "mount_bracket",
    "radio_enclosure",
    "cable_route",
    "ground_cabinet",
    "gps_radome",
}
_KNOWN_SECTOR_GEOMETRY_FAMILIES = {"panel", "microwave_dish"}


def validate_trusted_assembly(scene: dict, project_root: Path) -> dict:
    plan = scene.get("assembly_plan")
    exact_requested = _exact_import_roles(scene)
    if not isinstance(plan, dict) or plan.get("schema_version") != "1.1.0":
        if exact_requested:
            raise RuntimeError("EXACT_IMPORT_MANIFEST_SNAPSHOT_REQUIRED")
        return {
            "status": "legacy_uncompiled",
            "schema_version": str((plan or {}).get("schema_version") or "none"),
            "builder_profiles": [],
            "manifest_snapshots": [],
            "operations": [],
            "exact_imports": [],
        }
    if plan.get("compilation_status") != "resolved":
        raise RuntimeError("ASSEMBLY_PLAN_NOT_RESOLVED")
    catalog_hash = _manifest_catalog_sha256(project_root)
    if plan.get("manifest_catalog_sha256") != catalog_hash:
        raise RuntimeError("ASSET_MANIFEST_CATALOG_HASH_MISMATCH")
    components = plan.get("components")
    operations = plan.get("operations")
    if not isinstance(components, list) or not components:
        raise RuntimeError("ASSEMBLY_COMPONENTS_MISSING")
    if not isinstance(operations, list) or not operations:
        raise RuntimeError("ASSEMBLY_OPERATIONS_MISSING")
    components_by_role: dict[str, dict] = {}
    authoritative_builders = _load_authoritative_builders(project_root)
    manifest_evidence: list[dict] = []
    builder_evidence: list[dict] = []
    exact_evidence: list[dict] = []
    for component in components:
        if not isinstance(component, dict):
            raise RuntimeError("ASSEMBLY_COMPONENT_INVALID")
        role_id = str(component.get("role_id") or "")
        if not role_id or role_id in components_by_role:
            raise RuntimeError("ASSEMBLY_COMPONENT_ROLE_INVALID")
        snapshot = component.get("manifest_snapshot")
        builder = component.get("builder_profile")
        if not isinstance(snapshot, dict):
            raise RuntimeError(f"ASSEMBLY_MANIFEST_SNAPSHOT_MISSING:{role_id}")
        if not isinstance(builder, dict):
            raise RuntimeError(f"ASSEMBLY_BUILDER_SNAPSHOT_MISSING:{role_id}")
        _validate_snapshot_hash(
            snapshot,
            "snapshot_sha256",
            "ASSET_MANIFEST_SNAPSHOT_HASH_MISMATCH",
        )
        _validate_snapshot_hash(builder, "profile_sha256", "BUILDER_PROFILE_SNAPSHOT_HASH_MISMATCH")
        handler = str(builder.get("worker_handler") or "")
        if handler not in _KNOWN_HANDLERS:
            raise RuntimeError(f"UNKNOWN_BUILDER_HANDLER:{handler}")
        _validate_builder_geometry_family(builder)
        _revalidate_builder_source(builder, authoritative_builders)
        if builder.get("profile_id") != component.get("builder_profile_id"):
            raise RuntimeError(f"BUILDER_PROFILE_ID_MISMATCH:{role_id}")
        if snapshot.get("builder_profile_id") != component.get("builder_profile_id"):
            raise RuntimeError(f"MANIFEST_BUILDER_PROFILE_MISMATCH:{role_id}")
        if snapshot.get("asset_id") != component.get("selected_asset_id"):
            raise RuntimeError(f"ASSEMBLY_ASSET_ID_MISMATCH:{role_id}")
        _revalidate_manifest_source(project_root, snapshot)
        _validate_component_parameters(component)
        manifest_evidence.append(
            {
                "role_id": role_id,
                "asset_id": snapshot["asset_id"],
                "manifest_file_name": snapshot["manifest_file_name"],
                "source_manifest_sha256": snapshot["source_manifest_sha256"],
                "snapshot_sha256": snapshot["snapshot_sha256"],
                "generation_mode": snapshot["generation_mode"],
            }
        )
        builder_evidence.append(
            {
                "role_id": role_id,
                "profile_id": builder["profile_id"],
                "profile_sha256": builder["profile_sha256"],
                "worker_handler": handler,
            }
        )
        if snapshot.get("generation_mode") == "imported_glb_exact":
            exact_evidence.append(
                _external_exact_evidence(_revalidate_exact_asset(project_root, snapshot))
            )
        components_by_role[role_id] = component
    connections = plan.get("connections")
    if not isinstance(connections, list) or not connections:
        raise RuntimeError("ASSEMBLY_CONNECTIONS_MISSING")
    connections_by_id: dict[str, dict] = {}
    for connection in connections:
        if not isinstance(connection, dict):
            raise RuntimeError("ASSEMBLY_CONNECTION_INVALID")
        connection_id = str(connection.get("connection_id") or "")
        if not connection_id or connection_id in connections_by_id:
            raise RuntimeError("ASSEMBLY_CONNECTION_ID_INVALID")
        connections_by_id[connection_id] = connection
    operation_evidence = [
        _validate_operation(operation, components_by_role, connections_by_id)
        for operation in operations
    ]
    required_connections = {
        str(connection.get("connection_id"))
        for connection in connections
        if connection.get("required") is True
    }
    compiled_connections = {entry["connection_id"] for entry in operation_evidence}
    if not required_connections.issubset(compiled_connections):
        raise RuntimeError("ASSEMBLY_REQUIRED_CONNECTION_NOT_COMPILED")
    _validate_exact_transform_permissions(scene, components_by_role, operations)
    return {
        "status": "passed",
        "schema_version": plan["schema_version"],
        "manifest_catalog_sha256": plan.get("manifest_catalog_sha256"),
        "builder_profiles": builder_evidence,
        "manifest_snapshots": manifest_evidence,
        "operations": operation_evidence,
        "exact_imports": exact_evidence,
    }


def exact_asset_boundary(
    scene: dict,
    *,
    role_id: str,
    asset_id: str,
    project_root: Path,
) -> dict:
    plan = scene.get("assembly_plan") or {}
    component = next(
        (
            item
            for item in plan.get("components", [])
            if item.get("role_id") == role_id and item.get("selected_asset_id") == asset_id
        ),
        None,
    )
    if not isinstance(component, dict):
        raise RuntimeError(f"EXACT_IMPORT_COMPONENT_BOUNDARY_MISSING:{role_id}:{asset_id}")
    snapshot = component.get("manifest_snapshot")
    if not isinstance(snapshot, dict) or snapshot.get("generation_mode") != "imported_glb_exact":
        raise RuntimeError(f"EXACT_IMPORT_MODE_NOT_AUTHORIZED:{role_id}:{asset_id}")
    _validate_snapshot_hash(snapshot, "snapshot_sha256", "ASSET_MANIFEST_SNAPSHOT_HASH_MISMATCH")
    _revalidate_manifest_source(project_root, snapshot)
    evidence = _revalidate_exact_asset(project_root, snapshot)
    return {**snapshot, "resolved_asset_path": evidence["resolved_asset_path"]}


def operation_instance(
    scene: dict,
    *,
    connection_id: str,
    instance_id: str,
) -> dict:
    operation = next(
        (
            item
            for item in (scene.get("assembly_plan") or {}).get("operations", [])
            if item.get("connection_id") == connection_id
        ),
        None,
    )
    if not isinstance(operation, dict):
        raise RuntimeError(f"ASSEMBLY_OPERATION_MISSING:{connection_id}")
    instance = next(
        (item for item in operation.get("instances", []) if item.get("instance_id") == instance_id),
        None,
    )
    if not isinstance(instance, dict):
        raise RuntimeError(f"ASSEMBLY_OPERATION_INSTANCE_MISSING:{connection_id}:{instance_id}")
    return instance


def component_boundary(scene: dict, role_id: str) -> dict:
    component = next(
        (
            item
            for item in (scene.get("assembly_plan") or {}).get("components", [])
            if item.get("role_id") == role_id
        ),
        None,
    )
    if not isinstance(component, dict):
        raise RuntimeError(f"ASSEMBLY_COMPONENT_BOUNDARY_MISSING:{role_id}")
    return component


def resolve_component_builder(
    scene: dict,
    *,
    role_id: str,
    runtime_builder_profile_id: str | None,
    project_root: Path,
) -> dict:
    """Resolve one authoritative builder without consulting asset or network names.

    Trusted Assembly 1.1 carries the immutable profile snapshot. Legacy scenes
    created by the current planner carry only the profile ID in runtime asset
    metadata, so they are resolved against the local authoritative catalog.
    """

    plan = scene.get("assembly_plan") or {}
    if plan.get("schema_version") == "1.1.0":
        component = component_boundary(scene, role_id)
        builder = component.get("builder_profile")
        if not isinstance(builder, dict):
            raise RuntimeError(f"ASSEMBLY_BUILDER_SNAPSHOT_MISSING:{role_id}")
        if runtime_builder_profile_id and runtime_builder_profile_id != builder.get("profile_id"):
            raise RuntimeError(f"RUNTIME_BUILDER_PROFILE_MISMATCH:{role_id}")
    else:
        if not runtime_builder_profile_id:
            raise RuntimeError(f"RUNTIME_BUILDER_PROFILE_MISSING:{role_id}")
        builder = _load_authoritative_builders(project_root).get(runtime_builder_profile_id)
        if builder is None:
            raise RuntimeError(f"UNKNOWN_BUILDER_PROFILE:{runtime_builder_profile_id}")
    _validate_builder_geometry_family(builder)
    return builder


def _validate_snapshot_hash(snapshot: dict, field: str, error_code: str) -> None:
    expected = snapshot.get(field)
    payload = {key: value for key, value in snapshot.items() if key != field}
    if not isinstance(expected, str) or _canonical_sha256(payload) != expected:
        raise RuntimeError(error_code)


def _revalidate_manifest_source(project_root: Path, snapshot: dict) -> None:
    file_name = snapshot.get("manifest_file_name")
    if not isinstance(file_name, str) or Path(file_name).name != file_name:
        raise RuntimeError("ASSET_MANIFEST_PATH_INVALID")
    manifests_root = (project_root / "assets" / "manifests").resolve()
    path = (manifests_root / file_name).resolve()
    if path.parent != manifests_root or not path.is_file():
        raise RuntimeError("ASSET_MANIFEST_PATH_OUTSIDE_CATALOG")
    if _sha256(path) != snapshot.get("source_manifest_sha256"):
        raise RuntimeError("ASSET_MANIFEST_SOURCE_HASH_MISMATCH")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("ASSET_MANIFEST_SOURCE_INVALID") from exc
    qualification = manifest.get("qualification") or {}
    comparisons = {
        "asset_id": manifest.get("asset_id"),
        "asset_type": manifest.get("type"),
        "manifest_version": manifest.get("version"),
        "asset_file": manifest.get("file"),
        "builder_profile_id": manifest.get("builder_profile_id"),
        "dimensions_m": manifest.get("dimensions_m"),
        "units": qualification.get("units"),
        "verified_file_sha256": qualification.get("verified_file_sha256"),
        "anchors": manifest.get("anchors", []),
        "connectors": manifest.get("connectors", []),
        "allowed_parameters": manifest.get("allowed_parameters", []),
        "transform_permissions": manifest.get("transform_permissions"),
        "import_fallback_allowed": manifest.get("import_fallback_allowed", True),
    }
    for key, actual in comparisons.items():
        expected = snapshot.get(key)
        actual = _with_contract_defaults(key, actual)
        if actual != expected:
            raise RuntimeError(f"ASSET_MANIFEST_SNAPSHOT_FIELD_MISMATCH:{key}")
    if snapshot.get("generation_mode") not in qualification.get("allowed_generation_modes", []):
        raise RuntimeError("ASSET_MANIFEST_GENERATION_MODE_REVOKED")


def _with_contract_defaults(kind: str, values: object) -> object:
    if kind == "transform_permissions" and isinstance(values, dict):
        entry = dict(values)
        entry.setdefault("translation_axes", [])
        entry.setdefault("rotation_axes", [])
        entry.setdefault("maximum_translation_m", 0.0)
        entry.setdefault("maximum_rotation_deg", 0.0)
        entry.setdefault("uniform_scale_allowed", False)
        entry.setdefault("non_uniform_scale_allowed", False)
        return entry
    if not isinstance(values, list):
        return values
    normalized = []
    for value in values:
        if not isinstance(value, dict):
            normalized.append(value)
            continue
        entry = dict(value)
        if kind == "anchors":
            entry.setdefault("up", [0.0, 0.0, 1.0])
            entry.setdefault("placement_policy", "fixed")
        elif kind == "connectors":
            entry.setdefault("gender", "bidirectional")
            entry.setdefault("compatible_connector_kinds", [])
            entry.setdefault("tolerance_m", 0.01)
        elif kind == "allowed_parameters":
            entry.setdefault("unit", "none")
            entry.setdefault("minimum", None)
            entry.setdefault("maximum", None)
            entry.setdefault("enum_values", [])
        normalized.append(entry)
    return normalized


def _load_authoritative_builders(project_root: Path) -> dict[str, dict]:
    path = project_root / "assets" / "capabilities" / "builder_profiles.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("BUILDER_PROFILE_CATALOG_INVALID") from exc
    if payload.get("schema_version") != "1.0.0" or not isinstance(payload.get("profiles"), list):
        raise RuntimeError("BUILDER_PROFILE_CATALOG_SCHEMA_UNSUPPORTED")
    profiles: dict[str, dict] = {}
    for raw in payload["profiles"]:
        if not isinstance(raw, dict):
            raise RuntimeError("BUILDER_PROFILE_CATALOG_ENTRY_INVALID")
        profile_id = str(raw.get("profile_id") or "")
        if not profile_id or profile_id in profiles:
            raise RuntimeError("BUILDER_PROFILE_CATALOG_ID_INVALID")
        profile = dict(raw)
        profile["profile_sha256"] = _canonical_sha256(profile)
        profiles[profile_id] = profile
    return profiles


def _revalidate_builder_source(builder: dict, authoritative: dict[str, dict]) -> None:
    profile_id = str(builder.get("profile_id") or "")
    source = authoritative.get(profile_id)
    if source is None:
        raise RuntimeError(f"UNKNOWN_BUILDER_PROFILE:{profile_id}")
    if source != builder:
        raise RuntimeError(f"BUILDER_PROFILE_SOURCE_MISMATCH:{profile_id}")


def _validate_builder_geometry_family(builder: dict) -> None:
    if builder.get("worker_handler") != "sector_equipment":
        return
    family = builder.get("geometry_family")
    if family not in _KNOWN_SECTOR_GEOMETRY_FAMILIES:
        raise RuntimeError(f"UNKNOWN_BUILDER_GEOMETRY_FAMILY:{family}")


def _revalidate_exact_asset(project_root: Path, snapshot: dict) -> dict:
    if snapshot.get("units") != "meters":
        raise RuntimeError("EXACT_IMPORT_UNITS_AMBIGUOUS")
    if snapshot.get("import_fallback_allowed") is not False:
        raise RuntimeError("EXACT_IMPORT_FALLBACK_FORBIDDEN")
    if not isinstance(snapshot.get("transform_permissions"), dict):
        raise RuntimeError("EXACT_IMPORT_TRANSFORM_PERMISSIONS_MISSING")
    asset_file = snapshot.get("asset_file")
    if not isinstance(asset_file, str):
        raise RuntimeError("EXACT_IMPORT_ASSET_PATH_INVALID")
    relative = Path(asset_file)
    if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".glb":
        raise RuntimeError("EXACT_IMPORT_ASSET_PATH_INVALID")
    root = project_root.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root / "assets")
    except ValueError as exc:
        raise RuntimeError("EXACT_IMPORT_ASSET_PATH_OUTSIDE_CATALOG") from exc
    if not path.is_file():
        raise RuntimeError("EXACT_IMPORT_ASSET_FILE_MISSING")
    expected = snapshot.get("verified_file_sha256")
    actual = _sha256(path)
    if not isinstance(expected, str) or actual != expected:
        raise RuntimeError("EXACT_IMPORT_ASSET_HASH_MISMATCH")
    return {
        "asset_id": snapshot["asset_id"],
        "asset_file": asset_file,
        "resolved_asset_path": str(path),
        "verified_file_sha256": expected,
        "actual_file_sha256": actual,
        "units": snapshot["units"],
        "transform_permissions": snapshot["transform_permissions"],
    }


def _external_exact_evidence(evidence: dict) -> dict:
    """Keep the worker-local resolved path out of persisted/public proof artifacts."""

    return {key: value for key, value in evidence.items() if key != "resolved_asset_path"}


def _validate_operation(
    operation: object,
    components: dict[str, dict],
    connections: dict[str, dict],
) -> dict:
    if not isinstance(operation, dict):
        raise RuntimeError("ASSEMBLY_OPERATION_INVALID")
    _validate_snapshot_hash(operation, "operation_sha256", "ASSEMBLY_OPERATION_HASH_MISMATCH")
    source = components.get(str(operation.get("source_role_id") or ""))
    target = components.get(str(operation.get("target_role_id") or ""))
    if source is None or target is None:
        raise RuntimeError("ASSEMBLY_OPERATION_ROLE_UNKNOWN")
    connection_id = str(operation.get("connection_id") or "")
    connection = connections.get(connection_id)
    if connection is None:
        raise RuntimeError(f"ASSEMBLY_OPERATION_CONNECTION_UNKNOWN:{connection_id}")
    compared_connection_fields = (
        "kind",
        "source_role_id",
        "source_connector_id",
        "target_role_id",
        "target_connector_id",
    )
    if any(operation.get(field) != connection.get(field) for field in compared_connection_fields):
        raise RuntimeError(f"ASSEMBLY_OPERATION_CONNECTION_MISMATCH:{connection_id}")
    source_snapshot = source["manifest_snapshot"]
    target_snapshot = target["manifest_snapshot"]
    if operation.get("source_asset_id") != source.get("selected_asset_id"):
        raise RuntimeError("ASSEMBLY_OPERATION_SOURCE_ASSET_MISMATCH")
    if operation.get("target_asset_id") != target.get("selected_asset_id"):
        raise RuntimeError("ASSEMBLY_OPERATION_TARGET_ASSET_MISMATCH")
    if operation.get("builder_profile_id") != source.get("builder_profile_id"):
        raise RuntimeError("ASSEMBLY_OPERATION_BUILDER_MISMATCH")
    source_connector = _connector(source_snapshot, operation.get("source_connector_id"))
    target_connector = _connector(target_snapshot, operation.get("target_connector_id"))
    if source_connector.get("kind") != operation.get("kind") or target_connector.get(
        "kind"
    ) != operation.get("kind"):
        raise RuntimeError("ASSEMBLY_OPERATION_CONNECTOR_KIND_MISMATCH")
    _validate_connector_compatibility(source_connector, target_connector)
    source_anchor = _anchor(source_snapshot, source_connector.get("anchor_id"))
    target_anchor = _anchor(target_snapshot, target_connector.get("anchor_id"))
    if operation.get("source_anchor") != source_anchor:
        raise RuntimeError("ASSEMBLY_OPERATION_SOURCE_ANCHOR_MISMATCH")
    if operation.get("target_anchor") != target_anchor:
        raise RuntimeError("ASSEMBLY_OPERATION_TARGET_ANCHOR_MISMATCH")
    expected_tolerance = min(
        float(source_connector.get("tolerance_m") or 0.0),
        float(target_connector.get("tolerance_m") or 0.0),
    )
    if not math.isclose(
        float(operation.get("tolerance_m") or 0.0),
        expected_tolerance,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise RuntimeError("ASSEMBLY_OPERATION_TOLERANCE_MISMATCH")
    instances = operation.get("instances")
    if not isinstance(instances, list) or not instances:
        raise RuntimeError("ASSEMBLY_OPERATION_INSTANCES_MISSING")
    for instance in instances:
        if not isinstance(instance, dict):
            raise RuntimeError("ASSEMBLY_OPERATION_INSTANCE_INVALID")
        apply_to = components.get(str(instance.get("apply_to_role_id") or ""))
        if apply_to is None:
            raise RuntimeError("ASSEMBLY_OPERATION_INSTANCE_ROLE_UNKNOWN")
        _validate_resolved_parameters(
            instance.get("resolved_parameters"),
            apply_to,
        )
    return {
        "operation_id": operation.get("operation_id"),
        "connection_id": operation.get("connection_id"),
        "operation_type": operation.get("operation_type"),
        "operation_sha256": operation.get("operation_sha256"),
        "instance_count": len(instances),
        "builder_profile_id": operation.get("builder_profile_id"),
    }


def _validate_component_parameters(component: dict) -> None:
    role_id = str(component.get("role_id") or "")
    snapshot_parameters = component["manifest_snapshot"].get("allowed_parameters")
    if not isinstance(snapshot_parameters, list):
        raise RuntimeError(f"ASSEMBLY_COMPONENT_PARAMETER_CONTRACT_INVALID:{role_id}")
    allowed: dict[str, dict] = {}
    for item in snapshot_parameters:
        if not isinstance(item, dict):
            raise RuntimeError(f"ASSEMBLY_COMPONENT_PARAMETER_CONTRACT_INVALID:{role_id}")
        parameter_id = item.get("parameter_id")
        if not isinstance(parameter_id, str) or not parameter_id or parameter_id in allowed:
            raise RuntimeError(f"ASSEMBLY_COMPONENT_PARAMETER_CONTRACT_INVALID:{role_id}")
        allowed[parameter_id] = item
    declared_ids = component.get("allowed_parameter_ids")
    if (
        not isinstance(declared_ids, list)
        or any(not isinstance(item, str) for item in declared_ids)
        or len(declared_ids) != len(set(declared_ids))
        or set(declared_ids) != set(allowed)
    ):
        raise RuntimeError(f"ASSEMBLY_COMPONENT_PARAMETER_ALLOWLIST_MISMATCH:{role_id}")
    builder_ids = component["builder_profile"].get("allowed_parameter_ids")
    if not isinstance(builder_ids, list) or any(not isinstance(item, str) for item in builder_ids):
        raise RuntimeError(f"ASSEMBLY_COMPONENT_BUILDER_PARAMETER_MISMATCH:{role_id}")
    builder_allowed = set(builder_ids)
    if not set(allowed).issubset(builder_allowed):
        raise RuntimeError(f"ASSEMBLY_COMPONENT_BUILDER_PARAMETER_MISMATCH:{role_id}")
    _validate_parameter_values(
        component.get("parameter_values"),
        allowed,
        builder_allowed,
        container_error="ASSEMBLY_COMPONENT_PARAMETERS_INVALID",
        error_prefix="ASSEMBLY_COMPONENT_PARAMETER",
    )


def _validate_resolved_parameters(parameters: object, component: dict) -> None:
    allowed = {
        item["parameter_id"]: item
        for item in component["manifest_snapshot"].get("allowed_parameters", [])
    }
    builder_allowed = set(component["builder_profile"].get("allowed_parameter_ids", []))
    _validate_parameter_values(
        parameters,
        allowed,
        builder_allowed,
        container_error="ASSEMBLY_RESOLVED_PARAMETERS_INVALID",
        error_prefix="ASSEMBLY_RESOLVED_PARAMETER",
    )


def _validate_parameter_values(
    parameters: object,
    allowed: dict[str, dict],
    builder_allowed: set[str],
    *,
    container_error: str,
    error_prefix: str,
) -> None:
    if not isinstance(parameters, dict):
        raise RuntimeError(container_error)
    for parameter_id, value in parameters.items():
        contract = allowed.get(parameter_id)
        if contract is None or parameter_id not in builder_allowed:
            raise RuntimeError(f"{error_prefix}_NOT_AUTHORIZED:{parameter_id}")
        value_type = contract.get("value_type")
        if value_type == "boolean" and not isinstance(value, bool):
            raise RuntimeError(f"{error_prefix}_TYPE_INVALID:{parameter_id}")
        if value_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise RuntimeError(f"{error_prefix}_TYPE_INVALID:{parameter_id}")
        if value_type == "number" and (
            not isinstance(value, (int, float)) or isinstance(value, bool)
        ):
            raise RuntimeError(f"{error_prefix}_TYPE_INVALID:{parameter_id}")
        if value_type == "enum":
            if not isinstance(value, str):
                raise RuntimeError(f"{error_prefix}_TYPE_INVALID:{parameter_id}")
            if value not in contract.get("enum_values", []):
                raise RuntimeError(f"{error_prefix}_ENUM_INVALID:{parameter_id}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(float(value)):
                raise RuntimeError(f"{error_prefix}_TYPE_INVALID:{parameter_id}")
            minimum = contract.get("minimum")
            maximum = contract.get("maximum")
            if minimum is not None and float(value) < float(minimum):
                raise RuntimeError(f"{error_prefix}_BELOW_MIN:{parameter_id}")
            if maximum is not None and float(value) > float(maximum):
                raise RuntimeError(f"{error_prefix}_ABOVE_MAX:{parameter_id}")


def _connector(snapshot: dict, connector_id: object) -> dict:
    connector = next(
        (
            item
            for item in snapshot.get("connectors", [])
            if item.get("connector_id") == connector_id
        ),
        None,
    )
    if not isinstance(connector, dict):
        raise RuntimeError(f"ASSEMBLY_OPERATION_CONNECTOR_MISSING:{connector_id}")
    return connector


def _anchor(snapshot: dict, anchor_id: object) -> dict:
    anchor = next(
        (item for item in snapshot.get("anchors", []) if item.get("anchor_id") == anchor_id),
        None,
    )
    if not isinstance(anchor, dict):
        raise RuntimeError(f"ASSEMBLY_OPERATION_ANCHOR_MISSING:{anchor_id}")
    return anchor


def _validate_connector_compatibility(source: dict, target: dict) -> None:
    source_kind = source.get("kind")
    target_kind = target.get("kind")
    if target_kind not in source.get("compatible_connector_kinds", []) or source_kind not in (
        target.get("compatible_connector_kinds", [])
    ):
        raise RuntimeError("ASSEMBLY_OPERATION_CONNECTOR_INCOMPATIBLE")
    source_gender = source.get("gender", "bidirectional")
    target_gender = target.get("gender", "bidirectional")
    allowed = {
        ("source", "target"),
        ("male", "female"),
        ("female", "male"),
    }
    if (
        source_gender != "bidirectional"
        and target_gender != "bidirectional"
        and (source_gender, target_gender) not in allowed
    ):
        raise RuntimeError("ASSEMBLY_OPERATION_CONNECTOR_GENDER_INCOMPATIBLE")


def _validate_exact_transform_permissions(
    scene: dict,
    components: dict[str, dict],
    operations: list[dict],
) -> None:
    for role_id, component in components.items():
        snapshot = component["manifest_snapshot"]
        if snapshot.get("generation_mode") != "imported_glb_exact":
            continue
        permissions = snapshot["transform_permissions"]
        transforms = _component_transforms(scene, role_id, operations)
        if not transforms:
            raise RuntimeError(f"EXACT_IMPORT_TRANSFORM_UNRESOLVED:{role_id}")
        for translation, rotation, scale in transforms:
            _validate_axes(
                translation,
                permissions.get("translation_axes", []),
                float(permissions.get("maximum_translation_m") or 0.0),
                "EXACT_IMPORT_TRANSLATION_NOT_AUTHORIZED",
            )
            _validate_axes(
                rotation,
                permissions.get("rotation_axes", []),
                float(permissions.get("maximum_rotation_deg") or 0.0),
                "EXACT_IMPORT_ROTATION_NOT_AUTHORIZED",
            )
            non_identity = [abs(float(value) - 1.0) > 1e-6 for value in scale]
            if any(non_identity):
                if not permissions.get("uniform_scale_allowed"):
                    raise RuntimeError("EXACT_IMPORT_SCALE_NOT_AUTHORIZED")
                if max(scale) - min(scale) > 1e-6 and not permissions.get(
                    "non_uniform_scale_allowed"
                ):
                    raise RuntimeError("EXACT_IMPORT_NON_UNIFORM_SCALE_NOT_AUTHORIZED")


def _component_transforms(
    scene: dict,
    role_id: str,
    operations: list[dict],
) -> list[tuple[list[float], list[float], list[float]]]:
    resolved = [
        (
            list(instance.get("translation_m") or []),
            list(instance.get("rotation_deg") or []),
            list(instance.get("scale") or [1.0, 1.0, 1.0]),
        )
        for operation in operations
        for instance in operation.get("instances", [])
        if instance.get("apply_to_role_id") == role_id
        and operation.get("operation_type") == "place_component"
    ]
    if resolved:
        return resolved
    accessory_type = {"timing_antenna": "gps", "ground_equipment": "cabinet"}.get(role_id)
    if accessory_type:
        return [
            (
                list(asset.get("position") or [0.0, 0.0, 0.0]),
                list(asset.get("rotation_deg") or [0.0, 0.0, 0.0]),
                list(asset.get("scale") or [1.0, 1.0, 1.0]),
            )
            for asset in scene.get("accessory_assets", [])
            if asset.get("asset_type") == accessory_type
        ]
    if role_id == "support_structure":
        tower = scene.get("tower") or {}
        return [
            (
                list(tower.get("position") or [0.0, 0.0, 0.0]),
                list(tower.get("rotation_deg") or [0.0, 0.0, 0.0]),
                list(tower.get("scale") or [1.0, 1.0, 1.0]),
            )
        ]
    return []


def _validate_axes(values: list[float], allowed: list[str], maximum: float, code: str) -> None:
    if len(values) != 3:
        raise RuntimeError(code)
    for index, axis in enumerate(("x", "y", "z")):
        value = abs(float(values[index]))
        if value > 1e-6 and axis not in allowed:
            raise RuntimeError(f"{code}:{axis}")
        if value > maximum + 1e-6:
            raise RuntimeError(f"{code}:BOUND")


def _exact_import_roles(scene: dict) -> set[str]:
    roles: set[str] = set()
    if (scene.get("tower") or {}).get("generation_strategy") == "imported_glb_exact":
        roles.add("support_structure")
    if any(
        sector.get("antenna_generation_strategy") == "imported_glb_exact"
        for sector in scene.get("sectors", [])
    ):
        roles.add("sector_antenna")
    if any(
        sector.get("radio_generation_strategy") == "imported_glb_exact"
        for sector in scene.get("sectors", [])
    ):
        roles.add("remote_radio")
    for accessory in scene.get("accessory_assets", []):
        if accessory.get("generation_strategy") != "imported_glb_exact":
            continue
        role = {"gps": "timing_antenna", "cabinet": "ground_equipment"}.get(
            accessory.get("asset_type")
        )
        if role:
            roles.add(role)
    return roles


def _canonical_sha256(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _manifest_catalog_sha256(project_root: Path) -> str:
    manifests_root = project_root / "assets" / "manifests"
    entries = []
    try:
        for path in sorted(manifests_root.glob("*.json")):
            entries.append(
                {
                    "filename": path.name,
                    "content": json.loads(path.read_text(encoding="utf-8")),
                }
            )
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("ASSET_MANIFEST_CATALOG_INVALID") from exc
    encoded = json.dumps(
        entries,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
