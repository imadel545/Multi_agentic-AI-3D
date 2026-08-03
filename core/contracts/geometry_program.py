from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import Field, model_validator

from core.contracts.common import StrictModel

ProgramId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=96,
        pattern=r"^[a-z][a-z0-9._-]*$",
    ),
]


class GeometryProgramVector3(StrictModel):
    x: float
    y: float
    z: float


class GeometryProgramVector2(StrictModel):
    x: float
    y: float


class GeometryProgramColor(StrictModel):
    r: float = Field(ge=0.0, le=1.0)
    g: float = Field(ge=0.0, le=1.0)
    b: float = Field(ge=0.0, le=1.0)
    a: float = Field(ge=0.0, le=1.0)


class GeometryProgramTransform(StrictModel):
    """Local transform expressed in Blender's Z-up, meter-based frame."""

    translation_m: GeometryProgramVector3 = Field(
        default_factory=lambda: GeometryProgramVector3(x=0.0, y=0.0, z=0.0)
    )
    rotation_deg: GeometryProgramVector3 = Field(
        default_factory=lambda: GeometryProgramVector3(x=0.0, y=0.0, z=0.0)
    )
    scale: GeometryProgramVector3 = Field(
        default_factory=lambda: GeometryProgramVector3(x=1.0, y=1.0, z=1.0)
    )

    @model_validator(mode="after")
    def validate_transform(self) -> GeometryProgramTransform:
        scale = (self.scale.x, self.scale.y, self.scale.z)
        translation = (
            self.translation_m.x,
            self.translation_m.y,
            self.translation_m.z,
        )
        rotation = (self.rotation_deg.x, self.rotation_deg.y, self.rotation_deg.z)
        if any(component <= 0 or component > 100 for component in scale):
            raise ValueError("geometry-program scale components must be in ]0, 100]")
        if any(abs(component) > 1000 for component in translation):
            raise ValueError("geometry-program translation exceeds the 1000 m local bound")
        if any(abs(component) > 3600 for component in rotation):
            raise ValueError("geometry-program rotation exceeds the bounded range")
        return self


class GeometryProgramMaterial(StrictModel):
    material_id: ProgramId
    base_color_rgba: GeometryProgramColor
    metallic: float = Field(default=0.0, ge=0.0, le=1.0)
    roughness: float = Field(default=0.5, ge=0.0, le=1.0)


class GeometryProgramNodeBase(StrictModel):
    node_id: ProgramId
    parent_id: ProgramId | None = None
    material_id: ProgramId | None = None
    semantic_role: ProgramId | None = None
    transform: GeometryProgramTransform = Field(default_factory=GeometryProgramTransform)


class GeometryPrimitiveNode(GeometryProgramNodeBase):
    kind: Literal["primitive"] = "primitive"
    primitive: Literal["box", "cylinder", "cone", "uv_sphere"]
    size_m: GeometryProgramVector3 | None = None
    radius_m: float | None = Field(default=None, gt=0, le=100)
    top_radius_m: float | None = Field(default=None, ge=0, le=100)
    height_m: float | None = Field(default=None, gt=0, le=300)
    vertices: int = Field(default=24, ge=8, le=96)
    bevel_m: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_primitive_parameters(self) -> GeometryPrimitiveNode:
        if self.primitive == "box":
            if self.size_m is None or any(
                component <= 0 or component > 300
                for component in (self.size_m.x, self.size_m.y, self.size_m.z)
            ):
                raise ValueError("box requires positive size_m components no greater than 300 m")
            if any(
                value is not None for value in (self.radius_m, self.top_radius_m, self.height_m)
            ):
                raise ValueError("box does not accept radius_m, top_radius_m or height_m")
            return self
        if self.primitive == "uv_sphere":
            if self.radius_m is None:
                raise ValueError("uv_sphere requires radius_m")
            if (
                self.size_m is not None
                or self.top_radius_m is not None
                or self.height_m is not None
            ):
                raise ValueError("uv_sphere accepts only radius_m")
            return self
        if self.radius_m is None or self.height_m is None:
            raise ValueError(f"{self.primitive} requires radius_m and height_m")
        if self.size_m is not None:
            raise ValueError(f"{self.primitive} does not accept size_m")
        if self.primitive == "cylinder" and self.top_radius_m is not None:
            raise ValueError("cylinder does not accept top_radius_m")
        if self.primitive == "cone" and self.top_radius_m is None:
            raise ValueError("cone requires top_radius_m")
        return self


class GeometryCurveNode(GeometryProgramNodeBase):
    kind: Literal["curve"] = "curve"
    points_m: list[GeometryProgramVector3] = Field(min_length=2, max_length=128)
    bevel_depth_m: float = Field(gt=0, le=2.0)
    cyclic: bool = False

    @model_validator(mode="after")
    def validate_points(self) -> GeometryCurveNode:
        if any(
            abs(component) > 1000
            for point in self.points_m
            for component in (point.x, point.y, point.z)
        ):
            raise ValueError("curve point exceeds the 1000 m local bound")
        return self


class GeometryInstanceNode(GeometryProgramNodeBase):
    kind: Literal["instance"] = "instance"
    source_node_id: ProgramId


class GeometryProfileNode(GeometryProgramNodeBase):
    """Reusable bounded 2D profile in its local XY plane."""

    kind: Literal["profile"] = "profile"
    points_m: list[GeometryProgramVector2] = Field(min_length=2, max_length=128)
    closed: bool = True

    @model_validator(mode="after")
    def validate_profile(self) -> GeometryProfileNode:
        if self.closed and len(self.points_m) < 3:
            raise ValueError("closed geometry profile requires at least three points")
        points = [(point.x, point.y) for point in self.points_m]
        if any(abs(value) > 300 for point in points for value in point):
            raise ValueError("geometry profile point exceeds the 300 m local bound")
        if any(points[index] == points[index - 1] for index in range(1, len(points))):
            raise ValueError("geometry profile contains consecutive duplicate points")
        if self.closed:
            if points[0] == points[-1]:
                raise ValueError("closed geometry profile must not repeat its first point")
            area = sum(
                points[index][0] * points[(index + 1) % len(points)][1]
                - points[(index + 1) % len(points)][0] * points[index][1]
                for index in range(len(points))
            )
            if abs(area) <= 1e-9:
                raise ValueError("closed geometry profile must have non-zero area")
            if _polygon_self_intersects(points):
                raise ValueError("closed geometry profile must not self-intersect")
        return self


class GeometryExtrudeNode(GeometryProgramNodeBase):
    kind: Literal["extrude"] = "extrude"
    profile_node_id: ProgramId
    depth_m: float = Field(gt=0, le=300)


class GeometryRevolveNode(GeometryProgramNodeBase):
    kind: Literal["revolve"] = "revolve"
    profile_node_id: ProgramId
    angle_deg: float = Field(default=360.0, gt=0, le=360)
    segments: int = Field(default=32, ge=8, le=128)


class GeometrySweepNode(GeometryProgramNodeBase):
    kind: Literal["sweep"] = "sweep"
    profile_node_id: ProgramId
    path_points_m: list[GeometryProgramVector3] = Field(min_length=2, max_length=128)
    cyclic: bool = False

    @model_validator(mode="after")
    def validate_path(self) -> GeometrySweepNode:
        points = [(point.x, point.y, point.z) for point in self.path_points_m]
        if any(abs(value) > 1000 for point in points for value in point):
            raise ValueError("sweep path point exceeds the 1000 m local bound")
        if any(points[index] == points[index - 1] for index in range(1, len(points))):
            raise ValueError("sweep path contains consecutive duplicate points")
        if self.cyclic and len(points) < 3:
            raise ValueError("cyclic sweep path requires at least three points")
        return self


class GeometryArrayNode(GeometryProgramNodeBase):
    kind: Literal["array"] = "array"
    source_node_id: ProgramId
    count: int = Field(ge=2, le=128)
    offset_m: GeometryProgramVector3

    @model_validator(mode="after")
    def validate_array(self) -> GeometryArrayNode:
        offset = (self.offset_m.x, self.offset_m.y, self.offset_m.z)
        if all(abs(value) <= 1e-12 for value in offset):
            raise ValueError("geometry array offset must be non-zero")
        if any(abs(value) > 300 for value in offset):
            raise ValueError("geometry array offset exceeds the 300 m bound")
        return self


class GeometryBooleanNode(GeometryProgramNodeBase):
    kind: Literal["boolean"] = "boolean"
    left_node_id: ProgramId
    right_node_id: ProgramId
    operation: Literal["union", "difference", "intersection"]
    solver: Literal["exact"] = "exact"

    @model_validator(mode="after")
    def validate_operands(self) -> GeometryBooleanNode:
        if self.left_node_id == self.right_node_id:
            raise ValueError("geometry boolean requires two distinct operands")
        return self


class GeometryModifierNode(GeometryProgramNodeBase):
    kind: Literal["modifier"] = "modifier"
    source_node_id: ProgramId
    modifier: Literal["bevel", "solidify", "mirror"]
    width_m: float | None = Field(default=None, gt=0, le=2)
    thickness_m: float | None = Field(default=None, ge=-5, le=5)
    segments: int = Field(default=3, ge=1, le=8)
    mirror_axes: list[Literal["x", "y", "z"]] = Field(default_factory=list, max_length=3)
    merge_distance_m: float = Field(default=0.001, ge=0, le=0.1)

    @model_validator(mode="after")
    def validate_modifier(self) -> GeometryModifierNode:
        if self.modifier == "bevel":
            if self.width_m is None or self.thickness_m is not None or self.mirror_axes:
                raise ValueError("bevel modifier requires only width_m and segments")
        elif self.modifier == "solidify":
            if self.thickness_m in (None, 0) or self.width_m is not None or self.mirror_axes:
                raise ValueError("solidify modifier requires only non-zero thickness_m")
        else:
            if (
                not self.mirror_axes
                or len(self.mirror_axes) != len(set(self.mirror_axes))
                or self.width_m is not None
                or self.thickness_m is not None
            ):
                raise ValueError("mirror modifier requires unique mirror_axes only")
        return self


class GeometryTerrainNode(GeometryProgramNodeBase):
    kind: Literal["terrain"] = "terrain"
    width_m: float = Field(gt=0, le=1000)
    depth_m: float = Field(gt=0, le=1000)
    columns: int = Field(ge=2, le=64)
    rows: int = Field(ge=2, le=64)
    heights_m: list[float] = Field(min_length=4, max_length=4096)

    @model_validator(mode="after")
    def validate_heightfield(self) -> GeometryTerrainNode:
        if self.columns * self.rows != len(self.heights_m):
            raise ValueError("terrain heights_m length must equal columns times rows")
        if any(abs(height) > 100 for height in self.heights_m):
            raise ValueError("terrain height exceeds the 100 m local bound")
        return self


GeometryProgramNode = Annotated[
    GeometryPrimitiveNode
    | GeometryCurveNode
    | GeometryInstanceNode
    | GeometryProfileNode
    | GeometryExtrudeNode
    | GeometryRevolveNode
    | GeometrySweepNode
    | GeometryArrayNode
    | GeometryBooleanNode
    | GeometryModifierNode
    | GeometryTerrainNode,
    Field(discriminator="kind"),
]


class GeometryProgramAnchor(StrictModel):
    anchor_id: ProgramId
    node_id: ProgramId
    position_m: GeometryProgramVector3 = Field(
        default_factory=lambda: GeometryProgramVector3(x=0.0, y=0.0, z=0.0)
    )
    normal: GeometryProgramVector3 = Field(
        default_factory=lambda: GeometryProgramVector3(x=0.0, y=1.0, z=0.0)
    )
    up: GeometryProgramVector3 = Field(
        default_factory=lambda: GeometryProgramVector3(x=0.0, y=0.0, z=1.0)
    )

    @model_validator(mode="after")
    def validate_frame(self) -> GeometryProgramAnchor:
        normal = (self.normal.x, self.normal.y, self.normal.z)
        up = (self.up.x, self.up.y, self.up.z)
        normal_length = math.sqrt(sum(value * value for value in normal))
        up_length = math.sqrt(sum(value * value for value in up))
        if normal_length <= 1e-9 or up_length <= 1e-9:
            raise ValueError("geometry anchor normal and up must be non-zero")
        dot = sum(normal[index] * up[index] for index in range(3)) / (normal_length * up_length)
        if abs(dot) >= 1.0 - 1e-7:
            raise ValueError("geometry anchor normal and up must not be parallel")
        if any(
            abs(value) > 1000 for value in (self.position_m.x, self.position_m.y, self.position_m.z)
        ):
            raise ValueError("geometry anchor position exceeds the 1000 m local bound")
        return self


class GeometryProgramConnector(StrictModel):
    connector_id: ProgramId
    anchor_id: ProgramId
    kind: Literal["mechanical", "power", "fiber", "rf", "grounding", "routing"]
    gender: Literal["source", "target", "male", "female", "bidirectional"] = "bidirectional"
    compatible_kinds: list[
        Literal["mechanical", "power", "fiber", "rf", "grounding", "routing"]
    ] = Field(default_factory=list, max_length=6)
    tolerance_m: float = Field(default=0.01, gt=0, le=1)

    @model_validator(mode="after")
    def validate_compatibility(self) -> GeometryProgramConnector:
        if len(self.compatible_kinds) != len(set(self.compatible_kinds)):
            raise ValueError("geometry connector compatible kinds must be unique")
        return self


class GeometryProgramSemanticGroup(StrictModel):
    group_id: ProgramId
    semantic_role: ProgramId
    node_ids: list[ProgramId] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_nodes(self) -> GeometryProgramSemanticGroup:
        if len(self.node_ids) != len(set(self.node_ids)):
            raise ValueError("geometry semantic group node IDs must be unique")
        return self


class GeometryProgram(StrictModel):
    """Executable declarative geometry authored by an LLM or a trusted planner.

    It is data, never Python. The deterministic compiler owns Blender API calls,
    resource budgets, semantic metadata and artifact provenance.
    """

    schema_version: Literal["1.0.0", "2.0.0"] = "1.0.0"
    program_id: ProgramId
    semantic_role: ProgramId
    requested_quantity: int = Field(default=1, ge=1, le=32)
    units: Literal["meters"] = "meters"
    authorship: Literal["llm_generated", "deterministic_generated"]
    generator_provider: str = Field(min_length=1, max_length=120)
    generator_model: str = Field(min_length=1, max_length=160)
    structured_output_mode: Literal[
        "strict_json_schema",
        "json_object_validated",
        "json_object_repaired",
    ]
    source_prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_description: str | None = Field(default=None, min_length=8, max_length=2400)
    source_description_origin: Literal[
        "user_requirement",
        "revision_preserved",
        "legacy_unavailable",
    ] = "legacy_unavailable"
    placement_context: str | None = Field(default=None, max_length=600)
    maximum_dimensions_m: GeometryProgramVector3 | None = None
    materials: list[GeometryProgramMaterial] = Field(default_factory=list, max_length=64)
    nodes: list[GeometryProgramNode] = Field(min_length=1, max_length=512)
    anchors: list[GeometryProgramAnchor] = Field(
        default_factory=list,
        max_length=128,
        exclude_if=lambda value: not value,
    )
    connectors: list[GeometryProgramConnector] = Field(
        default_factory=list,
        max_length=128,
        exclude_if=lambda value: not value,
    )
    semantic_groups: list[GeometryProgramSemanticGroup] = Field(
        default_factory=list,
        max_length=128,
        exclude_if=lambda value: not value,
    )
    construction_node_ids: list[ProgramId] = Field(
        default_factory=list,
        max_length=256,
        exclude_if=lambda value: not value,
    )
    assumptions: list[str] = Field(default_factory=list, max_length=32)
    limitations: list[str] = Field(default_factory=list, max_length=32)
    deterministic_adjustments: list[str] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_program_graph(self) -> GeometryProgram:
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("geometry-program node IDs must be unique")
        known_nodes = set(node_ids)
        material_ids = [material.material_id for material in self.materials]
        if len(material_ids) != len(set(material_ids)):
            raise ValueError("geometry-program material IDs must be unique")
        known_materials = set(material_ids)

        v2_node_types = (
            GeometryProfileNode,
            GeometryExtrudeNode,
            GeometryRevolveNode,
            GeometrySweepNode,
            GeometryArrayNode,
            GeometryBooleanNode,
            GeometryModifierNode,
            GeometryTerrainNode,
        )
        if self.schema_version == "1.0.0" and (
            any(isinstance(node, v2_node_types) for node in self.nodes)
            or self.anchors
            or self.connectors
            or self.semantic_groups
            or self.construction_node_ids
        ):
            raise ValueError("geometry-program V2 capabilities require schema_version 2.0.0")

        for node in self.nodes:
            if node.parent_id is not None and node.parent_id not in known_nodes:
                raise ValueError(f"node {node.node_id!r} references an unknown parent")
            if node.parent_id == node.node_id:
                raise ValueError(f"node {node.node_id!r} cannot parent itself")
            if node.material_id is not None and node.material_id not in known_materials:
                raise ValueError(f"node {node.node_id!r} references an unknown material")
            if isinstance(node, GeometryInstanceNode):
                if node.source_node_id not in known_nodes:
                    raise ValueError(f"instance {node.node_id!r} references an unknown source")
                if node.source_node_id == node.node_id:
                    raise ValueError(f"instance {node.node_id!r} cannot instance itself")

        node_by_id = {node.node_id: node for node in self.nodes}
        dependencies: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
        for node in self.nodes:
            if node.parent_id is not None:
                dependencies[node.node_id].add(node.parent_id)
            if isinstance(node, (GeometryInstanceNode, GeometryArrayNode, GeometryModifierNode)):
                _require_known_reference(node.node_id, node.source_node_id, known_nodes)
                dependencies[node.node_id].add(node.source_node_id)
            if isinstance(node, GeometryArrayNode) and not _node_resolves_to_mesh(
                node.source_node_id, node_by_id, set()
            ):
                raise ValueError(f"array node {node.node_id!r} requires a mesh source")
            if isinstance(node, (GeometryExtrudeNode, GeometryRevolveNode, GeometrySweepNode)):
                _require_known_reference(node.node_id, node.profile_node_id, known_nodes)
                profile = node_by_id[node.profile_node_id]
                if not isinstance(profile, GeometryProfileNode):
                    raise ValueError(f"node {node.node_id!r} requires a profile source")
                if (
                    isinstance(node, (GeometryExtrudeNode, GeometrySweepNode))
                    and not profile.closed
                ):
                    raise ValueError(f"node {node.node_id!r} requires a closed profile")
                if isinstance(node, GeometryRevolveNode) and (
                    any(point.x < 0 for point in profile.points_m)
                    or not any(point.x > 0 for point in profile.points_m)
                ):
                    raise ValueError(f"revolve node {node.node_id!r} requires non-negative radii")
                dependencies[node.node_id].add(node.profile_node_id)
            if isinstance(node, GeometryBooleanNode):
                for operand_id in (node.left_node_id, node.right_node_id):
                    _require_known_reference(node.node_id, operand_id, known_nodes)
                    if not _node_resolves_to_mesh(operand_id, node_by_id, set()):
                        raise ValueError(f"boolean node {node.node_id!r} requires mesh operands")
                    dependencies[node.node_id].add(operand_id)
            if isinstance(node, GeometryModifierNode) and not _node_resolves_to_mesh(
                node.source_node_id, node_by_id, set()
            ):
                raise ValueError(f"modifier node {node.node_id!r} requires a mesh source")
            if isinstance(node, GeometryProfileNode):
                if (
                    node.parent_id is not None
                    or node.material_id is not None
                    or node.semantic_role is not None
                    or node.transform != GeometryProgramTransform()
                ):
                    raise ValueError("geometry profile nodes are transform-free definitions")

        parents = {node.node_id: node.parent_id for node in self.nodes}
        for node_id in node_ids:
            visited: set[str] = set()
            current: str | None = node_id
            while current is not None:
                if current in visited:
                    raise ValueError("geometry-program parent graph contains a cycle")
                visited.add(current)
                current = parents[current]

        instance_sources = {
            node.node_id: node.source_node_id
            for node in self.nodes
            if isinstance(node, GeometryInstanceNode)
        }
        for node_id in instance_sources:
            visited: set[str] = set()
            current = node_id
            while current in instance_sources:
                if current in visited:
                    raise ValueError("geometry-program instance graph contains a cycle")
                visited.add(current)
                current = instance_sources[current]

        _validate_dependency_graph(dependencies)

        construction_ids = self.construction_node_ids
        if len(construction_ids) != len(set(construction_ids)):
            raise ValueError("geometry-program construction node IDs must be unique")
        if not set(construction_ids).issubset(known_nodes):
            raise ValueError("geometry-program construction nodes reference unknown nodes")
        profile_ids = {node.node_id for node in self.nodes if isinstance(node, GeometryProfileNode)}
        if not profile_ids.issubset(construction_ids):
            raise ValueError("geometry profile nodes must be construction-only")

        anchor_ids = [anchor.anchor_id for anchor in self.anchors]
        if len(anchor_ids) != len(set(anchor_ids)):
            raise ValueError("geometry-program anchor IDs must be unique")
        for anchor in self.anchors:
            if anchor.node_id not in known_nodes:
                raise ValueError(f"anchor {anchor.anchor_id!r} references an unknown node")
        connector_ids = [connector.connector_id for connector in self.connectors]
        if len(connector_ids) != len(set(connector_ids)):
            raise ValueError("geometry-program connector IDs must be unique")
        known_anchors = set(anchor_ids)
        for connector in self.connectors:
            if connector.anchor_id not in known_anchors:
                raise ValueError(
                    f"connector {connector.connector_id!r} references an unknown anchor"
                )
        group_ids = [group.group_id for group in self.semantic_groups]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("geometry-program semantic group IDs must be unique")
        for group in self.semantic_groups:
            if not set(group.node_ids).issubset(known_nodes):
                raise ValueError(f"semantic group {group.group_id!r} references unknown nodes")

        semantic_nodes = [node for node in self.nodes if node.semantic_role == self.semantic_role]
        if len(semantic_nodes) != self.requested_quantity:
            raise ValueError(
                "geometry program requires exactly requested_quantity nodes carrying "
                "its semantic_role"
            )
        if any(node.node_id in construction_ids for node in semantic_nodes):
            raise ValueError("primary semantic nodes cannot be construction-only")
        if self.authorship == "llm_generated" and len(self.nodes) < 3:
            raise ValueError(
                "LLM-authored geometry programs require at least three semantic/detail nodes"
            )
        if self.maximum_dimensions_m is not None:
            maximum = self.maximum_dimensions_m
            if any(value <= 0 or value > 300 for value in (maximum.x, maximum.y, maximum.z)):
                raise ValueError(
                    "geometry-program maximum_dimensions_m components must be in ]0, 300]"
                )
            actual = geometry_program_dimensions(self)
            for axis, actual_value, maximum_value in zip(
                ("x", "y", "z"),
                actual,
                (maximum.x, maximum.y, maximum.z),
                strict=True,
            ):
                if actual_value > maximum_value + 1e-6:
                    raise ValueError(
                        f"geometry-program {axis} dimension {actual_value:.6f} m "
                        f"exceeds maximum {maximum_value:.6f} m"
                    )
        return self


def _require_known_reference(node_id: str, reference_id: str, known_nodes: set[str]) -> None:
    if reference_id not in known_nodes:
        raise ValueError(f"node {node_id!r} references unknown geometry {reference_id!r}")
    if reference_id == node_id:
        raise ValueError(f"node {node_id!r} cannot reference itself")


def _validate_dependency_graph(dependencies: dict[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            raise ValueError("geometry-program dependency graph contains a cycle")
        visiting.add(node_id)
        for dependency in dependencies[node_id]:
            visit(dependency)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in dependencies:
        visit(node_id)


def _node_resolves_to_mesh(
    node_id: str,
    nodes: dict[str, GeometryProgramNode],
    visiting: set[str],
) -> bool:
    if node_id in visiting:
        return False
    visiting.add(node_id)
    node = nodes[node_id]
    if isinstance(
        node,
        (
            GeometryPrimitiveNode,
            GeometryExtrudeNode,
            GeometryRevolveNode,
            GeometrySweepNode,
            GeometryTerrainNode,
            GeometryBooleanNode,
        ),
    ):
        return True
    if isinstance(node, (GeometryInstanceNode, GeometryArrayNode, GeometryModifierNode)):
        return _node_resolves_to_mesh(node.source_node_id, nodes, visiting)
    return False


def geometry_program_dimensions(program: GeometryProgram) -> tuple[float, float, float]:
    minimum, maximum = geometry_program_bounds(program)
    return tuple(maximum[axis] - minimum[axis] for axis in range(3))


def geometry_program_bounds(
    program: GeometryProgram,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return the visible program envelope in its validated Z-up world frame."""

    nodes = {node.node_id: node for node in program.nodes}
    world_matrices: dict[str, tuple[tuple[float, ...], ...]] = {}

    points: list[tuple[float, float, float]] = []
    for node in program.nodes:
        if node.node_id in program.construction_node_ids:
            continue
        local_corners = _geometry_corners(node, nodes, set())
        matrix = _node_world_matrix(node.node_id, nodes, world_matrices)
        points.extend(_transform_point(matrix, point) for point in local_corners)
    if not points:
        raise ValueError("geometry-program has no visible geometry bounds")
    return _point_bounds(points)


def geometry_program_visible_root_bounds(
    program: GeometryProgram,
) -> dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]]:
    """Return bounds for each independently transformed visible root output."""

    nodes = {node.node_id: node for node in program.nodes}
    construction = set(program.construction_node_ids)
    bounds: dict[
        str,
        tuple[tuple[float, float, float], tuple[float, float, float]],
    ] = {}
    for node in program.nodes:
        if node.node_id in construction or node.parent_id is not None:
            continue
        local_corners = _geometry_corners(node, nodes, set())
        matrix = _node_world_matrix(node.node_id, nodes, {})
        bounds[node.node_id] = _point_bounds(
            [_transform_point(matrix, point) for point in local_corners]
        )
    return bounds


def _geometry_corners(
    node: GeometryProgramNode,
    nodes: dict[str, GeometryProgramNode],
    visiting: set[str],
) -> list[tuple[float, float, float]]:
    if node.node_id in visiting:
        raise ValueError("geometry-program geometry reference contains a cycle")
    next_visiting = {*visiting, node.node_id}
    if isinstance(node, GeometryInstanceNode):
        return _geometry_corners(nodes[node.source_node_id], nodes, next_visiting)
    if isinstance(node, GeometryArrayNode):
        source = _geometry_corners(nodes[node.source_node_id], nodes, next_visiting)
        offset = (node.offset_m.x, node.offset_m.y, node.offset_m.z)
        return [
            tuple(point[axis] + offset[axis] * index for axis in range(3))
            for index in range(node.count)
            for point in source
        ]
    if isinstance(node, GeometryBooleanNode):
        left = _transformed_geometry_corners(nodes[node.left_node_id], nodes, next_visiting)
        if node.operation == "difference":
            return left
        right = _transformed_geometry_corners(nodes[node.right_node_id], nodes, next_visiting)
        if node.operation == "union":
            return [*left, *right]
        left_minimum, left_maximum = _point_bounds(left)
        right_minimum, right_maximum = _point_bounds(right)
        minimum = tuple(max(left_minimum[axis], right_minimum[axis]) for axis in range(3))
        maximum = tuple(min(left_maximum[axis], right_maximum[axis]) for axis in range(3))
        if any(minimum[axis] > maximum[axis] for axis in range(3)):
            raise ValueError("geometry-program intersection operands do not overlap")
        return _bounds_corners(minimum, maximum)
    if isinstance(node, GeometryModifierNode):
        source = _geometry_corners(nodes[node.source_node_id], nodes, next_visiting)
        minimum, maximum = _point_bounds(source)
        if node.modifier == "bevel":
            padding = float(node.width_m or 0.0)
            return _bounds_corners(
                tuple(value - padding for value in minimum),
                tuple(value + padding for value in maximum),
            )
        if node.modifier == "solidify":
            padding = abs(float(node.thickness_m or 0.0))
            return _bounds_corners(
                tuple(value - padding for value in minimum),
                tuple(value + padding for value in maximum),
            )
        mirrored = list(source)
        for point in source:
            reflected = list(point)
            for axis_name in node.mirror_axes:
                reflected[{"x": 0, "y": 1, "z": 2}[axis_name]] *= -1
            mirrored.append(tuple(reflected))
        return mirrored
    if isinstance(node, GeometryCurveNode):
        depth = node.bevel_depth_m
        minimum = tuple(
            min(getattr(point, axis) for point in node.points_m) - depth for axis in ("x", "y", "z")
        )
        maximum = tuple(
            max(getattr(point, axis) for point in node.points_m) + depth for axis in ("x", "y", "z")
        )
        return _bounds_corners(minimum, maximum)
    if isinstance(node, GeometryProfileNode):
        minimum = (
            min(point.x for point in node.points_m),
            min(point.y for point in node.points_m),
            0.0,
        )
        maximum = (
            max(point.x for point in node.points_m),
            max(point.y for point in node.points_m),
            0.0,
        )
        return _bounds_corners(minimum, maximum)
    if isinstance(node, GeometryExtrudeNode):
        profile = nodes[node.profile_node_id]
        assert isinstance(profile, GeometryProfileNode)
        half_depth = node.depth_m / 2.0
        return _bounds_corners(
            (
                min(point.x for point in profile.points_m),
                min(point.y for point in profile.points_m),
                -half_depth,
            ),
            (
                max(point.x for point in profile.points_m),
                max(point.y for point in profile.points_m),
                half_depth,
            ),
        )
    if isinstance(node, GeometryRevolveNode):
        profile = nodes[node.profile_node_id]
        assert isinstance(profile, GeometryProfileNode)
        radius = max(abs(point.x) for point in profile.points_m)
        return _bounds_corners(
            (-radius, -radius, min(point.y for point in profile.points_m)),
            (radius, radius, max(point.y for point in profile.points_m)),
        )
    if isinstance(node, GeometrySweepNode):
        profile = nodes[node.profile_node_id]
        assert isinstance(profile, GeometryProfileNode)
        return _sweep_vertices(node, profile)
    if isinstance(node, GeometryTerrainNode):
        return _bounds_corners(
            (-node.width_m / 2.0, -node.depth_m / 2.0, min(node.heights_m)),
            (node.width_m / 2.0, node.depth_m / 2.0, max(node.heights_m)),
        )
    if not isinstance(node, GeometryPrimitiveNode):
        raise ValueError(f"unsupported geometry-program node kind: {node.kind}")
    if node.primitive == "box":
        assert node.size_m is not None
        half = (node.size_m.x / 2, node.size_m.y / 2, node.size_m.z / 2)
    elif node.primitive == "uv_sphere":
        assert node.radius_m is not None
        half = (node.radius_m, node.radius_m, node.radius_m)
    else:
        assert node.radius_m is not None and node.height_m is not None
        radius = max(node.radius_m, node.top_radius_m or 0.0)
        half = (radius, radius, node.height_m / 2)
    return _bounds_corners(tuple(-value for value in half), half)


def _sweep_vertices(
    node: GeometrySweepNode,
    profile: GeometryProfileNode,
) -> list[tuple[float, float, float]]:
    """Mirror the deterministic Blender sweep frame exactly for envelope QA.

    A radial approximation is incorrect for asymmetric profiles: it doubles a
    one-sided vertical profile and can trigger an unnecessary global scale.
    Keeping the contract and compiler on the same tangent/normal/binormal
    construction prevents validated dimensions from diverging from the GLB.
    """

    path = [(point.x, point.y, point.z) for point in node.path_points_m]
    vertices: list[tuple[float, float, float]] = []
    for index, center in enumerate(path):
        previous = path[index - 1] if index > 0 else (path[-1] if node.cyclic else center)
        following = (
            path[(index + 1) % len(path)] if index + 1 < len(path) or node.cyclic else center
        )
        tangent = _normalize_vector(_subtract_vectors(following, previous))
        reference = (0.0, 0.0, 1.0)
        if abs(_dot_vectors(tangent, reference)) > 0.95:
            reference = (1.0, 0.0, 0.0)
        normal = _normalize_vector(_cross_vectors(tangent, reference))
        binormal = _normalize_vector(_cross_vectors(tangent, normal))
        for point in profile.points_m:
            vertices.append(
                tuple(
                    center[axis] + normal[axis] * point.x + binormal[axis] * point.y
                    for axis in range(3)
                )
            )
    return vertices


def _subtract_vectors(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return tuple(left[axis] - right[axis] for axis in range(3))


def _dot_vectors(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> float:
    return sum(left[axis] * right[axis] for axis in range(3))


def _cross_vectors(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _normalize_vector(
    value: tuple[float, float, float],
) -> tuple[float, float, float]:
    length = math.sqrt(_dot_vectors(value, value))
    if length <= 1e-12:
        return (0.0, 0.0, 0.0)
    return tuple(component / length for component in value)


def _transformed_geometry_corners(
    node: GeometryProgramNode,
    nodes: dict[str, GeometryProgramNode],
    visiting: set[str],
) -> list[tuple[float, float, float]]:
    """Return referenced Boolean operand geometry in program/world space.

    Boolean inputs are spatial operands. Their complete parent/local transform
    is therefore part of the operation and must be reflected by the bounded
    envelope contract just as it is by the deterministic Blender compiler.
    """

    local_corners = _geometry_corners(node, nodes, visiting)
    matrix = _node_world_matrix(node.node_id, nodes, {})
    return [_transform_point(matrix, point) for point in local_corners]


def _node_world_matrix(
    node_id: str,
    nodes: dict[str, GeometryProgramNode],
    cache: dict[str, tuple[tuple[float, ...], ...]],
) -> tuple[tuple[float, ...], ...]:
    cached = cache.get(node_id)
    if cached is not None:
        return cached
    node = nodes[node_id]
    local = _transform_matrix(node.transform)
    result = (
        _matrix_multiply(_node_world_matrix(node.parent_id, nodes, cache), local)
        if node.parent_id is not None
        else local
    )
    cache[node_id] = result
    return result


def _point_bounds(
    points: list[tuple[float, float, float]],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    return (
        tuple(min(point[axis] for point in points) for axis in range(3)),
        tuple(max(point[axis] for point in points) for axis in range(3)),
    )


def _bounds_corners(
    minimum: tuple[float, float, float],
    maximum: tuple[float, float, float],
) -> list[tuple[float, float, float]]:
    return [
        (x, y, z)
        for x in (minimum[0], maximum[0])
        for y in (minimum[1], maximum[1])
        for z in (minimum[2], maximum[2])
    ]


def _transform_matrix(
    transform: GeometryProgramTransform,
) -> tuple[tuple[float, ...], ...]:
    rx, ry, rz = (
        math.radians(transform.rotation_deg.x),
        math.radians(transform.rotation_deg.y),
        math.radians(transform.rotation_deg.z),
    )
    sx, sy, sz = transform.scale.x, transform.scale.y, transform.scale.z
    cx, cy, cz = math.cos(rx), math.cos(ry), math.cos(rz)
    sinx, siny, sinz = math.sin(rx), math.sin(ry), math.sin(rz)
    rotation = (
        (cz * cy, cz * siny * sinx - sinz * cx, cz * siny * cx + sinz * sinx),
        (sinz * cy, sinz * siny * sinx + cz * cx, sinz * siny * cx - cz * sinx),
        (-siny, cy * sinx, cy * cx),
    )
    translation = transform.translation_m
    return (
        (rotation[0][0] * sx, rotation[0][1] * sy, rotation[0][2] * sz, translation.x),
        (rotation[1][0] * sx, rotation[1][1] * sy, rotation[1][2] * sz, translation.y),
        (rotation[2][0] * sx, rotation[2][1] * sy, rotation[2][2] * sz, translation.z),
        (0.0, 0.0, 0.0, 1.0),
    )


def _matrix_multiply(
    left: tuple[tuple[float, ...], ...],
    right: tuple[tuple[float, ...], ...],
) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple(
            sum(left[row][item] * right[item][column] for item in range(4)) for column in range(4)
        )
        for row in range(4)
    )


def _transform_point(
    matrix: tuple[tuple[float, ...], ...],
    point: tuple[float, float, float],
) -> tuple[float, float, float]:
    vector = (*point, 1.0)
    return tuple(
        sum(matrix[row][column] * vector[column] for column in range(4)) for row in range(3)
    )


def _polygon_self_intersects(points: list[tuple[float, float]]) -> bool:
    edge_count = len(points)
    for first_index in range(edge_count):
        first = (points[first_index], points[(first_index + 1) % edge_count])
        for second_index in range(first_index + 1, edge_count):
            if second_index in {
                first_index,
                (first_index + 1) % edge_count,
                (first_index - 1) % edge_count,
            }:
                continue
            second = (points[second_index], points[(second_index + 1) % edge_count])
            if _segments_intersect(first[0], first[1], second[0], second[1]):
                return True
    return False


def _segments_intersect(
    first_start: tuple[float, float],
    first_end: tuple[float, float],
    second_start: tuple[float, float],
    second_end: tuple[float, float],
) -> bool:
    def orientation(
        start: tuple[float, float],
        end: tuple[float, float],
        point: tuple[float, float],
    ) -> float:
        return (end[0] - start[0]) * (point[1] - start[1]) - (end[1] - start[1]) * (
            point[0] - start[0]
        )

    first_side = orientation(first_start, first_end, second_start)
    second_side = orientation(first_start, first_end, second_end)
    third_side = orientation(second_start, second_end, first_start)
    fourth_side = orientation(second_start, second_end, first_end)
    return first_side * second_side < -1e-12 and third_side * fourth_side < -1e-12
