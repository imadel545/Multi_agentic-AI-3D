from pydantic import Field, model_validator

from core.contracts.common import AssetType, NetworkType, StrictModel


class DimensionsM(StrictModel):
    width: float = Field(gt=0)
    depth: float = Field(gt=0)
    height: float = Field(gt=0)


class MountZone(StrictModel):
    name: str = Field(min_length=1)
    min_height_m: float = Field(ge=0)
    max_height_m: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "MountZone":
        if self.max_height_m < self.min_height_m:
            raise ValueError("max_height_m must be greater than or equal to min_height_m")
        return self


class AssetManifest(StrictModel):
    asset_id: str = Field(min_length=1)
    type: AssetType
    file: str = Field(min_length=1)
    height_m: float | None = Field(default=None, gt=0)
    dimensions_m: DimensionsM | None = None
    compatible_networks: list[NetworkType]
    compatible_tower_types: list[str] = Field(default_factory=list)
    mount_zones: list[MountZone] = Field(default_factory=list)
    status: str = "validated"
    version: str = "1.0.0"

    @property
    def is_validated(self) -> bool:
        return self.status == "validated"
