import hashlib
from pathlib import Path

from core.contracts.assets import AssetManifest
from core.services.asset_evidence import (
    ProfessionalAssetVerifier,
    claims_professional_identity,
    preview_image_matches,
)
from core.services.asset_registry import AssetRegistry


class AssetInventoryService:
    def __init__(self, project_root: Path, registry: AssetRegistry) -> None:
        self.project_root = project_root
        self.registry = registry

    def inspect(self) -> dict:
        assets = self.registry.list_assets()
        verifier = self.registry.evidence_verifier
        entries = [inspect_asset_manifest(self.project_root, asset, verifier) for asset in assets]
        missing = [
            entry
            for entry in entries
            if entry["asset_file_required"] and not entry["asset_file_exists"]
        ]
        import_ready = [
            entry for entry in entries if entry["asset_import_mode"] == "imported_glb_exact"
        ]
        generation_eligible = [entry for entry in entries if entry["generation_eligible"]]
        professional_evidence = [entry for entry in entries if entry["milestone_evidence_eligible"]]
        reference_only = [
            entry for entry in entries if entry["qualification_status"] == "reference_only"
        ]
        integrity_failures = [
            entry for entry in entries if entry["asset_import_mode"] == "qualified_file_rejected"
        ]
        professional_evidence_rejected = [
            entry
            for entry in entries
            if entry["asset_import_mode"] == "professional_evidence_rejected"
        ]
        reference_evidence_missing = [
            entry
            for entry in entries
            if entry["qualification_status"] == "reference_only"
            and entry["local_evidence_status"] != "available"
        ]
        real_glb_files = [
            entry
            for entry in entries
            if entry["asset_file_exists"] and entry["file"].lower().endswith(".glb")
        ]
        fallback = [
            entry
            for entry in entries
            if entry["effective_generation_mode"] == "procedural_fallback"
        ]
        parametric = [
            entry
            for entry in entries
            if entry["effective_generation_mode"] == "parametric_generated"
        ]
        by_type: dict[str, int] = {}
        for entry in entries:
            by_type[entry["type"]] = by_type.get(entry["type"], 0) + 1
        status = "qualified_mixed_catalog"
        if integrity_failures or professional_evidence_rejected:
            status = "qualification_error"
        elif not generation_eligible:
            status = "no_generation_eligible_assets"
        return {
            "status": status,
            "asset_count": len(entries),
            "asset_count_by_type": by_type,
            "missing_file_count": len(missing),
            "real_glb_asset_count": len(real_glb_files),
            "import_ready_asset_count": len(import_ready),
            "import_qualified_glb_count": len(import_ready),
            "generation_eligible_asset_count": len(generation_eligible),
            "professional_evidence_asset_count": len(professional_evidence),
            "reference_only_asset_count": len(reference_only),
            "qualified_integrity_failure_count": len(integrity_failures),
            "professional_evidence_rejected_count": len(professional_evidence_rejected),
            "reference_evidence_missing_count": len(reference_evidence_missing),
            "procedural_fallback_count": len(fallback),
            "parametric_generation_count": len(parametric),
            "procedural_generation_required": bool(parametric or fallback),
            "entries": entries,
            "missing_files": missing,
        }

    def inspect_asset(self, asset_id: str) -> dict:
        """Return one effective inventory record using the shared admission authority."""

        return inspect_asset_manifest(
            self.project_root,
            self.registry.get(asset_id),
            self.registry.evidence_verifier,
        )


def inspect_asset_manifest(
    project_root: Path,
    asset: AssetManifest,
    verifier: ProfessionalAssetVerifier,
) -> dict:
    file_required = not asset.file.startswith("procedural://")
    path = _safe_project_path(project_root, asset.file) if file_required else None
    file_exists = bool(path and path.is_file())
    dimensions_checked = asset.dimensions_m is not None
    qualification = asset.qualification
    expected_sha256 = qualification.verified_file_sha256
    actual_sha256 = _sha256_file(path) if path and file_exists and expected_sha256 else None
    hash_matches = actual_sha256 == expected_sha256 if expected_sha256 else None
    import_authorized = asset.allows_generation_mode("imported_glb_exact")
    parametric_authorized = asset.allows_generation_mode("parametric_generated")
    admission = verifier.verify_effective_generation_admission(asset)
    import_ready = admission.eligible and import_authorized and file_exists and hash_matches is True
    parametric_ready = admission.eligible and parametric_authorized
    generation_eligible = import_ready or parametric_ready
    warnings = []
    if file_required and not file_exists:
        warnings.append("ASSET_FILE_MISSING")
    if asset.source == "internal_test_minimal":
        warnings.append("INTERNAL_TEST_MINIMAL_ASSET_NOT_VENDOR_GRADE")
    if asset.source == "internal_cleaned":
        warnings.append("INTERNAL_CLEANED_ASSET_NOT_VENDOR_GRADE")
    if asset.source == "internal_project_generated":
        warnings.append("INTERNAL_PROJECT_GENERATED_ASSET_NOT_VENDOR_GRADE")
    if asset.attribution_required:
        warnings.append("ATTRIBUTION_REQUIRED")
    if asset.source == "cc_by":
        warnings.append("CC_BY_ASSET_NOT_VENDOR_GRADE")
    professional_admission_failed = (
        claims_professional_identity(asset)
        and asset.is_generation_eligible
        and not admission.eligible
    )
    if professional_admission_failed:
        warnings.append("PROFESSIONAL_ASSET_EVIDENCE_NOT_ADMITTED")
    if import_authorized and not file_exists:
        warnings.append("QUALIFIED_ASSET_FILE_MISSING")
    if import_authorized and file_exists and hash_matches is False:
        warnings.append("QUALIFIED_ASSET_HASH_MISMATCH")
    if professional_admission_failed:
        asset_import_mode = "professional_evidence_rejected"
        effective_generation_mode = "quarantined_unverified"
    elif import_ready:
        asset_import_mode = "imported_glb_exact"
        effective_generation_mode = "imported_glb_exact"
    elif parametric_ready:
        asset_import_mode = "parametric_generated"
        effective_generation_mode = "parametric_generated"
    elif import_authorized:
        asset_import_mode = "qualified_file_rejected"
        effective_generation_mode = (
            "procedural_fallback" if asset.import_fallback_allowed else "missing_file"
        )
    elif qualification.status == "reference_only":
        asset_import_mode = "reference_only"
        effective_generation_mode = "reference_only"
    else:
        asset_import_mode = "quarantined_unverified"
        effective_generation_mode = "quarantined_unverified"
    preview_set = []
    for preview in asset.preview_set:
        preview_path = _safe_project_path(project_root, preview.file)
        preview_exists = bool(preview_path and preview_path.is_file())
        preview_hash_matches = (
            _sha256_file(preview_path) == preview.sha256
            if preview_path is not None and preview_exists
            else False
        )
        preview_valid = bool(
            preview_path
            and preview_hash_matches
            and preview_image_matches(preview_path, preview.width_px, preview.height_px)
        )
        preview_set.append(
            {
                "view": preview.view,
                "url": f"/assets/{asset.asset_id}/previews/{preview.view}",
                "sha256": preview.sha256,
                "available": preview_valid,
                "content_type": "image/png",
                "width_px": preview.width_px,
                "height_px": preview.height_px,
                "qa_status": preview.qa_status,
            }
        )
    evidence_paths = []
    for representation in (asset.master_representation, asset.viewer_representation):
        if representation is not None:
            evidence_paths.append((representation.file, representation.sha256))
    if asset.qa_evidence.report_file and asset.qa_evidence.report_sha256:
        evidence_paths.append((asset.qa_evidence.report_file, asset.qa_evidence.report_sha256))
    evidence_paths.extend((preview.file, preview.sha256) for preview in asset.preview_set)
    evidence_matches = []
    for relative_path, expected_hash in evidence_paths:
        evidence_path = _safe_project_path(project_root, relative_path)
        evidence_matches.append(
            bool(
                evidence_path
                and evidence_path.is_file()
                and _sha256_file(evidence_path) == expected_hash
            )
        )
    if not evidence_paths:
        local_evidence_status = "not_published"
    elif all(evidence_matches):
        local_evidence_status = "available"
    elif any(evidence_matches):
        local_evidence_status = "partial"
    else:
        local_evidence_status = "unavailable"
    evidence = verifier.verify(asset)
    return {
        "asset_id": asset.asset_id,
        "type": asset.type,
        # Keep the technical response useful for display while never exposing
        # a path that could reveal the local catalog layout.
        "file": Path(asset.file).name if file_required else asset.file,
        "file_exists": file_exists,
        "asset_file_exists": file_exists,
        "asset_file_required": file_required,
        "asset_import_mode": asset_import_mode,
        "asset_import_success": None,
        "effective_generation_mode": effective_generation_mode,
        "import_fallback_allowed": asset.import_fallback_allowed,
        "source": asset.source,
        "source_provenance": asset.source_provenance,
        "license": asset.license,
        "attribution_required": asset.attribution_required,
        "attribution": asset.attribution,
        "original_url": asset.original_url,
        "original_author": asset.original_author,
        "normalized_by": asset.normalized_by,
        "pivot_policy": asset.pivot_policy,
        "front_axis": asset.front_axis,
        "adaptation_profile_id": asset.adaptation_profile_id,
        "qualification_status": qualification.status,
        "generation_eligible": generation_eligible,
        "allowed_generation_modes": (
            list(qualification.allowed_generation_modes) if admission.eligible else []
        ),
        "qualification_method": qualification.qualification_method,
        "qualification_limitations": list(qualification.limitations),
        "verified_file_sha256": expected_sha256,
        "actual_file_sha256": actual_sha256,
        "qualified_file_hash_matches": hash_matches,
        "mesh_integrity_verified": qualification.mesh_integrity_verified,
        "pivot_verified": qualification.pivot_verified,
        "orientation_verified": qualification.orientation_verified,
        "status": asset.status,
        "compatible_networks": asset.compatible_networks,
        "compatible_tower_types": asset.compatible_tower_types,
        "dimensions_m": asset.dimensions_m.model_dump() if asset.dimensions_m else None,
        "asset_dimensions_checked": dimensions_checked,
        "mount_zones": [zone.model_dump() for zone in asset.mount_zones],
        "family": asset.resolved_family,
        "subtype": asset.subtype,
        "manufacturer": asset.manufacturer,
        "reference": asset.reference,
        "source_format": asset.resolved_source_format,
        "geometry_status": asset.resolved_geometry_status,
        "fidelity_status": asset.geometry_fidelity,
        "qualification_version": asset.qualification_version,
        "preview_set": preview_set,
        "local_evidence_status": local_evidence_status,
        "reference_evidence_available": local_evidence_status == "available",
        "provenance_url": f"/assets/{asset.asset_id}/provenance",
        "visual_review_status": "not_requested",
        "milestone_evidence_eligible": evidence.eligible,
        "milestone_evidence_failures": list(evidence.failures),
        "anchor_count": len(asset.anchors),
        "connector_count": len(asset.connectors),
        "warnings": warnings,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_project_path(project_root: Path, relative_path: str) -> Path | None:
    candidate = (project_root / relative_path).resolve()
    try:
        candidate.relative_to(project_root.resolve())
    except ValueError:
        return None
    return candidate
