from core.contracts.assets import (
    AssetManifest,
    PanelAntennaGeometryProfile,
    RadioGeometryProfile,
)
from core.contracts.common import DetailLevel
from core.contracts.requirements import RequirementSpec
from core.contracts.scene import (
    RuntimeAssetMetadata,
    SceneAccessoryPlacement,
    SceneAssetPlacement,
    SceneSpec,
    SectorSpec,
    VisualElements,
)
from core.contracts.tower import TowerCharacteristics
from core.rag.planning import RagPlanningResolution, resolve_planning_hints


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
        planning_resolution: RagPlanningResolution | dict | None = None,
    ) -> SceneSpec:
        del memory_recall
        if planning_resolution is None:
            rag_resolution = resolve_planning_hints(requirements, rag_context)
        elif isinstance(planning_resolution, RagPlanningResolution):
            rag_resolution = planning_resolution
        else:
            rag_resolution = RagPlanningResolution(
                antenna_install_height_m=float(planning_resolution["antenna_install_height_m"]),
                beamwidth_deg=float(planning_resolution["beamwidth_deg"]),
                mechanical_tilt_deg=float(
                    planning_resolution.get(
                        "mechanical_tilt_deg", requirements.mechanical_tilt_deg
                    )
                ),
                electrical_tilt_deg=float(
                    planning_resolution.get(
                        "electrical_tilt_deg", requirements.electrical_tilt_deg
                    )
                ),
                include_cables=bool(planning_resolution["include_cables"]),
                include_sector_beams=bool(planning_resolution["include_sector_beams"]),
                decisions=tuple(planning_resolution.get("decisions", ())),
            )
        visual_elements = VisualElements(
            include_sector_beams=rag_resolution.include_sector_beams,
            include_azimuth_arrows=True,
            include_height_markers=True,
            include_labels=requirements.include_labels,
            include_power_cabinet=requirements.include_power_cabinet,
            include_gps_antenna=requirements.include_gps_antenna,
        )
        beamwidth = rag_resolution.beamwidth_deg
        install_height = rag_resolution.antenna_install_height_m
        mechanical_tilt = rag_resolution.mechanical_tilt_deg
        electrical_tilt = rag_resolution.electrical_tilt_deg
        include_cables = rag_resolution.include_cables
        tower_characteristics = _resolved_tower_characteristics(requirements, tower)
        antenna_geometry_profile = _panel_profile_for_detail(
            antenna.panel_geometry_profile,
            requirements.detail_level,
        )
        radio_geometry_profile = _radio_profile_for_detail(
            radio.radio_geometry_profile if radio else None,
            requirements.detail_level,
        )

        sectors = [
            SectorSpec(
                sector_id=f"S{index + 1}",
                antenna_asset_id=antenna.asset_id,
                antenna_asset_file=antenna.file,
                antenna_asset_source=antenna.source,
                antenna_asset_metadata=_runtime_asset_metadata(antenna),
                antenna_import_fallback_allowed=antenna.import_fallback_allowed,
                antenna_generation_strategy=_component_generation_strategy(antenna),
                antenna_geometry_source=_component_geometry_source(antenna),
                antenna_generation_reason=_component_generation_reason(antenna),
                radio_asset_id=radio.asset_id if radio else None,
                radio_asset_file=radio.file if radio else None,
                radio_asset_source=radio.source if radio else None,
                radio_asset_metadata=_runtime_asset_metadata(radio)
                if radio
                else RuntimeAssetMetadata(),
                radio_import_fallback_allowed=radio.import_fallback_allowed if radio else True,
                radio_generation_strategy=_component_generation_strategy(radio)
                if radio
                else "procedural_fallback",
                radio_geometry_source=_component_geometry_source(radio) if radio else "degraded",
                radio_generation_reason=_component_generation_reason(radio)
                if radio
                else "no radio requested",
                install_height_m=install_height,
                azimuth_deg=azimuth,
                mechanical_tilt_deg=mechanical_tilt,
                electrical_tilt_deg=electrical_tilt,
                beamwidth_deg=beamwidth,
                antenna_dimensions_m=antenna.dimensions_m,
                radio_dimensions_m=radio.dimensions_m if radio else None,
                antenna_geometry_profile=antenna_geometry_profile,
                radio_geometry_profile=radio_geometry_profile,
                include_cable=include_cables,
                include_label=requirements.include_labels,
            )
            for index, azimuth in enumerate(requirements.azimuths_deg)
        ]
        return SceneSpec(
            scene_id=workflow_id,
            network_type=requirements.network_type,
            detail_level=requirements.detail_level,
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
                generation_strategy="parametric_generated",
                geometry_source="parametric_generated",
                generation_reason=(
                    "qualified SceneSpec-driven parametric tower profile"
                    if tower.allows_generation_mode("parametric_generated")
                    else "tower import is not authorized; using controlled parametric generation"
                ),
                height_m=requirements.tower_height_m,
                characteristics=tower_characteristics,
            ),
            sectors=sectors,
            visual_elements=visual_elements,
            accessory_assets=_accessory_placements(
                requirements=requirements,
                tower=tower,
                assets=accessory_assets or [],
            ),
        )


def _panel_profile_for_detail(
    profile: PanelAntennaGeometryProfile | None,
    detail_level: DetailLevel,
) -> PanelAntennaGeometryProfile | None:
    if profile is None or detail_level == "high":
        return profile
    payload = profile.model_dump()
    payload.update(
        {
            "rear_mount_rail_count": _detail_count(
                profile.rear_mount_rail_count,
                minimum=2,
                detail_level=detail_level,
            ),
            "bottom_port_count": _detail_count(
                profile.bottom_port_count,
                minimum=2,
                detail_level=detail_level,
            ),
        }
    )
    return PanelAntennaGeometryProfile.model_validate(payload)


def _radio_profile_for_detail(
    profile: RadioGeometryProfile | None,
    detail_level: DetailLevel,
) -> RadioGeometryProfile | None:
    if profile is None or detail_level == "high":
        return profile
    payload = profile.model_dump()
    payload.update(
        {
            "heat_sink_fin_count": _detail_count(
                profile.heat_sink_fin_count,
                minimum=4,
                detail_level=detail_level,
            ),
            "bottom_connector_count": _detail_count(
                profile.bottom_connector_count,
                minimum=2,
                detail_level=detail_level,
            ),
            "mounting_rail_count": _detail_count(
                profile.mounting_rail_count,
                minimum=2,
                detail_level=detail_level,
            ),
        }
    )
    return RadioGeometryProfile.model_validate(payload)


def _detail_count(value: int, *, minimum: int, detail_level: DetailLevel) -> int:
    """Reduce visual repetition without changing dimensions or installation semantics."""

    if detail_level == "high":
        return value
    if detail_level == "medium":
        reduced = (value * 3 + 3) // 4
    else:
        reduced = (value + 1) // 2
    return max(minimum, min(value, reduced))


def _runtime_asset_metadata(asset: AssetManifest) -> RuntimeAssetMetadata:
    return RuntimeAssetMetadata(
        geometry_fidelity=asset.geometry_fidelity,
        license=asset.license,
        attribution_required=asset.attribution_required,
        attribution=asset.attribution,
        original_url=asset.original_url,
        original_author=asset.original_author,
        normalized_by=asset.normalized_by,
        pivot_policy=asset.pivot_policy,
        front_axis=asset.front_axis,
        qualification_status=asset.qualification.status,
        allowed_generation_modes=list(asset.qualification.allowed_generation_modes),
        verified_file_sha256=asset.qualification.verified_file_sha256,
        qualification_method=asset.qualification.qualification_method,
        qualification_limitations=list(asset.qualification.limitations),
    )


def _accessory_placements(
    *,
    requirements: RequirementSpec,
    tower: AssetManifest,
    assets: list[AssetManifest],
) -> list[SceneAccessoryPlacement]:
    placements: list[SceneAccessoryPlacement] = []
    assets_by_type = {asset.type: asset for asset in assets}
    characteristics = _resolved_tower_characteristics(requirements, tower)
    base_width = float(characteristics.base_width_m or 4.0)
    if requirements.include_power_cabinet and (cabinet := assets_by_type.get("cabinet")):
        offset = max(3.0, float(base_width) * 1.2)
        placements.append(
            _accessory_placement(
                cabinet,
                asset_type="cabinet",
                # Accessory positions use a base datum. The Blender importer
                # aligns base_center_ground assets to this Z coordinate.
                position=[offset, 0.0, 0.0],
                rotation_deg=[0.0, 0.0, 0.0],
            )
        )
    if requirements.include_gps_antenna and (gps := assets_by_type.get("gps")):
        gps_height = max(0.5, requirements.tower_height_m - 0.5)
        mount_radius = (
            _tower_width_at_height(
                height_m=gps_height,
                tower_height_m=requirements.tower_height_m,
                base_width_m=base_width,
                top_width_m=float(characteristics.top_width_m or base_width),
            )
            / 2
            + 0.1
        )
        placements.append(
            _accessory_placement(
                gps,
                asset_type="gps",
                position=[0.0, mount_radius, gps_height],
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
        generation_strategy=_component_generation_strategy(asset),
        geometry_source=_component_geometry_source(asset),
        generation_reason=_component_generation_reason(asset),
    )


def _component_generation_strategy(asset: AssetManifest):
    if asset.allows_generation_mode("imported_glb_exact"):
        return "imported_glb_exact"
    if asset.allows_generation_mode("parametric_generated"):
        return "internal_project_generated"
    return "procedural_fallback"


def _component_geometry_source(asset: AssetManifest):
    strategy = _component_generation_strategy(asset)
    if strategy == "imported_glb_exact":
        return "imported_glb_exact"
    if strategy == "internal_project_generated":
        return "internal_project_generated"
    return "degraded"


def _component_generation_reason(asset: AssetManifest) -> str:
    if asset.allows_generation_mode("imported_glb_exact"):
        return "qualified exact GLB import authorized by pinned asset manifest"
    if asset.allows_generation_mode("parametric_generated"):
        return "qualified SceneSpec-driven parametric component profile"
    return "asset is not qualified for generation; controlled procedural fallback required"


def _resolved_tower_characteristics(
    requirements: RequirementSpec,
    tower: AssetManifest,
) -> TowerCharacteristics:
    """Resolve optional tower widths once so SceneSpec is generation-ready."""

    characteristics = requirements.tower_characteristics
    manifest_width = tower.dimensions_m.width if tower.dimensions_m else None
    default_base = {
        "lattice": 4.0,
        "monopole": 0.8,
        "rooftop_mast": 0.35,
        "small_cell_pole": 0.3,
    }[characteristics.structure]
    base_width = float(characteristics.base_width_m or manifest_width or default_base)
    default_top_ratio = {
        "lattice": 0.25,
        "monopole": 0.35,
        "rooftop_mast": 0.4,
        "small_cell_pole": 0.6,
    }[characteristics.structure]
    top_width = float(characteristics.top_width_m or (base_width * default_top_ratio))
    return characteristics.model_copy(
        update={
            "base_width_m": base_width,
            "top_width_m": min(top_width, base_width),
        }
    )


def _tower_width_at_height(
    *,
    height_m: float,
    tower_height_m: float,
    base_width_m: float,
    top_width_m: float,
) -> float:
    ratio = min(max(float(height_m) / max(float(tower_height_m), 1e-6), 0.0), 1.0)
    return float(base_width_m) + (float(top_width_m) - float(base_width_m)) * ratio
