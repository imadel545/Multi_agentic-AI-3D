"""Bounded world-frame relations shared by generic compilation and exported QA."""

from typing import Literal

from pydantic import Field

from core.contracts.common import StrictModel
from core.contracts.geometry_program import GeometryProgramVector3


class RigidComponentRelation(StrictModel):
    relationship_id: str = Field(min_length=1, max_length=120)
    kind: Literal["aligned_with"] = "aligned_with"
    source_program_id: str
    target_program_id: str
    offset_world_m: GeometryProgramVector3
    tolerance_m: float = Field(default=1e-5, gt=0, le=1e-5)
