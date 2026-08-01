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


GeometryProgramNode = Annotated[
    GeometryPrimitiveNode | GeometryCurveNode | GeometryInstanceNode,
    Field(discriminator="kind"),
]


class GeometryProgram(StrictModel):
    """Executable declarative geometry authored by an LLM or a trusted planner.

    It is data, never Python. The deterministic compiler owns Blender API calls,
    resource budgets, semantic metadata and artifact provenance.
    """

    schema_version: Literal["1.0.0"] = "1.0.0"
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

        semantic_nodes = [node for node in self.nodes if node.semantic_role == self.semantic_role]
        if len(semantic_nodes) != self.requested_quantity:
            raise ValueError(
                "geometry program requires exactly requested_quantity nodes carrying "
                "its semantic_role"
            )
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


def geometry_program_dimensions(program: GeometryProgram) -> tuple[float, float, float]:
    nodes = {node.node_id: node for node in program.nodes}
    world_matrices: dict[str, tuple[tuple[float, ...], ...]] = {}

    def world_matrix(node_id: str) -> tuple[tuple[float, ...], ...]:
        cached = world_matrices.get(node_id)
        if cached is not None:
            return cached
        node = nodes[node_id]
        local = _transform_matrix(node.transform)
        result = (
            _matrix_multiply(world_matrix(node.parent_id), local)
            if node.parent_id is not None
            else local
        )
        world_matrices[node_id] = result
        return result

    def source_geometry(node: GeometryProgramNode) -> GeometryProgramNode:
        current = node
        while isinstance(current, GeometryInstanceNode):
            current = nodes[current.source_node_id]
        return current

    points: list[tuple[float, float, float]] = []
    for node in program.nodes:
        geometry = source_geometry(node)
        local_corners = _geometry_corners(geometry)
        matrix = world_matrix(node.node_id)
        points.extend(_transform_point(matrix, point) for point in local_corners)
    return tuple(
        max(point[axis] for point in points) - min(point[axis] for point in points)
        for axis in range(3)
    )


def _geometry_corners(node: GeometryProgramNode) -> list[tuple[float, float, float]]:
    if isinstance(node, GeometryCurveNode):
        depth = node.bevel_depth_m
        minimum = tuple(
            min(getattr(point, axis) for point in node.points_m) - depth for axis in ("x", "y", "z")
        )
        maximum = tuple(
            max(getattr(point, axis) for point in node.points_m) + depth for axis in ("x", "y", "z")
        )
        return _bounds_corners(minimum, maximum)
    if not isinstance(node, GeometryPrimitiveNode):
        raise ValueError("instance source must resolve to primitive or curve geometry")
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
