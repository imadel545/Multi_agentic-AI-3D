"""Verify sector inspection previews against the actual exported GLB.

The Blender worker renders the image, but this module runs outside Blender and
accepts it only after checking the exported glTF semantic extras, declared
sector roles, PNG framing evidence, and byte hashes.  It intentionally makes
no claim about vendor fidelity, mounting fitness, RF performance, or visual
semantics beyond the bounded measurements below.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from core.contracts.scene import SceneSpec
from core.contracts.sector_preview import (
    SectorPreviewEvidence,
    SectorPreviewEvidenceItem,
    SectorPreviewVisualInspection,
)
from core.qa.glb_inspector import GLBInspector
from core.qa.gltf_integrity import inspect_gltf_integrity
from core.qa.preview_inspector import PreviewInspector

_TECHNICAL_ROLES = frozenset({"antenna", "mount_bracket", "radio", "rru", "cable"})
_MIN_SECTOR_SUBJECT_WIDTH_RATIO = 0.09
_MIN_SECTOR_SUBJECT_HEIGHT_RATIO = 0.55
_MAX_SECTOR_SUBJECT_HEIGHT_RATIO = 0.92
_MIN_SECTOR_CONTRAST_MEAN = 45.0
_MIN_SECTOR_PIXEL_RATIO = 0.004


def sector_preview_required(scene: SceneSpec) -> bool:
    """Limit this evidence to selectable telecom assemblies with stable roots."""

    return bool(
        scene.sectors
        and scene.assembly_plan is not None
        and scene.assembly_plan.schema_version == "1.1.0"
    )


def sector_preview_id(sector_id: str) -> str:
    return hashlib.sha256(sector_id.encode("utf-8")).hexdigest()[:16]


def sector_preview_file_name(sector_id: str) -> str:
    return f"preview_sector_{sector_preview_id(sector_id)}.png"


class SectorPreviewInspector:
    def inspect(self, output_dir: Path, scene: SceneSpec) -> SectorPreviewEvidence:
        glb_path = output_dir / "design.glb"
        metadata_path = output_dir / "scene_metadata.json"
        metadata = _read_json(metadata_path)
        glb_report = GLBInspector().inspect(glb_path, scene, metadata_path)
        errors: list[str] = []
        if not glb_report.structural_qa_passed:
            errors.append("SECTOR_PREVIEW_GLB_STRUCTURAL_QA_FAILED")
        if glb_report.semantic_inspection_mode != "semantic_extras":
            errors.append("SECTOR_PREVIEW_GLB_SEMANTIC_EXTRAS_REQUIRED")

        payload = _sector_preview_payload(metadata)
        expected_sector_ids = [sector.sector_id for sector in scene.sectors]
        records = _records_by_sector(payload, expected_sector_ids, errors)
        roots_by_sector = _exported_roots_by_sector(glb_path, expected_sector_ids, errors)
        previews: list[SectorPreviewEvidenceItem] = []
        for sector in scene.sectors:
            sector_id = sector.sector_id
            record = records.get(sector_id)
            if record is None:
                continue
            preview = _inspect_record(
                output_dir=output_dir,
                scene=scene,
                sector=sector,
                record=record,
                glb_report=glb_report,
                exported_roots=roots_by_sector.get(sector_id, {}),
                errors=errors,
            )
            if preview is not None:
                previews.append(preview)

        if len(previews) != len(expected_sector_ids):
            errors.append("SECTOR_PREVIEW_EVIDENCE_INCOMPLETE")
        return SectorPreviewEvidence(
            scene_id=scene.scene_id,
            status="passed" if not errors else "failed",
            measurement_scope="exported_glb_semantics_and_rendered_sector_preview",
            glb_sha256=_sha256(glb_path) if glb_path.is_file() else "0" * 64,
            previews=previews,
            limitations=[
                "Chaque image cadre le sous-assemblage sectoriel rendu par Blender et mesure "
                "sa présence, son contraste et son cadrage.",
                "Cette preuve ne certifie ni la géométrie constructeur, ni le contact, la "
                "fixation, les charges, les raccordements électriques ou les performances RF.",
            ],
            errors=sorted(set(errors)),
        )


def verify_sector_preview_evidence(artifact_dir: Path, scene: SceneSpec) -> SectorPreviewEvidence:
    """Re-run the bounded proof before serving a persisted sector image."""

    evidence_path = artifact_dir / "sector_preview_evidence.json"
    try:
        persisted = SectorPreviewEvidence.model_validate_json(
            evidence_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("ACTIVE_VERSION_SECTOR_PREVIEW_EVIDENCE_INVALID") from exc
    inspected = SectorPreviewInspector().inspect(artifact_dir, scene)
    if inspected.status != "passed" or persisted != inspected:
        raise ValueError("ACTIVE_VERSION_SECTOR_PREVIEW_EVIDENCE_MISMATCH")
    return persisted


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sector_preview_payload(metadata: dict[str, Any]) -> object:
    camera = metadata.get("preview_camera")
    return camera.get("sector_preview_views") if isinstance(camera, dict) else None


def _records_by_sector(
    payload: object,
    expected_sector_ids: list[str],
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, list):
        errors.append("SECTOR_PREVIEW_METADATA_MISSING")
        return {}
    records: dict[str, dict[str, Any]] = {}
    for record in payload:
        if not isinstance(record, dict):
            errors.append("SECTOR_PREVIEW_METADATA_INVALID")
            continue
        sector_id = record.get("sector_id")
        if not isinstance(sector_id, str) or sector_id not in expected_sector_ids:
            errors.append("SECTOR_PREVIEW_METADATA_SECTOR_INVALID")
            continue
        if sector_id in records:
            errors.append("SECTOR_PREVIEW_METADATA_DUPLICATE")
            continue
        records[sector_id] = record
    if set(records) != set(expected_sector_ids):
        errors.append("SECTOR_PREVIEW_METADATA_INCOMPLETE")
    return records


def _exported_roots_by_sector(
    glb_path: Path,
    expected_sector_ids: list[str],
    errors: list[str],
) -> dict[str, dict[str, set[str]]]:
    integrity = inspect_gltf_integrity(glb_path)
    payload = integrity.payload
    if not isinstance(payload, dict):
        errors.append("SECTOR_PREVIEW_GLB_PARSE_FAILED")
        return {}
    roots: dict[str, dict[str, set[str]]] = {}
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        errors.append("SECTOR_PREVIEW_GLB_NODES_INVALID")
        return roots
    for node in nodes:
        if not isinstance(node, dict):
            continue
        extras = node.get("extras")
        if not isinstance(extras, dict):
            continue
        sector_id = extras.get("sector_id")
        role = str(extras.get("role") or extras.get("object_role") or "").lower()
        semantic_root = extras.get("semantic_root")
        if (
            not isinstance(sector_id, str)
            or sector_id not in expected_sector_ids
            or role not in _TECHNICAL_ROLES
            or not isinstance(semantic_root, str)
            or not semantic_root
        ):
            continue
        roots.setdefault(sector_id, {}).setdefault(role, set()).add(semantic_root)
    return roots


def _inspect_record(
    *,
    output_dir: Path,
    scene: SceneSpec,
    sector,
    record: dict[str, Any],
    glb_report,
    exported_roots: dict[str, set[str]],
    errors: list[str],
) -> SectorPreviewEvidenceItem | None:
    sector_id = sector.sector_id
    preview_id = sector_preview_id(sector_id)
    file_name = record.get("file_name")
    if file_name != sector_preview_file_name(sector_id):
        errors.append(f"SECTOR_PREVIEW_FILE_NAME_INVALID:{sector_id}")
        return None
    path = output_dir / file_name
    expected_roles = ["antenna"]
    if sector.radio_asset_id:
        expected_roles.append("rru")
    if sector.include_cable:
        expected_roles.append("cable")
    exported_roles = sorted(role for role in exported_roots if role in _TECHNICAL_ROLES)
    framed_roles = record.get("framed_roles")
    expected_framed_roles = ["antenna", "mount_bracket"]
    if sector.radio_asset_id:
        expected_framed_roles.append("radio")
    if framed_roles != expected_framed_roles:
        errors.append(f"SECTOR_PREVIEW_FRAMED_ROLE_SET_INVALID:{sector_id}")
        return None
    canonical_roles = set(glb_report.semantic_sector_ids)
    for role in expected_roles:
        if sector_id not in glb_report.semantic_sector_ids.get(role, []):
            errors.append(f"SECTOR_PREVIEW_EXPORTED_ROLE_MISSING:{sector_id}:{role}")
    if not path.is_file() or Path(file_name).name != file_name:
        errors.append(f"SECTOR_PREVIEW_FILE_MISSING:{sector_id}")
        return None
    if record.get("sha256") != _sha256(path) or record.get("size_bytes") != path.stat().st_size:
        errors.append(f"SECTOR_PREVIEW_RENDER_EVIDENCE_MISMATCH:{sector_id}")
        return None
    visual_inspection = _inspect_sector_visual_quality(path, scene)
    if not visual_inspection.visual_quality_passed:
        errors.append(f"SECTOR_PREVIEW_VISUAL_QA_FAILED:{sector_id}")
    semantic_roots = sorted({root for values in exported_roots.values() for root in values})
    if not semantic_roots:
        errors.append(f"SECTOR_PREVIEW_SEMANTIC_ROOTS_MISSING:{sector_id}")
        return None
    if not canonical_roles:
        errors.append("SECTOR_PREVIEW_GLB_SEMANTIC_ROLES_MISSING")
    return SectorPreviewEvidenceItem(
        preview_id=preview_id,
        sector_id=sector_id,
        file_name=file_name,
        sha256=_sha256(path),
        size_bytes=path.stat().st_size,
        semantic_roots=semantic_roots,
        expected_roles=expected_roles,
        exported_roles=exported_roles,
        framed_roles=framed_roles,
        post_blender_identity_verified=bool(
            glb_report.structural_qa_passed
            and glb_report.semantic_inspection_mode == "semantic_extras"
            and all(
                sector_id in glb_report.semantic_sector_ids.get(role, []) for role in expected_roles
            )
        ),
        visual_inspection=visual_inspection,
    )


def _inspect_sector_visual_quality(path: Path, scene: SceneSpec) -> SectorPreviewVisualInspection:
    """Use measured pixels with compact-equipment thresholds, never tower ones."""

    inspection = PreviewInspector().inspect(path, scene)
    checks = {
        "file_exists": inspection.file_exists,
        "format_valid": inspection.format == "png",
        "minimum_resolution_valid": inspection.minimum_resolution_valid,
        "subject_present": (inspection.subject_pixel_ratio or 0.0) >= _MIN_SECTOR_PIXEL_RATIO,
        "subject_width_valid": (inspection.subject_bbox_width_ratio or 0.0)
        >= _MIN_SECTOR_SUBJECT_WIDTH_RATIO,
        "subject_height_valid": _MIN_SECTOR_SUBJECT_HEIGHT_RATIO
        <= (inspection.subject_bbox_height_ratio or 0.0)
        <= _MAX_SECTOR_SUBJECT_HEIGHT_RATIO,
        "subject_contrast_valid": (inspection.subject_contrast_mean or 0.0)
        >= _MIN_SECTOR_CONTRAST_MEAN,
        "subject_centered": inspection.subject_center_x_ratio is not None
        and 0.25 <= inspection.subject_center_x_ratio <= 0.75,
        "subject_not_clipped": not inspection.subject_touches_frame,
    }
    errors = [name.upper() for name, passed in checks.items() if not passed]
    return SectorPreviewVisualInspection(
        inspection_mode=inspection.inspection_mode,
        file_exists=inspection.file_exists,
        file_size_bytes=inspection.file_size_bytes,
        width=inspection.width,
        height=inspection.height,
        format=inspection.format,
        minimum_resolution_valid=inspection.minimum_resolution_valid,
        subject_pixel_ratio=inspection.subject_pixel_ratio,
        subject_bbox_width_ratio=inspection.subject_bbox_width_ratio,
        subject_bbox_height_ratio=inspection.subject_bbox_height_ratio,
        subject_contrast_mean=inspection.subject_contrast_mean,
        subject_center_x_ratio=inspection.subject_center_x_ratio,
        subject_touches_frame=inspection.subject_touches_frame,
        checks=checks,
        critical_errors=errors,
        visual_quality_passed=not errors,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
