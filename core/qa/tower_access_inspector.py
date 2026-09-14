"""Independent exported-GLB inspection for bounded lattice-tower access geometry."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from core.contracts.scene import SceneSpec
from core.contracts.tower_access_evidence import (
    TowerAccessEvidence,
    TowerAccessLadderMeasurement,
    TowerAccessPlatformMeasurement,
    canonical_tower_access_evidence_sha256,
)
from core.qa import gltf_integrity


def tower_access_evidence_required(scene: SceneSpec | None) -> bool:
    return bool(
        scene
        and scene.tower is not None
        and scene.tower.tower_access_geometry_profile is not None
        and scene.tower.characteristics.structure == "lattice"
        and (scene.tower.characteristics.has_ladder or scene.tower.characteristics.has_platform)
    )


class TowerAccessInspector:
    """Read actual GLB nodes/vertices; never trust worker object names or metadata."""

    def inspect(self, artifact_dir: Path, scene: SceneSpec) -> TowerAccessEvidence:
        if not tower_access_evidence_required(scene):
            raise ValueError("tower access evidence is not required for this SceneSpec")
        glb_path = artifact_dir / "design.glb"
        profile = scene.tower.tower_access_geometry_profile
        assert profile is not None
        profile_payload = profile.model_dump(mode="json")
        profile_sha256 = _canonical_json_sha256(profile_payload)
        semantic_root = f"tower_access_{scene.tower.asset_id}"
        errors: list[str] = []
        nodes = _mesh_nodes(glb_path, errors)
        root_nodes = _semantic_root_nodes(glb_path, semantic_root, errors)
        root_verified = bool(root_nodes) and all(
            node["extras"].get("role") == "tower_access"
            and node["extras"].get("tower_access_generation") == "manifest_bounded_procedural"
            for node in root_nodes
        )
        access_nodes = [
            node
            for node in nodes
            if node["extras"].get("semantic_root") == semantic_root
            and node["extras"].get("role") == "tower_access"
        ]
        profile_verified = bool(access_nodes) and all(
            node["extras"].get("tower_access_profile_family") == profile.family
            and node["extras"].get("tower_access_profile_sha256") == profile_sha256
            for node in access_nodes
        )
        if not root_verified:
            errors.append("TOWER_ACCESS_SEMANTIC_ROOT_INVALID")
        if not profile_verified:
            errors.append("TOWER_ACCESS_PROFILE_IDENTITY_INVALID")

        features: dict[str, list[dict[str, Any]]] = {}
        for node in access_nodes:
            feature = node["extras"].get("tower_access_feature")
            if isinstance(feature, str):
                features.setdefault(feature, []).append(node)
            else:
                errors.append("TOWER_ACCESS_FEATURE_MISSING")

        requested_ladder = scene.tower.characteristics.has_ladder
        expected_platforms = _expected_platform_levels(scene)
        ladder = (
            _ladder_measurement(features, profile_payload, scene.tower.height_m)
            if requested_ladder
            else None
        )
        if requested_ladder and (ladder is None or not ladder.passed):
            errors.append("TOWER_ACCESS_LADDER_GEOMETRY_INVALID")
        platforms = _platform_measurements(
            features,
            profile_payload,
            expected_platforms,
        )
        if len(platforms) != len(expected_platforms) or any(not item.passed for item in platforms):
            errors.append("TOWER_ACCESS_PLATFORM_GEOMETRY_INVALID")

        overlap_count = _primary_equipment_deck_overlap_count(
            nodes, features.get("platform_deck", [])
        )
        checks = {
            "semantic_root_verified": root_verified,
            "profile_verified": profile_verified,
            "ladder_geometry_verified": not requested_ladder or bool(ladder and ladder.passed),
            "platform_geometry_verified": len(platforms) == len(expected_platforms)
            and all(item.passed for item in platforms),
            "primary_equipment_deck_clearance": overlap_count == 0,
        }
        if profile.platform_support_drop_m is not None:
            checks["platform_support_geometry_verified"] = all(
                item.support_tower_attachment_count is not None
                and item.support_tower_attachment_count >= 2
                and item.support_deck_attachment_count is not None
                and item.support_deck_attachment_count >= 2
                and item.minimum_support_radial_span_m is not None
                and item.minimum_support_radial_span_m >= profile.platform_depth_m * 0.3
                and item.minimum_support_vertical_drop_m is not None
                and item.minimum_support_vertical_drop_m
                >= min(max(profile.platform_depth_m * 0.15, 0.2), 0.5)
                for item in platforms
            )
        evidence_payload = {
            "schema_version": "1.0.0",
            "scene_id": scene.scene_id,
            "status": "passed" if all(checks.values()) and not errors else "failed",
            "measurement_scope": "exported_glb_tower_access_geometry",
            "glb_sha256": _sha256(glb_path) if glb_path.is_file() else "0" * 64,
            "semantic_root": semantic_root,
            "profile_family": profile.family,
            "profile_sha256": profile_sha256,
            "requested_ladder": requested_ladder,
            "expected_platform_count": len(expected_platforms),
            "ladder": ladder.model_dump(mode="json") if ladder is not None else None,
            "platforms": [item.model_dump(mode="json") for item in platforms],
            "primary_equipment_deck_overlap_count": overlap_count,
            "checks": checks,
            "errors": sorted(set(errors)),
            "limitations": [
                (
                    "La preuve mesure des meshes exportés, leurs dimensions et leurs niveaux; "
                    "elle ne certifie pas la résistance structurelle."
                ),
                (
                    "Le dégagement est un test large par boîtes englobantes contre les "
                    "équipements principaux, sans collision triangle, contact ni fixation."
                ),
                (
                    "Cette géométrie procédurale interne ne représente pas une installation "
                    "constructeur, une conformité de sécurité, une évacuation ou une "
                    "approbation de chantier."
                ),
            ],
        }
        evidence_payload["evidence_sha256"] = canonical_tower_access_evidence_sha256(
            evidence_payload
        )
        return TowerAccessEvidence.model_validate(evidence_payload)


def verify_tower_access_evidence(artifact_dir: Path, scene: SceneSpec) -> TowerAccessEvidence:
    """Reinspect a persisted GLB and require byte-for-byte semantic agreement."""

    evidence_path = artifact_dir / "tower_access_evidence.json"
    try:
        persisted = TowerAccessEvidence.model_validate_json(
            evidence_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("ACTIVE_VERSION_TOWER_ACCESS_EVIDENCE_INVALID") from exc
    inspected = TowerAccessInspector().inspect(artifact_dir, scene)
    if inspected.status != "passed" or persisted != inspected:
        raise ValueError("ACTIVE_VERSION_TOWER_ACCESS_EVIDENCE_MISMATCH")
    return persisted


def _expected_platform_levels(scene: SceneSpec) -> list[float]:
    characteristics = scene.tower.characteristics
    profile = scene.tower.tower_access_geometry_profile
    assert profile is not None
    if not characteristics.has_platform:
        return []
    if characteristics.platform_levels_m:
        return [float(level) for level in characteristics.platform_levels_m]
    count = max(1, characteristics.platform_count)
    return [
        scene.tower.height_m
        * (
            profile.legacy_platform_start_height_ratio
            + profile.legacy_platform_span_height_ratio * index / max(count, 1)
        )
        for index in range(count)
    ]


def _ladder_measurement(
    features: dict[str, list[dict[str, Any]]], profile: dict[str, Any], height_m: float
) -> TowerAccessLadderMeasurement | None:
    rails = features.get("ladder_rail", [])
    rungs = features.get("ladder_rung", [])
    expected_base = float(profile["ladder_base_clearance_m"])
    expected_top = height_m - float(profile["ladder_top_clearance_m"])
    expected_spacing = float(profile["ladder_rung_spacing_m"])
    expected_minimum = max(
        2, int(math.floor((expected_top - expected_base) / expected_spacing)) + 1
    )
    if len(rails) != 2:
        return TowerAccessLadderMeasurement(
            rail_count=len(rails),
            rung_count=len(rungs),
            expected_minimum_rung_count=expected_minimum,
            expected_width_m=float(profile["ladder_width_m"]),
            observed_width_m=None,
            expected_base_m=expected_base,
            observed_base_m=None,
            expected_top_m=expected_top,
            observed_top_m=None,
            expected_rung_spacing_m=expected_spacing,
            observed_rung_spacing_m=None,
            passed=False,
        )
    rail_centers = [_bounds_center(item["bounds"]) for item in rails]
    observed_width = math.dist(rail_centers[0][:2], rail_centers[1][:2])
    observed_base = min(item["bounds"][2] for item in rails)
    observed_top = max(item["bounds"][5] for item in rails)
    rung_centers = sorted(_bounds_center(item["bounds"])[2] for item in rungs)
    spacings = [right - left for left, right in zip(rung_centers, rung_centers[1:], strict=False)]
    observed_spacing = (sum(spacings) / len(spacings)) if spacings else None
    passed = _ladder_passes(
        len(rails),
        len(rungs),
        expected_minimum,
        observed_width,
        float(profile["ladder_width_m"]),
        observed_base,
        expected_base,
        observed_top,
        expected_top,
        observed_spacing,
        expected_spacing,
    )
    return TowerAccessLadderMeasurement(
        rail_count=len(rails),
        rung_count=len(rungs),
        expected_minimum_rung_count=expected_minimum,
        expected_width_m=float(profile["ladder_width_m"]),
        observed_width_m=observed_width,
        expected_base_m=expected_base,
        observed_base_m=observed_base,
        expected_top_m=expected_top,
        observed_top_m=observed_top,
        expected_rung_spacing_m=expected_spacing,
        observed_rung_spacing_m=observed_spacing,
        passed=passed,
    )


def _ladder_passes(
    rails: int,
    rungs: int,
    expected_rungs: int,
    width: float,
    expected_width: float,
    base: float,
    expected_base: float,
    top: float,
    expected_top: float,
    spacing: float | None,
    expected_spacing: float,
) -> bool:
    return bool(
        rails == 2
        and rungs >= expected_rungs
        and spacing is not None
        and all(
            abs(actual - expected) <= 0.035
            for actual, expected in (
                (width, expected_width),
                (base, expected_base),
                (top, expected_top),
                (spacing, expected_spacing),
            )
        )
    )


def _platform_measurements(
    features: dict[str, list[dict[str, Any]]], profile: dict[str, Any], levels: list[float]
) -> list[TowerAccessPlatformMeasurement]:
    result: list[TowerAccessPlatformMeasurement] = []
    for index, level in enumerate(levels, start=1):

        def matching(
            feature: str, *, platform_index: int = index, level_m: float = level
        ) -> list[dict[str, Any]]:
            return [
                node
                for node in features.get(feature, [])
                if _platform_index(node) == platform_index
                and _requested_level(node) is not None
                and math.isclose(
                    _requested_level(node) or 0.0,
                    level_m,
                    rel_tol=0.0,
                    abs_tol=1e-6,
                )
            ]

        decks, rails, toes, supports = (
            matching("platform_deck"),
            matching("guardrail"),
            matching("toe_board"),
            matching("platform_support"),
        )
        observed_top = decks[0]["bounds"][5] if len(decks) == 1 else None
        observed_width, observed_depth = (
            _rectangle_dimensions(
                decks[0]["points"],
                expected_width=float(profile["platform_width_m"]),
                expected_depth=float(profile["platform_depth_m"]),
            )
            if len(decks) == 1
            else (None, None)
        )
        elevation_error = abs(observed_top - level) if observed_top is not None else None
        enhanced_supports = profile.get("platform_support_drop_m") is not None
        tower_attachments: int | None = None
        deck_attachments: int | None = None
        minimum_radial_span: float | None = None
        minimum_vertical_drop: float | None = None
        support_shape_valid = True
        if enhanced_supports:
            (
                tower_attachments,
                deck_attachments,
                minimum_radial_span,
                minimum_vertical_drop,
            ) = _support_geometry_measurement(
                supports,
                decks[0] if len(decks) == 1 else None,
                profile,
                level,
            )
            support_shape_valid = bool(
                tower_attachments >= 2
                and deck_attachments >= 2
                and minimum_radial_span is not None
                and minimum_radial_span >= float(profile["platform_depth_m"]) * 0.3
                and minimum_vertical_drop is not None
                and minimum_vertical_drop
                >= min(max(float(profile["platform_depth_m"]) * 0.15, 0.2), 0.5)
            )
        passed = bool(
            len(decks) == 1
            and observed_top is not None
            and elevation_error is not None
            and observed_width is not None
            and observed_depth is not None
            and elevation_error <= 0.04
            and abs(observed_width - float(profile["platform_width_m"])) <= 0.04
            and abs(observed_depth - float(profile["platform_depth_m"])) <= 0.04
            and len(rails) >= 7
            and len(toes) >= 3
            and len(supports) >= 2
            and support_shape_valid
        )
        result.append(
            TowerAccessPlatformMeasurement(
                platform_index=index,
                requested_level_m=level,
                observed_deck_top_m=observed_top,
                elevation_error_m=elevation_error,
                expected_width_m=float(profile["platform_width_m"]),
                expected_depth_m=float(profile["platform_depth_m"]),
                observed_width_m=observed_width,
                observed_depth_m=observed_depth,
                guardrail_mesh_count=len(rails),
                toe_board_mesh_count=len(toes),
                support_mesh_count=len(supports),
                support_tower_attachment_count=tower_attachments,
                support_deck_attachment_count=deck_attachments,
                minimum_support_radial_span_m=minimum_radial_span,
                minimum_support_vertical_drop_m=minimum_vertical_drop,
                passed=passed,
            )
        )
    return result


def _support_geometry_measurement(
    supports: list[dict[str, Any]],
    deck: dict[str, Any] | None,
    profile: dict[str, Any],
    level: float,
) -> tuple[int, int, float | None, float | None]:
    """Measure whether support meshes bridge the tower side and deck underside.

    This is a projected mesh measurement, not proof of fastening or load
    capacity.  It catches short horizontal rods hidden inside the deck.
    """

    if deck is None or not supports:
        return 0, 0, None, None
    face = math.radians(float(profile["access_face_azimuth_deg"]))
    outward = (math.sin(face), math.cos(face))

    def radial(point: tuple[float, float, float]) -> float:
        return point[0] * outward[0] + point[1] * outward[1]

    deck_radials = [radial(point) for point in deck["points"]]
    deck_inner = min(deck_radials)
    clearance = float(profile["platform_tower_clearance_m"])
    depth = float(profile["platform_depth_m"])
    thickness = float(profile["platform_thickness_m"])
    tower_attachments = 0
    deck_attachments = 0
    radial_spans: list[float] = []
    vertical_drops: list[float] = []
    for support in supports:
        radials = [radial(point) for point in support["points"]]
        heights = [point[2] for point in support["points"]]
        minimum_radial = min(radials)
        maximum_radial = max(radials)
        minimum_height = min(heights)
        maximum_height = max(heights)
        radial_spans.append(maximum_radial - minimum_radial)
        vertical_drops.append(maximum_height - minimum_height)
        if minimum_radial <= deck_inner - max(clearance * 0.5, 0.05):
            tower_attachments += 1
        if (
            maximum_radial >= deck_inner + depth * 0.3
            and abs(maximum_height - (level - thickness)) <= 0.04
        ):
            deck_attachments += 1
    return (
        tower_attachments,
        deck_attachments,
        min(radial_spans),
        min(vertical_drops),
    )


def _mesh_nodes(glb_path: Path, errors: list[str]) -> list[dict[str, Any]]:
    integrity = gltf_integrity.inspect_gltf_integrity(glb_path)
    payload = integrity.payload
    if payload is None:
        errors.append("TOWER_ACCESS_GLB_PARSE_FAILED")
        return []
    load_errors: list[str] = []
    _, chunks = gltf_integrity._load_document(glb_path, load_errors)
    buffers = gltf_integrity._load_buffers(glb_path, payload, chunks, load_errors)
    nodes, meshes, accessors, views = (
        payload.get(key) for key in ("nodes", "meshes", "accessors", "bufferViews")
    )
    if not all(isinstance(value, list) for value in (nodes, meshes, accessors, views)):
        errors.append("TOWER_ACCESS_GLB_STRUCTURE_INVALID")
        return []
    worlds = _world_matrices(nodes)
    observed: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        if (
            not isinstance(node, dict)
            or not isinstance(node.get("mesh"), int)
            or not isinstance(node.get("extras"), dict)
        ):
            continue
        mesh_index = node["mesh"]
        if not 0 <= mesh_index < len(meshes) or not isinstance(meshes[mesh_index], dict):
            continue
        points = _node_points(
            meshes[mesh_index],
            accessors,
            views,
            buffers,
            worlds.get(index, _identity()),
            load_errors,
        )
        if not points:
            continue
        observed.append(
            {"extras": dict(node["extras"]), "bounds": _bounds(points), "points": points}
        )
    if load_errors:
        errors.append("TOWER_ACCESS_GLB_GEOMETRY_INVALID")
    return observed


def _semantic_root_nodes(
    glb_path: Path, semantic_root: str, errors: list[str]
) -> list[dict[str, Any]]:
    """Read semantic group nodes independently of the mesh-feature scan."""

    load_errors: list[str] = []
    # The JSON payload is returned as the first result by the integrity helper.
    payload, _ = gltf_integrity._load_document(glb_path, load_errors)
    if not isinstance(payload, dict):
        errors.append("TOWER_ACCESS_GLB_STRUCTURE_INVALID")
        return []
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        errors.append("TOWER_ACCESS_GLB_STRUCTURE_INVALID")
        return []
    result: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("extras"), dict):
            continue
        extras = dict(node["extras"])
        if extras.get("semantic_root") == semantic_root:
            result.append({"extras": extras})
    if load_errors:
        errors.append("TOWER_ACCESS_GLB_PARSE_FAILED")
    return result


def _node_points(
    mesh: dict[str, Any],
    accessors: list[Any],
    views: list[Any],
    buffers: list[bytes | None],
    transform: list[list[float]],
    errors: list[str],
) -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []
    for primitive in mesh.get("primitives", []):
        if not isinstance(primitive, dict):
            continue
        attributes = primitive.get("attributes")
        position = attributes.get("POSITION") if isinstance(attributes, dict) else None
        vertices = gltf_integrity._read_accessor(
            accessors,
            views,
            buffers,
            position,
            expected_type="VEC3",
            expected_component_type=5126,
            error_prefix="TOWER_ACCESS_POSITION",
            errors=errors,
        )
        for vertex in vertices or []:
            x, y, z = _apply(transform, (float(vertex[0]), float(vertex[1]), float(vertex[2])))
            if all(math.isfinite(value) for value in (x, y, z)):
                points.append(_gltf_to_scene_point((x, y, z)))
    return points


def _gltf_to_scene_point(
    point: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Undo Blender's (x, y, z) to glTF (x, z, -y) axis mapping."""

    x, y, z = point
    return (x, -z, y)


def _primary_equipment_deck_overlap_count(
    nodes: list[dict[str, Any]], decks: list[dict[str, Any]]
) -> int:
    count = 0
    for deck in decks:
        for node in nodes:
            role = str(
                node["extras"].get("role") or node["extras"].get("object_role") or ""
            ).lower()
            if role in {"antenna", "rru", "radio", "gps", "power_cabinet"} and _aabb_overlap(
                deck["bounds"], node["bounds"]
            ):
                count += 1
    return count


def _platform_index(node: dict[str, Any]) -> int | None:
    value = node["extras"].get("tower_access_platform_index")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _requested_level(node: dict[str, Any]) -> float | None:
    value = node["extras"].get("tower_access_requested_level_m")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _rectangle_dimensions(
    points: list[tuple[float, float, float]], *, expected_width: float, expected_depth: float
) -> tuple[float | None, float | None]:
    horizontal = sorted({(round(x, 6), round(y, 6)) for x, y, _ in points})
    distances = sorted(
        {
            round(math.dist(left, right), 6)
            for index, left in enumerate(horizontal)
            for right in horizontal[index + 1 :]
            if math.dist(left, right) > 1e-6
        }
    )
    if not distances:
        return None, None
    # A rotated rectangular mesh exposes its side lengths and diagonal in world
    # coordinates.  Match each independently measured candidate to the declared
    # side it is meant to verify; no local object transform is trusted here.
    width = min(distances, key=lambda value: abs(value - expected_width))
    depth = min(distances, key=lambda value: abs(value - expected_depth))
    return width, depth


def _world_matrices(nodes: list[Any]) -> dict[int, list[list[float]]]:
    parents: dict[int, int] = {}
    for parent_index, node in enumerate(nodes):
        if isinstance(node, dict):
            for child in node.get("children", []):
                if isinstance(child, int) and 0 <= child < len(nodes):
                    parents[child] = parent_index
    cache: dict[int, list[list[float]]] = {}

    def resolve(index: int, visiting: set[int]) -> list[list[float]]:
        if index in cache:
            return cache[index]
        if index in visiting or not isinstance(nodes[index], dict):
            return _identity()
        local = _node_matrix(nodes[index])
        parent = parents.get(index)
        cache[index] = (
            local if parent is None else _multiply(resolve(parent, {*visiting, index}), local)
        )
        return cache[index]

    for index in range(len(nodes)):
        resolve(index, set())
    return cache


def _node_matrix(node: dict[str, Any]) -> list[list[float]]:
    matrix = node.get("matrix")
    if isinstance(matrix, list) and len(matrix) == 16:
        return [
            [float(matrix[0]), float(matrix[4]), float(matrix[8]), float(matrix[12])],
            [float(matrix[1]), float(matrix[5]), float(matrix[9]), float(matrix[13])],
            [float(matrix[2]), float(matrix[6]), float(matrix[10]), float(matrix[14])],
            [float(matrix[3]), float(matrix[7]), float(matrix[11]), float(matrix[15])],
        ]
    t, r, s = (
        node.get("translation", [0, 0, 0]),
        node.get("rotation", [0, 0, 0, 1]),
        node.get("scale", [1, 1, 1]),
    )
    if not (
        isinstance(t, list)
        and len(t) == 3
        and isinstance(r, list)
        and len(r) == 4
        and isinstance(s, list)
        and len(s) == 3
    ):
        return _identity()
    x, y, z, w = (float(value) for value in r)
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    return [
        [
            (1 - 2 * (yy + zz)) * float(s[0]),
            (2 * (xy - wz)) * float(s[1]),
            (2 * (xz + wy)) * float(s[2]),
            float(t[0]),
        ],
        [
            (2 * (xy + wz)) * float(s[0]),
            (1 - 2 * (xx + zz)) * float(s[1]),
            (2 * (yz - wx)) * float(s[2]),
            float(t[1]),
        ],
        [
            (2 * (xz - wy)) * float(s[0]),
            (2 * (yz + wx)) * float(s[1]),
            (1 - 2 * (xx + yy)) * float(s[2]),
            float(t[2]),
        ],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _identity() -> list[list[float]]:
    return [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]


def _multiply(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [
        [sum(left[row][item] * right[item][column] for item in range(4)) for column in range(4)]
        for row in range(4)
    ]


def _apply(
    matrix: list[list[float]], vertex: tuple[float, float, float]
) -> tuple[float, float, float]:
    return tuple(
        sum(matrix[row][column] * (*vertex, 1.0)[column] for column in range(4)) for row in range(3)
    )  # type: ignore[return-value]


def _bounds(
    points: list[tuple[float, float, float]],
) -> tuple[float, float, float, float, float, float]:
    return (
        min(value[0] for value in points),
        min(value[1] for value in points),
        min(value[2] for value in points),
        max(value[0] for value in points),
        max(value[1] for value in points),
        max(value[2] for value in points),
    )


def _bounds_center(
    bounds: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float]:
    return ((bounds[0] + bounds[3]) / 2, (bounds[1] + bounds[4]) / 2, (bounds[2] + bounds[5]) / 2)


def _aabb_overlap(
    left: tuple[float, float, float, float, float, float],
    right: tuple[float, float, float, float, float, float],
) -> bool:
    return all(
        left[index] < right[index + 3] - 0.005 and right[index] < left[index + 3] - 0.005
        for index in range(3)
    )


def _canonical_json_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
