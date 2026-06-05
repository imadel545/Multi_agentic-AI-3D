import struct
from pathlib import Path

from core.contracts.glb_inspection import PreviewInspectionReport
from core.contracts.scene import SceneSpec

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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
                critical_errors=["PREVIEW_FILE_TOO_SMALL"],
            )
        try:
            width, height, image_format = _parse_preview(preview_path)
        except (OSError, ValueError, struct.error):
            return _report(
                file_exists=True,
                file_size_bytes=file_size_bytes,
                width=0,
                height=0,
                image_format=None,
                minimum_resolution=_minimum_resolution(scene),
                critical_errors=["PREVIEW_FORMAT_INVALID"],
            )
        return _report(
            file_exists=True,
            file_size_bytes=file_size_bytes,
            width=width,
            height=height,
            image_format=image_format,
            minimum_resolution=_minimum_resolution(scene),
            critical_errors=[],
        )


def _parse_preview(path: Path) -> tuple[int, int, str]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("preview is not PNG")
    width, height = struct.unpack(">II", data[16:24])
    return width, height, "png"


def _report(
    *,
    file_exists: bool,
    file_size_bytes: int,
    width: int,
    height: int,
    image_format: str | None,
    minimum_resolution: tuple[int, int],
    critical_errors: list[str],
) -> PreviewInspectionReport:
    min_width, min_height = minimum_resolution
    minimum_resolution_valid = width >= min_width and height >= min_height
    checks = {
        "file_exists": file_exists,
        "format_valid": image_format == "png",
        "minimum_resolution_valid": minimum_resolution_valid,
    }
    errors = list(critical_errors)
    if not minimum_resolution_valid:
        errors.append("PREVIEW_MINIMUM_RESOLUTION_NOT_MET")
    return PreviewInspectionReport(
        inspection_mode="png_parse" if image_format == "png" else "not_available",
        file_exists=file_exists,
        file_size_bytes=file_size_bytes,
        width=width,
        height=height,
        format=image_format,
        minimum_resolution_valid=minimum_resolution_valid,
        checks=checks,
        warnings=[],
        critical_errors=errors,
        preview_qa_passed=not errors,
    )


def _minimum_resolution(scene: SceneSpec) -> tuple[int, int]:
    width, height = scene.preview.resolution
    return width, height
