from __future__ import annotations

import hashlib
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from core.contracts.assets import AssetManifest
from core.qa.gltf_integrity import inspect_gltf_integrity


@dataclass(frozen=True)
class ProfessionalAssetVerification:
    eligible: bool
    failures: tuple[str, ...]


class ProfessionalAssetVerifier:
    """Verify professional asset evidence against immutable bytes on disk.

    Manifest validation establishes declaration consistency. This boundary is
    deliberately filesystem-aware and is the only authority used by public
    inventory and decision packets for the professional milestone flag.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def verify(self, manifest: AssetManifest) -> ProfessionalAssetVerification:
        failures = list(manifest.milestone_evidence_declaration_failures)
        master = manifest.master_representation
        viewer = manifest.viewer_representation

        master_path = self._evidence_path(
            master.file if master is not None else None,
            label="Master representation",
            failures=failures,
        )
        viewer_path = self._evidence_path(
            viewer.file if viewer is not None else None,
            label="Viewer representation",
            failures=failures,
        )
        if master is not None and master_path is not None:
            self._verify_hash(
                master_path,
                master.sha256,
                "Master representation hash does not match its published SHA-256.",
                failures,
            )
        if viewer is not None and viewer_path is not None:
            self._verify_hash(
                viewer_path,
                viewer.sha256,
                "Viewer representation hash does not match its published SHA-256.",
                failures,
            )
            integrity = inspect_gltf_integrity(viewer_path)
            if integrity.errors or integrity.valid_primitive_count < 1:
                failures.append("Viewer representation is not a valid GLB with mesh geometry.")

        for preview in manifest.preview_set:
            preview_path = self._evidence_path(
                preview.file,
                label=f"Qualification preview ({preview.view})",
                failures=failures,
            )
            if preview_path is None:
                continue
            self._verify_hash(
                preview_path,
                preview.sha256,
                f"Qualification preview hash does not match: {preview.view}.",
                failures,
            )
            dimensions = _inspect_png(preview_path)
            if dimensions is None:
                failures.append(f"Qualification preview is not a valid PNG: {preview.view}.")
            elif dimensions != (preview.width_px, preview.height_px):
                failures.append(
                    f"Qualification preview dimensions do not match: {preview.view}."
                )

        report_path = self._evidence_path(
            manifest.qa_evidence.report_file,
            label="Professional QA report",
            failures=failures,
        )
        if report_path is not None and manifest.qa_evidence.report_sha256 is not None:
            self._verify_hash(
                report_path,
                manifest.qa_evidence.report_sha256,
                "Professional QA report hash does not match its published SHA-256.",
                failures,
            )
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                report = None
            if not isinstance(report, dict) or report.get("status") != "passed":
                failures.append("Professional QA report is not a readable passed report.")

        _verify_dimensions_and_anchors(manifest, failures)
        unique_failures = tuple(dict.fromkeys(failures))
        return ProfessionalAssetVerification(
            eligible=not unique_failures,
            failures=unique_failures,
        )

    def _evidence_path(
        self,
        relative_path: str | None,
        *,
        label: str,
        failures: list[str],
    ) -> Path | None:
        if not relative_path:
            return None
        candidate = (self.project_root / relative_path).resolve()
        try:
            candidate.relative_to(self.project_root)
        except ValueError:
            failures.append(f"{label} path escapes the project evidence root.")
            return None
        if not candidate.is_file():
            failures.append(f"{label} file is missing.")
            return None
        return candidate

    @staticmethod
    def _verify_hash(
        path: Path,
        expected: str,
        failure: str,
        failures: list[str],
    ) -> None:
        if _sha256_file(path) != expected:
            failures.append(failure)


def _verify_dimensions_and_anchors(manifest: AssetManifest, failures: list[str]) -> None:
    dimensions = manifest.dimensions_m
    bounds = manifest.bounding_box_m
    if dimensions is None or bounds is None:
        return
    extents = tuple(bounds.maximum[index] - bounds.minimum[index] for index in range(3))
    declared = (dimensions.width, dimensions.depth, dimensions.height)
    if any(abs(extents[index] - declared[index]) > 1e-6 for index in range(3)):
        failures.append("Qualified dimensions do not match the published bounding box.")
    for anchor in manifest.anchors:
        if any(
            anchor.position_m[index] < bounds.minimum[index] - 1e-6
            or anchor.position_m[index] > bounds.maximum[index] + 1e-6
            for index in range(3)
        ):
            failures.append(f"Qualified anchor is outside the bounding box: {anchor.anchor_id}.")


def _inspect_png(path: Path) -> tuple[int, int] | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    offset = 8
    width = height = None
    idat = bytearray()
    found_end = False
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        offset += 4
        kind = data[offset : offset + 4]
        offset += 4
        if offset + length + 4 > len(data):
            return None
        payload = data[offset : offset + length]
        offset += length
        checksum = struct.unpack_from(">I", data, offset)[0]
        offset += 4
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != checksum:
            return None
        if kind == b"IHDR":
            if length != 13:
                return None
            width, height = struct.unpack_from(">II", payload, 0)
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            found_end = True
            break
    if not width or not height or not idat or not found_end:
        return None
    try:
        if not zlib.decompress(bytes(idat)):
            return None
    except zlib.error:
        return None
    return width, height


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
