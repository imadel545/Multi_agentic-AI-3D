from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NetworkType = Literal["4G", "5G", "MW"]
TowerType = Literal["lattice_tower", "monopole", "rooftop_mast", "small_cell_pole"]
DetailLevel = Literal["low", "medium", "high"]
AssetType = Literal[
    "tower",
    "antenna",
    "radio",
    "cable",
    "bracket",
    "cabinet",
    "gps",
    "beam",
    "marker",
    "label",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        allow_inf_nan=False,
    )


class Vector3(StrictModel):
    x: float
    y: float
    z: float

    def as_list(self) -> list[float]:
        return [self.x, self.y, self.z]


class WarningItem(StrictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
