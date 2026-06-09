from core.contracts.assets import AssetManifest
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import (
    RuntimeAssetMetadata,
    SceneAccessoryPlacement,
    SceneAssetPlacement,
    SceneSpec,
    SectorSpec,
    VisualElements,
)


class ScenePlanner:
    def build_scene_spec(
        self,
        workflow_id: str,
        requirements: RequirementSpec,
        tower: AssetManifest,
        antenna: AssetManifest,
        radio: AssetManifest | None,
        accessory_assets: list[AssetManifest] | None = None,
        rag_context: list[dict] | None = None,
        memory_recall: dict | None = None,
    ) -> SceneSpec:
        visual_elements = VisualElements(
            include_sector_beams=requirements.include_beams,
            include_azimuth_arrows=True,
            include_height_markers=True,
            include_labels=requirements.include_labels,
            include_power_cabinet=requirements.include_power_cabinet,
            include_gps_antenna=requirements.include_gps_antenna,
        )
        beamwidth = requirements.beamwidth_deg
        install_height = requirements.antenna_install_height_m
        include_cables = requirements.include_cables
        if rag_context:
            for ctx in rag_context:
                hints = _planning_hints(ctx)
                beamwidth = _bounded_float_hint(
                    hints, "beamwidth_deg", beamwidth, minimum=1.0, maximum=360.0
                )
                install_height = _bounded_float_hint(
                    hints,
                    "antenna_install_height_m",
                    install_height,
                    minimum=0.1,
                    maximum=requirements.tower_height_m,
                )
                if isinstance(hints.get("include_cables"), bool):
                    include_cables = hints["include_cables"]
                if isinstance(hints.get("include_sector_beams"), bool):
                    visual_elements.include_sector_beams = hints["include_sector_beams"]

        if memory_recall:
            for err in memory_recall.get("error_patterns", []):
                code = err.get("issue_code", "")
                if code == "RF_AZIMUTH_SPACING_LOW":
                    visual_elements.include_sector_beams = True

        sectors = [
            SectorSpec(
                sector_id=f"S{index + 1}",
                antenna_asset_id=antenna.asset_id,
                antenna_asset_file=antenna.file,
                antenna_asset_source=antenna.source,
                antenna_asset_metadata=_runtime_asset_metadata(antenna),
                antenna_import_fallback_allowed=antenna.import_fallback_allowed,
                radio_asset_id=radio.asset_id if radio else None,
                radio_asset_file=radio.file if radio else None,
                radio_asset_source=radio.source if radio else None,
                radio_asset_metadata=_runtime_asset_metadata(radio)
                if radio
                else RuntimeAssetMetadata(),
                radio_import_fallback_allowed=radio.import_fallback_allowed if radio else True,
                install_height_m=install_height,
                azimuth_deg=azimuth,
                mechanical_tilt_deg=requirements.mechanical_tilt_deg,
                electrical_tilt_deg=requirements.electrical_tilt_deg,
                beamwidth_deg=beamwidth,
                antenna_dimensions_m=antenna.dimensions_m,
                radio_dimensions_m=radio.dimensions_m if radio else None,
                include_cable=include_cables,
                include_label=requirements.include_labels,
            )
            for index, azimuth in enumerate(requirements.azimuths_deg)
        ]
        return SceneSpec(
            scene_id=workflow_id,
            network_type=requirements.network_type,
            tower=SceneAssetPlacement(
                asset_id=tower.asset_id,
                asset_file=tower.file,
                asset_source=tower.source,
                asset_metadata=_runtime_asset_metadata(tower),
                import_fallback_allowed=tower.import_fallback_allowed,
                dimensions_m=tower.dimensions_m,
                position=[0.0, 0.0, 0.0],
                rotation_deg=[0.0, 0.0, 0.0],
                scale=[1.0, 1.0, 1.0],
                height_m=requirements.tower_height_m,
                characteristics=requirements.tower_characteristics,
            ),
            sectors=sectors,
            visual_elements=visual_elements,
            accessory_assets=_accessory_placements(
                requirements=requirements,
                tower=tower,
                assets=accessory_assets or [],
            ),
        )


def _runtime_asset_metadata(asset: AssetManifest) -> RuntimeAssetMetadata:
    return RuntimeAssetMetadata(
        license=asset.license,
        attribution_required=asset.attribution_required,
        attribution=asset.attribution,
        original_url=asset.original_url,
        original_author=asset.original_author,
        normalized_by=asset.normalized_by,
        pivot_policy=asset.pivot_policy,
        front_axis=asset.front_axis,
    )


def _accessory_placements(
    *,
    requirements: RequirementSpec,
    tower: AssetManifest,
    assets: list[AssetManifest],
) -> list[SceneAccessoryPlacement]:
    placements: list[SceneAccessoryPlacement] = []
    assets_by_type = {asset.type: asset for asset in assets}
    base_width = (
        requirements.tower_characteristics.base_width_m
        or (tower.dimensions_m.width if tower.dimensions_m else 4.0)
        or 4.0
    )
    if requirements.include_power_cabinet and (cabinet := assets_by_type.get("cabinet")):
        offset = max(3.0, float(base_width) * 1.2)
        placements.append(
            _accessory_placement(
                cabinet,
                asset_type="cabinet",
                position=[offset, 0.0, 0.8],
                rotation_deg=[0.0, 0.0, 0.0],
            )
        )
    if requirements.include_gps_antenna and (gps := assets_by_type.get("gps")):
        mount_radius = float(base_width) / 2 + 0.1
        placements.append(
            _accessory_placement(
                gps,
                asset_type="gps",
                position=[0.0, mount_radius, max(0.5, requirements.tower_height_m - 0.5)],
                rotation_deg=[0.0, 0.0, 0.0],
            )
        )
    return placements


def _accessory_placement(
    asset: AssetManifest,
    *,
    asset_type: str,
    position: list[float],
    rotation_deg: list[float],
) -> SceneAccessoryPlacement:
    return SceneAccessoryPlacement(
        asset_id=asset.asset_id,
        asset_file=asset.file,
        asset_source=asset.source,
        asset_metadata=_runtime_asset_metadata(asset),
        import_fallback_allowed=asset.import_fallback_allowed,
        asset_type=asset_type,  # type: ignore[arg-type]
        dimensions_m=asset.dimensions_m,
        position=position,
        rotation_deg=rotation_deg,
    )


def _planning_hints(context: dict) -> dict:
    payload = context.get("payload")
    if not isinstance(payload, dict):
        return {}
    hints = payload.get("planning_hints")
    return hints if isinstance(hints, dict) else {}


def _bounded_float_hint(
    hints: dict,
    key: str,
    current: float,
    minimum: float,
    maximum: float,
) -> float:
    value = hints.get(key)
    if not isinstance(value, (int, float)):
        return current
    value = float(value)
    if minimum <= value <= maximum:
        return value
    return current
