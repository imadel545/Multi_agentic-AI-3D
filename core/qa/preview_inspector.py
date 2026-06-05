import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from core.contracts.glb_inspection import PreviewInspectionReport
from core.contracts.scene import SceneSpec

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MIN_LUMINANCE_MEAN = 55.0
MIN_LUMINANCE_STDDEV = 6.5
MIN_NON_DARK_PIXEL_RATIO = 0.08


@dataclass(frozen=True)
class PreviewStats:
    luminance_mean: float | None
    luminance_stddev: float | None
    non_dark_pixel_ratio: float | None
    visual_quality_valid: bool
    warning: str | None = None


class PreviewInspector:
    def inspect(self, preview_path: Path, scene: SceneSpec) -> PreviewInspectionReport:
        file_exists = preview_path.exists()
        file_size_bytes = preview_path.stat().st_size if file_exists else 0
        if not file_exists:
            return _report(
                file_exists=False,
                file_size_bytes=0,
                width=0,
                height=0,
                image_format=None,
                minimum_resolution=_minimum_resolution(scene),
                stats=_unknown_stats(),
                critical_errors=["PREVIEW_FILE_MISSING"],
            )
        if file_size_bytes < 24:
            return _report(
                file_exists=True,
                file_size_bytes=file_size_bytes,
                width=0,
                height=0,
                image_format=None,
                minimum_resolution=_minimum_resolution(scene),
                stats=_unknown_stats(),
                critical_errors=["PREVIEW_FILE_TOO_SMALL"],
            )
        try:
            width, height, image_format, stats = _parse_preview(preview_path)
        except (OSError, ValueError, struct.error):
            return _report(
                file_exists=True,
                file_size_bytes=file_size_bytes,
                width=0,
                height=0,
                image_format=None,
                minimum_resolution=_minimum_resolution(scene),
                stats=_unknown_stats(),
                critical_errors=["PREVIEW_FORMAT_INVALID"],
            )
        return _report(
            file_exists=True,
            file_size_bytes=file_size_bytes,
            width=width,
            height=height,
            image_format=image_format,
            minimum_resolution=_minimum_resolution(scene),
            stats=stats,
            critical_errors=[],
        )


def _parse_preview(path: Path) -> tuple[int, int, str, PreviewStats]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("preview is not PNG")
    width, height = struct.unpack(">II", data[16:24])
    stats = _png_stats(data, width, height)
    return width, height, "png", stats


def _report(
    *,
    file_exists: bool,
    file_size_bytes: int,
    width: int,
    height: int,
    image_format: str | None,
    minimum_resolution: tuple[int, int],
    stats: PreviewStats,
    critical_errors: list[str],
) -> PreviewInspectionReport:
    min_width, min_height = minimum_resolution
    minimum_resolution_valid = width >= min_width and height >= min_height
    checks = {
        "file_exists": file_exists,
        "format_valid": image_format == "png",
        "minimum_resolution_valid": minimum_resolution_valid,
        "preview_visual_quality_valid": stats.visual_quality_valid,
    }
    errors = list(critical_errors)
    if not minimum_resolution_valid:
        errors.append("PREVIEW_MINIMUM_RESOLUTION_NOT_MET")
    if image_format == "png" and not stats.visual_quality_valid:
        errors.append("PREVIEW_VISUAL_QUALITY_INVALID")
    warnings = [stats.warning] if stats.warning else []
    return PreviewInspectionReport(
        inspection_mode="png_parse" if image_format == "png" else "not_available",
        file_exists=file_exists,
        file_size_bytes=file_size_bytes,
        width=width,
        height=height,
        format=image_format,
        minimum_resolution_valid=minimum_resolution_valid,
        luminance_mean=stats.luminance_mean,
        luminance_stddev=stats.luminance_stddev,
        non_dark_pixel_ratio=stats.non_dark_pixel_ratio,
        visual_quality_valid=stats.visual_quality_valid,
        checks=checks,
        warnings=warnings,
        critical_errors=errors,
        preview_qa_passed=not errors,
    )


def _minimum_resolution(scene: SceneSpec) -> tuple[int, int]:
    width, height = scene.preview.resolution
    return width, height


def _png_stats(data: bytes, width: int, height: int) -> PreviewStats:
    try:
        bit_depth, color_type, channels, bytes_per_pixel = _png_color_info(data)
        if bit_depth != 8 or color_type not in {0, 2, 6}:
            return _unknown_stats("PREVIEW_PIXEL_ANALYSIS_UNSUPPORTED_FORMAT")
        raw = zlib.decompress(_png_idat_payload(data))
        stride = width * channels
        previous = bytearray(stride)
        luminance_values = []
        offset = 0
        sample_step = max(1, (width * height) // 250_000)
        pixel_index = 0
        for _row in range(height):
            filter_type = raw[offset]
            offset += 1
            scanline = bytearray(raw[offset : offset + stride])
            offset += stride
            _unfilter_scanline(scanline, previous, filter_type, bytes_per_pixel)
            for index in range(0, stride, channels):
                if pixel_index % sample_step == 0:
                    if channels == 1:
                        r = g = b = scanline[index]
                    else:
                        r, g, b = scanline[index], scanline[index + 1], scanline[index + 2]
                    luminance_values.append((0.2126 * r) + (0.7152 * g) + (0.0722 * b))
                pixel_index += 1
            previous = scanline
        if not luminance_values:
            return _unknown_stats("PREVIEW_PIXEL_ANALYSIS_EMPTY")
        mean = sum(luminance_values) / len(luminance_values)
        variance = sum((value - mean) ** 2 for value in luminance_values) / len(luminance_values)
        stddev = math.sqrt(variance)
        non_dark_ratio = sum(1 for value in luminance_values if value >= 45) / len(luminance_values)
        visual_quality_valid = (
            mean >= MIN_LUMINANCE_MEAN
            and stddev >= MIN_LUMINANCE_STDDEV
            and non_dark_ratio >= MIN_NON_DARK_PIXEL_RATIO
        )
        return PreviewStats(
            luminance_mean=round(mean, 3),
            luminance_stddev=round(stddev, 3),
            non_dark_pixel_ratio=round(non_dark_ratio, 4),
            visual_quality_valid=visual_quality_valid,
        )
    except (IndexError, KeyError, ValueError, zlib.error, struct.error):
        return _unknown_stats("PREVIEW_PIXEL_ANALYSIS_FAILED")


def _png_color_info(data: bytes) -> tuple[int, int, int, int]:
    bit_depth = data[24]
    color_type = data[25]
    channels_by_color_type = {0: 1, 2: 3, 6: 4}
    channels = channels_by_color_type[color_type]
    return bit_depth, color_type, channels, channels


def _png_idat_payload(data: bytes) -> bytes:
    offset = len(PNG_SIGNATURE)
    payload = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        if chunk_type == b"IDAT":
            payload.extend(chunk_data)
        if chunk_type == b"IEND":
            break
        offset += 12 + length
    if not payload:
        raise ValueError("PNG has no IDAT payload")
    return bytes(payload)


def _unfilter_scanline(
    scanline: bytearray,
    previous: bytearray,
    filter_type: int,
    bytes_per_pixel: int,
) -> None:
    for index, value in enumerate(scanline):
        left = scanline[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
        up = previous[index]
        upper_left = previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
        if filter_type == 0:
            recon = value
        elif filter_type == 1:
            recon = value + left
        elif filter_type == 2:
            recon = value + up
        elif filter_type == 3:
            recon = value + ((left + up) // 2)
        elif filter_type == 4:
            recon = value + _paeth_predictor(left, up, upper_left)
        else:
            raise ValueError(f"unsupported PNG filter type: {filter_type}")
        scanline[index] = recon & 0xFF


def _paeth_predictor(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left


def _unknown_stats(warning: str | None = None) -> PreviewStats:
    return PreviewStats(
        luminance_mean=None,
        luminance_stddev=None,
        non_dark_pixel_ratio=None,
        visual_quality_valid=False,
        warning=warning,
    )
