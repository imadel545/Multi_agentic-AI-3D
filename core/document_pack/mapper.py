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
            )

        tower_type = _required_str(spec, "tower_spec", "tower_type")
        tower_height = _required_float(spec, "tower_spec", "tower_height_m")
        azimuths = _required_float_list(spec, "radio_sectors", "azimuth_deg")
        hba_values = _required_float_list(spec, "radio_sectors", "hba_m")
        install_height = min(hba_values) if hba_values else tower_height
        network_type = _network_type(spec)
        include_rru = _confirmed_bool(spec.cabling_spec.get("include_rru"))
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
