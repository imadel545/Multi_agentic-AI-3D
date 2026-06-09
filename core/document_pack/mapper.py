from core.contracts.common import WarningItem
from core.contracts.document_pack import ProjectDesignSpec, RequirementMappingResult
from core.contracts.requirements import RequirementSpec
from core.contracts.tower import TowerCharacteristics


class ProjectDesignSpecMapper:
    def map_to_requirements(
        self, spec: ProjectDesignSpec, detail_level: str = "high"
    ) -> RequirementMappingResult:
        blocking = [field.field for field in spec.missing_fields if field.severity == "blocking"]
        conflicts = [field.field for field in spec.conflicts]
        if blocking or conflicts:
            return RequirementMappingResult(
                status="blocked",
                blocking_fields=blocking,
                conflicts=conflicts,
                mapping_loss_report=_mapping_loss_report(spec, None),
            )

        tower_type = _required_str(spec, "tower_spec", "tower_type")
        tower_height = _required_float(spec, "tower_spec", "tower_height_m")
        azimuths = _required_float_list(spec, "radio_sectors", "azimuth_deg")
        hba_values = _required_float_list(spec, "radio_sectors", "hba_m")
        install_height = min(hba_values) if hba_values else tower_height
        network_type = _network_type(spec)
        include_rru = _confirmed_bool(_first_sector_field(spec, "rru")) or _confirmed_bool(
            spec.cabling_spec.get("include_rru")
        )
        include_cables = _confirmed_bool(spec.cabling_spec.get("include_cables"))
        include_gps_antenna = _confirmed_bool(spec.compound_spec.get("gps"))
        include_power_cabinet = _confirmed_bool(spec.compound_spec.get("power_cabinet"))
        mechanical_tilt = _uniform_confirmed_sector_float(spec, "mechanical_tilt_deg")
        characteristics = _tower_characteristics(spec, tower_type)
        warnings = _mapping_warnings(
            spec,
            include_gps_antenna=include_gps_antenna,
            include_power_cabinet=include_power_cabinet,
            mechanical_tilt_confirmed=mechanical_tilt is not None,
        )
        requirements = RequirementSpec(
            network_type=network_type,
            site_type="telecom_site",
            tower_type=tower_type,
            tower_height_m=tower_height,
            tower_characteristics=characteristics,
            sector_count=len(azimuths),
            antenna_type="microwave_dish" if network_type == "MW" else "panel_5g",
            antenna_install_height_m=install_height,
            azimuths_deg=azimuths,
            mechanical_tilt_deg=mechanical_tilt if mechanical_tilt is not None else 3.0,
            include_rru=include_rru if network_type != "MW" else False,
            include_cables=include_cables,
            include_beams=True,
            include_labels=True,
            include_gps_antenna=include_gps_antenna,
            include_power_cabinet=include_power_cabinet,
            detail_level=detail_level,  # type: ignore[arg-type]
            warnings=warnings,
        )
        return RequirementMappingResult(
            status="mapped",
            requirements=requirements.model_dump(),
            generated_requirements_text=_requirements_text(requirements, spec.pack_id),
            network_type=network_type,
            mapping_loss_report=_mapping_loss_report(spec, requirements),
        )


def _required_str(spec: ProjectDesignSpec, section: str, field: str) -> str:
    value = getattr(spec, section)[field].value
    if not isinstance(value, str):
        raise ValueError(f"{section}.{field} must be a string")
    return value


def _required_float(spec: ProjectDesignSpec, section: str, field: str) -> float:
    value = getattr(spec, section)[field].value
    if not isinstance(value, float | int):
        raise ValueError(f"{section}.{field} must be numeric")
    return float(value)


def _required_float_list(spec: ProjectDesignSpec, source: str, field: str) -> list[float]:
    if source == "radio_sectors":
        values = [getattr(sector, field).value for sector in spec.radio_sectors]
        if all(isinstance(value, float | int) for value in values):
            return [float(value) for value in values]
    raise ValueError(f"{source}.{field} must be numeric")


def _confirmed_bool(field) -> bool:
    return bool(field and field.status == "confirmed" and field.value is True)


def _confirmed_field(spec: ProjectDesignSpec, section: str, field: str):
    candidate = getattr(spec, section).get(field)
    return candidate if candidate and candidate.status == "confirmed" else None


def _first_sector_field(spec: ProjectDesignSpec, field: str):
    if not spec.radio_sectors:
        return None
    return getattr(spec.radio_sectors[0], field)


def _mapping_warnings(
    spec: ProjectDesignSpec,
    *,
    include_gps_antenna: bool,
    include_power_cabinet: bool,
    mechanical_tilt_confirmed: bool,
) -> list[WarningItem]:
    warnings: list[WarningItem] = []
    if include_gps_antenna:
        warnings.append(
            WarningItem(
                code="DOC_ACCESSORY_GPS_ENABLED_FROM_EVIDENCE",
                message="GPS antenna enabled from confirmed document-pack evidence.",
            )
        )
    if include_power_cabinet:
        warnings.append(
            WarningItem(
                code="DOC_ACCESSORY_POWER_CABINET_ENABLED_FROM_EVIDENCE",
                message="Power cabinet enabled from confirmed document-pack evidence.",
            )
        )
    if _confirmed_field(spec, "site_info", "site_name"):
        warnings.append(
            WarningItem(
                code="DOC_FIELD_NOT_MODELED_SITE_NAME",
                message="Site name is extracted but not yet represented in SceneSpec.",
            )
        )
    if _confirmed_field(spec, "coordinate_info", "latitude") or _confirmed_field(
        spec, "coordinate_info", "longitude"
    ):
        warnings.append(
            WarningItem(
                code="DOC_FIELD_NOT_MODELED_COORDINATES",
                message="Coordinates are extracted but not yet represented in SceneSpec.",
            )
        )
    if spec.grounding_spec:
        warnings.append(
            WarningItem(
                code="DOC_FIELD_NOT_MODELED_GROUNDING",
                message=(
                    "Grounding/adduction evidence is extracted but not yet represented "
                    "in SceneSpec."
                ),
            )
        )
    if _confirmed_field(spec, "tower_spec", "color_ral"):
        warnings.append(
            WarningItem(
                code="DOC_FIELD_NOT_MODELED_COLOR_RAL",
                message=(
                    "Tower color/RAL evidence is extracted but not yet represented "
                    "in SceneSpec materials."
                ),
            )
        )
    if not mechanical_tilt_confirmed:
        warnings.append(
            WarningItem(
                code="DOC_DEFAULT_MECHANICAL_TILT_USED",
                message=(
                    "Mechanical tilt was not confirmed in the document pack; "
                    "default 3 degrees is used."
                ),
            )
        )
    return warnings


def _uniform_confirmed_sector_float(spec: ProjectDesignSpec, field: str) -> float | None:
    values = []
    for sector in spec.radio_sectors:
        candidate = getattr(sector, field)
        if not candidate or candidate.status != "confirmed":
            return None
        if not isinstance(candidate.value, float | int):
            return None
        values.append(float(candidate.value))
    if not values:
        return None
    first = values[0]
    if all(abs(value - first) < 0.05 for value in values):
        return first
    return None


def _mapping_loss_report(
    spec: ProjectDesignSpec,
    requirements: RequirementSpec | None,
) -> dict:
    entries = [
        _mapping_entry(
            spec,
            "tower.tower_type",
            requirement_field="tower_type",
            scene_field="tower.asset_id",
            mapped=requirements is not None,
        ),
        _mapping_entry(
            spec,
            "tower.tower_height_m",
            requirement_field="tower_height_m",
            scene_field="tower.height_m",
            mapped=requirements is not None,
        ),
        _mapping_entry(
            spec,
            "radio.azimuths_deg",
            requirement_field="azimuths_deg",
            scene_field="sectors[].azimuth_deg",
            mapped=requirements is not None,
        ),
        _mapping_entry(
            spec,
            "radio.hba_m",
            requirement_field="antenna_install_height_m",
            scene_field="sectors[].install_height_m",
            mapped=requirements is not None,
        ),
        _mapping_entry(
            spec,
            "radio.mechanical_tilt_deg",
            requirement_field="mechanical_tilt_deg",
            scene_field="sectors[].mechanical_tilt_deg",
            mapped=requirements is not None
            and requirements.mechanical_tilt_deg != 3.0
            and _confirmed_any(spec, "radio_sectors", "mechanical_tilt_deg"),
            fallback=requirements is not None and requirements.mechanical_tilt_deg == 3.0,
        ),
        _mapping_entry(
            spec,
            "radio.include_rru",
            requirement_field="include_rru",
            scene_field="sectors[].radio_asset_id",
            mapped=requirements is not None,
        ),
        _mapping_entry(
            spec,
            "cabling.include_cables",
            requirement_field="include_cables",
            scene_field="sectors[].include_cable",
            mapped=requirements is not None,
        ),
        _mapping_entry(
            spec,
            "compound.gps",
            requirement_field="include_gps_antenna",
            scene_field="visual_elements.include_gps_antenna/accessory_assets[gps]",
            mapped=requirements is not None and requirements.include_gps_antenna,
        ),
        _mapping_entry(
            spec,
            "compound.power_cabinet",
            requirement_field="include_power_cabinet",
            scene_field="visual_elements.include_power_cabinet/accessory_assets[cabinet]",
            mapped=requirements is not None and requirements.include_power_cabinet,
        ),
        _mapping_entry(
            spec,
            "site.site_name",
            requirement_field=None,
            scene_field=None,
            not_modeled=True,
        ),
        _mapping_entry(
            spec,
            "coordinates.latitude",
            requirement_field=None,
            scene_field=None,
            not_modeled=True,
        ),
        _mapping_entry(
            spec,
            "coordinates.longitude",
            requirement_field=None,
            scene_field=None,
            not_modeled=True,
        ),
        _mapping_entry(
            spec,
            "grounding.grounding",
            requirement_field=None,
            scene_field=None,
            not_modeled=True,
        ),
        _mapping_entry(
            spec,
            "tower.color_ral",
            requirement_field=None,
            scene_field=None,
            not_modeled=True,
        ),
    ]
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return {"pack_id": spec.pack_id, "counts": counts, "fields": entries}


def _mapping_entry(
    spec: ProjectDesignSpec,
    project_field: str,
    *,
    requirement_field: str | None,
    scene_field: str | None,
    mapped: bool = False,
    not_modeled: bool = False,
    fallback: bool = False,
) -> dict:
    field = _find_project_field(spec, project_field)
    if _is_conflict(spec, project_field):
        status = "conflict"
    elif field is None or field.status == "missing":
        status = "missing"
    elif not_modeled and field.status == "confirmed":
        status = "not_modeled"
    elif mapped and field.status == "confirmed":
        status = "mapped"
    elif fallback:
        status = "fallback"
    elif field.status == "confirmed":
        status = "lost_field"
    else:
        status = field.status
    return {
        "project_field": project_field,
        "project_status": field.status if field else "missing",
        "requirement_field": requirement_field,
        "scene_field": scene_field,
        "status": status,
        "evidence_count": len(field.sources) if field else 0,
        "reason": _mapping_reason(status),
    }


def _mapping_reason(status: str) -> str:
    return {
        "mapped": "Field is preserved into RequirementSpec and expected SceneSpec fields.",
        "not_modeled": (
            "Field is extracted with evidence but no SceneSpec contract field exists yet."
        ),
        "missing": "No confirmed project field is available.",
        "conflict": "Conflicting document values require user correction before mapping.",
        "fallback": "No confirmed field is available; controlled deterministic default is used.",
        "lost_field": "Confirmed field exists but is not preserved by the current mapper.",
    }.get(status, "Field is visible for frontend review.")


def _find_project_field(spec: ProjectDesignSpec, project_field: str):
    if project_field == "radio.azimuths_deg" and spec.radio_sectors:
        return spec.radio_sectors[0].azimuth_deg
    if project_field == "radio.hba_m" and spec.radio_sectors:
        return spec.radio_sectors[0].hba_m
    if project_field == "radio.mechanical_tilt_deg" and spec.radio_sectors:
        return spec.radio_sectors[0].mechanical_tilt_deg
    if project_field == "radio.include_rru" and spec.radio_sectors:
        return spec.radio_sectors[0].rru
    sections = {
        "tower": spec.tower_spec,
        "cabling": spec.cabling_spec,
        "compound": spec.compound_spec,
        "site": spec.site_info,
        "coordinates": spec.coordinate_info,
        "grounding": spec.grounding_spec,
    }
    prefix, _, key = project_field.partition(".")
    return sections.get(prefix, {}).get(key)


def _is_conflict(spec: ProjectDesignSpec, project_field: str) -> bool:
    aliases = {
        "radio.azimuths_deg": {"radio.azimuths_deg"},
        "radio.hba_m": {"radio.hba_m"},
    }
    candidates = aliases.get(project_field, {project_field})
    return any(conflict.field in candidates for conflict in spec.conflicts)


def _confirmed_any(spec: ProjectDesignSpec, section: str, field: str) -> bool:
    if section == "radio_sectors":
        return any(
            (candidate := getattr(sector, field)) is not None and candidate.status == "confirmed"
            for sector in spec.radio_sectors
        )
    return False


def _network_type(spec: ProjectDesignSpec) -> str:
    bands = None
    if spec.radio_sectors and spec.radio_sectors[0].bands:
        bands = spec.radio_sectors[0].bands.value
    if isinstance(bands, list):
        joined = " ".join(str(band).upper() for band in bands)
        if "NR" in joined or "5G" in joined:
            return "5G"
        if "MW" in joined:
            return "MW"
        if "4G" in joined or "L800" in joined or "L1800" in joined:
            return "4G"
    return "5G"


def _tower_characteristics(spec: ProjectDesignSpec, tower_type: str) -> TowerCharacteristics:
    return TowerCharacteristics(
        structure={
            "lattice_tower": "lattice",
            "monopole": "monopole",
            "rooftop_mast": "rooftop_mast",
            "small_cell_pole": "small_cell_pole",
        }.get(tower_type, "lattice"),
        leg_count=4 if tower_type == "lattice_tower" else 1,
        base_width_m=4.0 if tower_type == "lattice_tower" else 1.2,
        top_width_m=1.0 if tower_type == "lattice_tower" else 0.6,
        foundation_type=_foundation_type(spec),
        has_lightning_rod=_confirmed_bool(spec.tower_spec.get("has_lightning_rod")),
        has_aviation_light=_confirmed_bool(spec.tower_spec.get("has_aviation_light")),
        has_ladder=_confirmed_bool(spec.tower_spec.get("has_ladder")),
        material="galvanized_steel",
    )


def _requirements_text(requirements: RequirementSpec, pack_id: str) -> str:
    azimuths = ", ".join(str(round(value, 2)) for value in requirements.azimuths_deg)
    return (
        f"Pack {pack_id}: créer un site {requirements.network_type} sur "
        f"{requirements.tower_type} {requirements.tower_height_m}m avec "
        f"{requirements.sector_count} secteurs à {requirements.antenna_install_height_m}m. "
        f"Azimuts : {azimuths}. "
        f"RRU={'oui' if requirements.include_rru else 'non'}, "
        f"câbles={'oui' if requirements.include_cables else 'non'}."
    )


def _foundation_type(spec: ProjectDesignSpec) -> str:
    field = spec.foundation_spec.get("foundation_type")
    if not field or not isinstance(field.value, str):
        return "concrete_pad"
    value = field.value.lower()
    if any(token in value for token in ["massif", "béton", "beton", "pad"]):
        return "concrete_pad"
    if "rooftop" in value or "toiture" in value:
        return "rooftop_anchored"
    if "pole" in value or "poteau" in value:
        return "pole_base"
    return "unknown"
