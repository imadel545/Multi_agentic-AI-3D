import math
import statistics
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from core.contracts.glb_inspection import PreviewInspectionReport
from core.contracts.scene import SceneSpec

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MIN_LUMINANCE_MEAN = 10.0
MIN_LUMINANCE_STDDEV = 3.0
MIN_NON_DARK_PIXEL_RATIO = 0.01
MIN_SUBJECT_PIXEL_RATIO = 0.004
MIN_SUBJECT_BBOX_HEIGHT_RATIO = 0.55
MAX_SUBJECT_BBOX_HEIGHT_RATIO = 0.92
MIN_SUBJECT_CONTRAST_MEAN = 45.0
MIN_SUBJECT_EDGE_MARGIN_RATIO = 0.025
MIN_SUBJECT_CENTER_X_RATIO = 0.25
MAX_SUBJECT_CENTER_X_RATIO = 0.75
FOREGROUND_COLOR_DISTANCE = 48


@dataclass(frozen=True)
class PreviewStats:
    luminance_mean: float | None
    luminance_stddev: float | None
    non_dark_pixel_ratio: float | None
    subject_pixel_ratio: float | None
    subject_bbox_width_ratio: float | None
    subject_bbox_height_ratio: float | None
    subject_contrast_mean: float | None
    subject_center_x_ratio: float | None
    subject_min_edge_margin_ratio: float | None
    subject_touches_frame: bool
    subject_framing_valid: bool
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
            width, height, image_format, stats = _parse_preview(preview_path, scene)
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


def _parse_preview(path: Path, scene: SceneSpec) -> tuple[int, int, str, PreviewStats]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("preview is not PNG")
    width, height = struct.unpack(">II", data[16:24])
    stats = _png_stats(data, width, height, scene)
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
        "preview_subject_present": (stats.subject_pixel_ratio or 0) >= MIN_SUBJECT_PIXEL_RATIO,
        "preview_subject_not_clipped": not stats.subject_touches_frame,
        "preview_subject_centered": stats.subject_center_x_ratio is not None
        and MIN_SUBJECT_CENTER_X_RATIO
        <= stats.subject_center_x_ratio
        <= MAX_SUBJECT_CENTER_X_RATIO,
        "preview_subject_framing_valid": stats.subject_framing_valid,
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
        subject_pixel_ratio=stats.subject_pixel_ratio,
        subject_bbox_width_ratio=stats.subject_bbox_width_ratio,
        subject_bbox_height_ratio=stats.subject_bbox_height_ratio,
        subject_contrast_mean=stats.subject_contrast_mean,
        subject_center_x_ratio=stats.subject_center_x_ratio,
        subject_min_edge_margin_ratio=stats.subject_min_edge_margin_ratio,
        subject_touches_frame=stats.subject_touches_frame,
        subject_framing_valid=stats.subject_framing_valid,
        visual_quality_valid=stats.visual_quality_valid,
        checks=checks,
        warnings=warnings,
        critical_errors=errors,
        preview_qa_passed=not errors,
    )


def _minimum_resolution(scene: SceneSpec) -> tuple[int, int]:
    width, height = scene.preview.resolution
    return width, height


def _png_stats(data: bytes, width: int, height: int, scene: SceneSpec) -> PreviewStats:
    try:
        bit_depth, color_type, channels, bytes_per_pixel = _png_color_info(data)
        if bit_depth != 8 or color_type not in {0, 2, 6}:
            return _unknown_stats("PREVIEW_PIXEL_ANALYSIS_UNSUPPORTED_FORMAT")
        raw = zlib.decompress(_png_idat_payload(data))
        stride = width * channels
        previous = bytearray(stride)
        sampled_pixels: list[tuple[int, int, int, int, int]] = []
        offset = 0
        sample_stride = max(1, math.ceil(math.sqrt((width * height) / 250_000)))
        for row_index in range(height):
            filter_type = raw[offset]
            offset += 1
            scanline = bytearray(raw[offset : offset + stride])
            offset += stride
            _unfilter_scanline(scanline, previous, filter_type, bytes_per_pixel)
            if row_index % sample_stride == 0:
                for index in range(0, stride, channels * sample_stride):
                    if channels == 1:
                        r = g = b = scanline[index]
                    else:
                        r, g, b = scanline[index], scanline[index + 1], scanline[index + 2]
                    sampled_pixels.append((index // channels, row_index, r, g, b))
            previous = scanline
        if not sampled_pixels:
            return _unknown_stats("PREVIEW_PIXEL_ANALYSIS_EMPTY")
        luminance_values = [
            (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
            for _, _, red, green, blue in sampled_pixels
        ]
        mean = sum(luminance_values) / len(luminance_values)
        variance = sum((value - mean) ** 2 for value in luminance_values) / len(luminance_values)
        stddev = math.sqrt(variance)
        non_dark_ratio = sum(1 for value in luminance_values if value >= 45) / len(luminance_values)
        subject = _subject_stats(sampled_pixels, width, height, scene)
        visual_quality_valid = (
            mean >= MIN_LUMINANCE_MEAN
            and stddev >= MIN_LUMINANCE_STDDEV
            and non_dark_ratio >= MIN_NON_DARK_PIXEL_RATIO
            and subject["framing_valid"]
        )
        return PreviewStats(
            luminance_mean=round(mean, 3),
            luminance_stddev=round(stddev, 3),
            non_dark_pixel_ratio=round(non_dark_ratio, 4),
            subject_pixel_ratio=subject["pixel_ratio"],
            subject_bbox_width_ratio=subject["bbox_width_ratio"],
            subject_bbox_height_ratio=subject["bbox_height_ratio"],
            subject_contrast_mean=subject["contrast_mean"],
            subject_center_x_ratio=subject["center_x_ratio"],
            subject_min_edge_margin_ratio=subject["min_edge_margin_ratio"],
            subject_touches_frame=subject["touches_frame"],
            subject_framing_valid=subject["framing_valid"],
            visual_quality_valid=visual_quality_valid,
        )
    except (IndexError, KeyError, ValueError, zlib.error, struct.error):
        return _unknown_stats("PREVIEW_PIXEL_ANALYSIS_FAILED")


def _subject_stats(
    sampled_pixels: list[tuple[int, int, int, int, int]],
    width: int,
    height: int,
    scene: SceneSpec,
) -> dict[str, float | bool]:
    border_x = max(1, round(width * 0.035))
    border_y = max(1, round(height * 0.035))
    border_pixels = [
        (red, green, blue)
        for x, y, red, green, blue in sampled_pixels
        if x <= border_x or x >= width - border_x or y <= border_y or y >= height - border_y
    ]
    if not border_pixels:
        border_pixels = [(red, green, blue) for _, _, red, green, blue in sampled_pixels]
    background = tuple(
        float(statistics.median(pixel[channel] for pixel in border_pixels)) for channel in range(3)
    )
    foreground: list[tuple[int, int, float]] = []
    for x, y, red, green, blue in sampled_pixels:
        distance = abs(red - background[0]) + abs(green - background[1]) + abs(blue - background[2])
        if distance >= FOREGROUND_COLOR_DISTANCE:
            foreground.append((x, y, distance))
    if not foreground:
        return {
            "pixel_ratio": 0.0,
            "bbox_width_ratio": 0.0,
            "bbox_height_ratio": 0.0,
            "contrast_mean": 0.0,
            "center_x_ratio": 0.0,
            "min_edge_margin_ratio": 0.0,
            "touches_frame": True,
            "framing_valid": False,
        }
    xs = [item[0] for item in foreground]
    ys = [item[1] for item in foreground]
    pixel_ratio = len(foreground) / len(sampled_pixels)
    bbox_width_ratio = (max(xs) - min(xs) + 1) / max(width, 1)
    bbox_height_ratio = (max(ys) - min(ys) + 1) / max(height, 1)
    contrast_mean = sum(item[2] for item in foreground) / len(foreground)
    center_x_ratio = ((min(xs) + max(xs)) / 2) / max(width - 1, 1)
    edge_margins = (
        min(xs) / max(width - 1, 1),
        (width - 1 - max(xs)) / max(width - 1, 1),
        min(ys) / max(height - 1, 1),
        (height - 1 - max(ys)) / max(height - 1, 1),
    )
    min_edge_margin_ratio = min(edge_margins)
    upper_foreground = [item for item in foreground if item[1] <= height * 0.82]
    silhouette = upper_foreground or foreground
    silhouette_xs = [item[0] for item in silhouette]
    left_margin = min(silhouette_xs) / max(width - 1, 1)
    right_margin = (width - 1 - max(silhouette_xs)) / max(width - 1, 1)
    top_margin = edge_margins[2]
    # Telecom previews intentionally include a ground plane that can meet the
    # lower and side image edges in the bottom context band. Side clipping is
    # therefore measured on the upper technical silhouette; top contact still
    # indicates real clipping and bottom contact remains bounded by max height.
    clipping_margins = (left_margin, right_margin, top_margin)
    touches_frame = min(clipping_margins) < MIN_SUBJECT_EDGE_MARGIN_RATIO
    minimum_width_ratio = _minimum_subject_width_ratio(scene)
    framing_valid = (
        pixel_ratio >= MIN_SUBJECT_PIXEL_RATIO
        and bbox_width_ratio >= minimum_width_ratio
        and bbox_height_ratio >= MIN_SUBJECT_BBOX_HEIGHT_RATIO
        and bbox_height_ratio <= MAX_SUBJECT_BBOX_HEIGHT_RATIO
        and contrast_mean >= MIN_SUBJECT_CONTRAST_MEAN
        and MIN_SUBJECT_CENTER_X_RATIO <= center_x_ratio <= MAX_SUBJECT_CENTER_X_RATIO
        and not touches_frame
    )
    return {
        "pixel_ratio": round(pixel_ratio, 4),
        "bbox_width_ratio": round(bbox_width_ratio, 4),
        "bbox_height_ratio": round(bbox_height_ratio, 4),
        "contrast_mean": round(contrast_mean, 3),
        "center_x_ratio": round(center_x_ratio, 4),
        "min_edge_margin_ratio": round(min_edge_margin_ratio, 4),
        "touches_frame": touches_frame,
        "framing_valid": framing_valid,
    }


def _minimum_subject_width_ratio(scene: SceneSpec) -> float:
    sector_count = len(scene.sectors)
    if sector_count >= 3:
        return 0.16
    if sector_count == 2:
        return 0.13
    return 0.09


def _png_color_info(data: bytes) -> tuple[int, int, int, int]:
    # IHDR is at offset 8 right after the PNG signature in standard PNGs.
    # Robustly locate the IHDR chunk in case ancillary chunks precede it.
    offset = len(PNG_SIGNATURE)
    while offset + 25 <= len(data):
        chunk_length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        if chunk_type == b"IHDR" and chunk_length == 13:
            # IHDR payload: width(4) + height(4) + bit_depth(1) + color_type(1) + ...
            bit_depth = data[offset + 16]
            color_type = data[offset + 17]
            channels_by_color_type = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
            channels = channels_by_color_type.get(color_type, 3)
            return bit_depth, color_type, channels, channels
        offset += 12 + chunk_length
    raise ValueError("IHDR chunk not found in PNG data")


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
        subject_pixel_ratio=None,
        subject_bbox_width_ratio=None,
        subject_bbox_height_ratio=None,
        subject_contrast_mean=None,
        subject_center_x_ratio=None,
        subject_min_edge_margin_ratio=None,
        subject_touches_frame=False,
        subject_framing_valid=False,
        visual_quality_valid=False,
        warning=warning,
    )
