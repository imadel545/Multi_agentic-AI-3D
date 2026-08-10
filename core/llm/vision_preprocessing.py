from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

from core.contracts.vision import NormalizedImageRegion, VisualEvidenceSource


class VisionPreprocessingError(ValueError):
    pass


class VisionPreprocessingUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class VisionImageInput:
    content: bytes = field(repr=False)
    file_name: str
    page: int | None = None
    region: NormalizedImageRegion | None = None


@dataclass(frozen=True)
class PreparedVisionImage:
    evidence_source: VisualEvidenceSource
    content: bytes = field(repr=False)

    @property
    def data_url(self) -> str:
        import base64

        encoded = base64.b64encode(self.content).decode("ascii")
        return f"data:{self.evidence_source.mime_type};base64,{encoded}"


class VisionImagePreprocessor:
    """Create metadata-free bounded derivatives without modifying source bytes."""

    _ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}

    def __init__(
        self,
        *,
        max_images: int = 3,
        max_image_bytes: int = 20_000_000,
        max_output_pixels: int = 16_000_000,
        max_source_pixels: int = 64_000_000,
        max_edge_px: int = 4096,
    ) -> None:
        if not 1 <= max_images <= 3:
            raise ValueError("max_images must be between 1 and 3")
        if not 1 <= max_image_bytes <= 20_000_000:
            raise ValueError("max_image_bytes must be between 1 and 20000000")
        if not 1_000_000 <= max_output_pixels <= 16_000_000:
            raise ValueError("max_output_pixels must be between 1000000 and 16000000")
        if max_source_pixels < max_output_pixels:
            raise ValueError("max_source_pixels must be at least max_output_pixels")
        if not 512 <= max_edge_px <= 8192:
            raise ValueError("max_edge_px must be between 512 and 8192")
        self.max_images = max_images
        self.max_image_bytes = max_image_bytes
        self.max_output_pixels = max_output_pixels
        self.max_source_pixels = max_source_pixels
        self.max_edge_px = max_edge_px

    def prepare_many(self, inputs: list[VisionImageInput]) -> list[PreparedVisionImage]:
        if not inputs:
            raise VisionPreprocessingError("at least one image is required")
        if len(inputs) > self.max_images:
            raise VisionPreprocessingError(
                f"at most {self.max_images} images are allowed per vision request"
            )
        return [self._prepare(item, index=index) for index, item in enumerate(inputs, start=1)]

    def _prepare(self, item: VisionImageInput, *, index: int) -> PreparedVisionImage:
        try:
            from PIL import Image, ImageOps, UnidentifiedImageError
        except ImportError as exc:
            raise VisionPreprocessingUnavailable(
                "Pillow is required for bounded remote-vision preprocessing"
            ) from exc

        if not item.content:
            raise VisionPreprocessingError("image content must not be empty")
        if len(item.content) > self.max_image_bytes:
            raise VisionPreprocessingError("source image exceeds the 20 MB capability limit")
        if item.page is not None and item.page < 1:
            raise VisionPreprocessingError("page must be greater than or equal to one")

        source_sha256 = hashlib.sha256(item.content).hexdigest()
        try:
            with Image.open(io.BytesIO(item.content)) as source:
                source_format = str(source.format or "").upper()
                detected_mime = self._ALLOWED_FORMATS.get(source_format)
                if detected_mime is None:
                    raise VisionPreprocessingError(
                        "only JPEG, PNG, and WebP images are accepted for remote vision"
                    )
                width, height = source.size
                if width <= 0 or height <= 0:
                    raise VisionPreprocessingError("image dimensions must be positive")
                if width * height > self.max_source_pixels:
                    raise VisionPreprocessingError("source image exceeds the decoded pixel budget")
                source.load()
                normalized = ImageOps.exif_transpose(source).convert("RGB")
        except VisionPreprocessingError:
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise VisionPreprocessingError("image content is corrupt or unsupported") from exc

        normalized.thumbnail(
            self._target_size(normalized.width, normalized.height),
            Image.Resampling.LANCZOS,
        )
        # Copy pixel data into a fresh image so EXIF, ICC, comments and source
        # path metadata cannot be propagated to the provider derivative.
        clean = Image.new("RGB", normalized.size)
        clean.paste(normalized)
        content, mime_type = self._encode(clean, detected_mime)
        if len(content) > self.max_image_bytes:
            raise VisionPreprocessingError("prepared image exceeds the provider byte budget")
        prepared_sha256 = hashlib.sha256(content).hexdigest()
        safe_name = _safe_file_name(item.file_name)
        source = VisualEvidenceSource(
            source_id=f"image_{index}",
            file_name=safe_name,
            source_sha256=source_sha256,
            prepared_sha256=prepared_sha256,
            mime_type=mime_type,
            width_px=clean.width,
            height_px=clean.height,
            page=item.page,
            region=item.region,
        )
        return PreparedVisionImage(evidence_source=source, content=content)

    def _target_size(self, width: int, height: int) -> tuple[int, int]:
        scale = min(1.0, self.max_edge_px / max(width, height))
        pixels_after_edge = width * height * scale * scale
        if pixels_after_edge > self.max_output_pixels:
            scale *= (self.max_output_pixels / pixels_after_edge) ** 0.5
        return max(1, round(width * scale)), max(1, round(height * scale))

    def _encode(self, image, detected_mime: str) -> tuple[bytes, str]:
        output = io.BytesIO()
        if detected_mime == "image/jpeg":
            image.save(output, format="JPEG", quality=92, optimize=True)
            return output.getvalue(), "image/jpeg"
        image.save(output, format="PNG", optimize=True)
        png = output.getvalue()
        if len(png) <= self.max_image_bytes:
            return png, "image/png"
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=90, optimize=True)
        return output.getvalue(), "image/jpeg"


def _safe_file_name(value: str) -> str:
    candidate = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not candidate:
        candidate = "visual-input"
    # Path.name also removes the special '.' and '..' path forms.
    safe = Path(candidate).name
    if safe in {"", ".", ".."}:
        safe = "visual-input"
    return safe[:255]
