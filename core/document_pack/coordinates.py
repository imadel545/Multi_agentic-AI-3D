import importlib.util
from dataclasses import dataclass

from core.contracts.document_pack import ExtractedField, SourceEvidence


@dataclass(frozen=True)
class CoordinateCandidate:
    field: str
    value: str | float | bool
    confidence: float
    source: SourceEvidence


def coordinate_conversion_candidates(
    resolved: dict[str, ExtractedField],
) -> list[CoordinateCandidate]:
    system = resolved.get("coordinates.coordinate_system")
    latitude = resolved.get("coordinates.latitude")
    longitude = resolved.get("coordinates.longitude")
    x_field = resolved.get("coordinates.x")
    y_field = resolved.get("coordinates.y")
    if _confirmed_number(latitude) is not None and _confirmed_number(longitude) is not None:
        return [
            CoordinateCandidate(
                "coordinates.conversion_available",
                True,
                0.95,
                _source_for(latitude, "WGS84 coordinates were supplied directly."),
            ),
            CoordinateCandidate(
                "coordinates.conversion_status",
                "not_required_wgs84",
                0.95,
                _source_for(latitude, "WGS84 coordinates were supplied directly."),
            ),
        ]
    if not system or system.status != "confirmed":
        return []
    x = _confirmed_number(x_field)
    y = _confirmed_number(y_field)
    if x is None or y is None:
        return [
            CoordinateCandidate(
                "coordinates.conversion_available",
                False,
                0.9,
                _source_for(system, "Coordinate CRS found but X/Y values are incomplete."),
            ),
            CoordinateCandidate(
                "coordinates.conversion_status",
                "missing_xy",
                0.9,
                _source_for(system, "Coordinate CRS found but X/Y values are incomplete."),
            ),
        ]
    epsg = _epsg_for(str(system.value))
    if epsg is None:
        return [
            CoordinateCandidate(
                "coordinates.conversion_available",
                False,
                0.88,
                _source_for(system, f"Unsupported coordinate system: {system.value}."),
            ),
            CoordinateCandidate(
                "coordinates.conversion_status",
                "unsupported_crs",
                0.88,
                _source_for(system, f"Unsupported coordinate system: {system.value}."),
            ),
        ]
    if importlib.util.find_spec("pyproj") is None:
        return [
            CoordinateCandidate(
                "coordinates.conversion_available",
                False,
                0.95,
                _source_for(system, "pyproj is not installed; conversion was not applied."),
            ),
            CoordinateCandidate(
                "coordinates.conversion_status",
                "unavailable_pyproj",
                0.95,
                _source_for(system, "pyproj is not installed; conversion was not applied."),
            ),
        ]
    try:
        from pyproj import Transformer  # type: ignore[import-not-found]

        transformer = Transformer.from_crs(epsg, 4326, always_xy=True)
        lon, lat = transformer.transform(x, y)
    except Exception as exc:
        return [
            CoordinateCandidate(
                "coordinates.conversion_available",
                False,
                0.72,
                _source_for(system, f"pyproj conversion failed: {type(exc).__name__}."),
            ),
            CoordinateCandidate(
                "coordinates.conversion_status",
                "conversion_failed",
                0.72,
                _source_for(system, f"pyproj conversion failed: {type(exc).__name__}."),
            ),
        ]
    return [
        CoordinateCandidate(
            "coordinates.latitude",
            round(float(lat), 7),
            0.76,
            _source_for(system, f"Converted EPSG:{epsg} X/Y to WGS84 latitude."),
        ),
        CoordinateCandidate(
            "coordinates.longitude",
            round(float(lon), 7),
            0.76,
            _source_for(system, f"Converted EPSG:{epsg} X/Y to WGS84 longitude."),
        ),
        CoordinateCandidate(
            "coordinates.conversion_available",
            True,
            0.82,
            _source_for(system, f"Converted coordinates using pyproj EPSG:{epsg} to WGS84."),
        ),
        CoordinateCandidate(
            "coordinates.conversion_status",
            f"converted_epsg_{epsg}_to_wgs84",
            0.82,
            _source_for(system, f"Converted coordinates using pyproj EPSG:{epsg} to WGS84."),
        ),
    ]


def _confirmed_number(field: ExtractedField | None) -> float | None:
    if field and field.status == "confirmed" and isinstance(field.value, float | int):
        return float(field.value)
    return None


def _epsg_for(system: str) -> int | None:
    normalized = system.lower().replace("_", " ")
    if "wgs" in normalized:
        return 4326
    if "lambert 93" in normalized or "l93" in normalized:
        return 2154
    if "lambert ii" in normalized or "lambert 2" in normalized:
        return 27572
    return None


def _source_for(field: ExtractedField | None, evidence: str) -> SourceEvidence:
    if field and field.sources:
        source = field.sources[0]
        return SourceEvidence(
            document_id=source.document_id,
            file=source.file,
            source_type="coordinate_conversion",
            page=source.page,
            sheet=source.sheet,
            layer=source.layer,
            evidence=evidence,
        )
    return SourceEvidence(
        document_id="coordinate_adapter",
        file="coordinate_adapter",
        source_type="coordinate_conversion",
        evidence=evidence,
    )
