from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from core.contracts.assets import AssetManifest
from core.qa.gltf_integrity import inspect_gltf_integrity
from core.services.professional_asset_worker_gate import (
    _inspect_png,
    professional_evidence_failures,
)
from core.services.professional_asset_worker_gate import (
    claims_professional_identity as _claims_professional_identity,
)


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
        payload = manifest.model_dump(mode="json")
        failures = list(professional_evidence_failures(payload, self.project_root))
        viewer = manifest.viewer_representation
        if viewer is not None:
            viewer_path = (self.project_root / viewer.file).resolve()
            try:
                viewer_path.relative_to(self.project_root)
            except ValueError:
                viewer_path = None
            if viewer_path is not None and viewer_path.is_file():
                integrity = inspect_gltf_integrity(viewer_path)
                if integrity.errors or integrity.valid_primitive_count < 1:
                    failures.append("Viewer representation is not a valid GLB with mesh geometry.")
        unique_failures = tuple(dict.fromkeys(failures))
        return ProfessionalAssetVerification(
            eligible=not unique_failures,
            failures=unique_failures,
        )

    def verify_generation_admission(
        self,
        manifest: AssetManifest,
    ) -> ProfessionalAssetVerification:
        """Return the effective generation decision for one manifest.

        Technical internal assets retain their existing qualification contract.
        A manifest that claims a manufacturer identity or vendor-qualified
        geometry must also pass the filesystem-aware professional evidence gate.
        """

        if not manifest.is_generation_eligible:
            return ProfessionalAssetVerification(
                eligible=False,
                failures=("Asset is not qualified for generation.",),
            )
        if not claims_professional_identity(manifest):
            return ProfessionalAssetVerification(eligible=True, failures=())
        return self.verify(manifest)

    def verify_effective_generation_admission(
        self,
        manifest: AssetManifest,
    ) -> ProfessionalAssetVerification:
        """Verify that at least one declared generation route is executable now."""

        declared = self.verify_generation_admission(manifest)
        if not declared.eligible:
            return declared
        if manifest.allows_generation_mode("parametric_generated"):
            return ProfessionalAssetVerification(eligible=True, failures=())
        if not manifest.allows_generation_mode("imported_glb_exact"):
            return ProfessionalAssetVerification(
                eligible=False,
                failures=("No executable generation mode is admitted.",),
            )
        runtime_path = (self.project_root / manifest.file).resolve()
        try:
            runtime_path.relative_to(self.project_root)
        except ValueError:
            return ProfessionalAssetVerification(
                eligible=False,
                failures=("Runtime asset path escapes the project root.",),
            )
        if not runtime_path.is_file():
            return ProfessionalAssetVerification(
                eligible=False,
                failures=("Qualified runtime asset file is missing.",),
            )
        expected = manifest.qualification.verified_file_sha256
        if not expected:
            return ProfessionalAssetVerification(
                eligible=False,
                failures=("Qualified runtime asset hash is not published.",),
            )
        if _sha256(runtime_path) != expected:
            return ProfessionalAssetVerification(
                eligible=False,
                failures=("Qualified runtime asset hash does not match.",),
            )
        integrity = inspect_gltf_integrity(runtime_path)
        if integrity.errors or integrity.valid_primitive_count < 1:
            return ProfessionalAssetVerification(
                eligible=False,
                failures=("Qualified runtime asset is not a valid GLB with mesh geometry.",),
            )
        return ProfessionalAssetVerification(eligible=True, failures=())

    def qualification_review(
        self,
        manifest: AssetManifest,
        *,
        published_previews: list[dict] | None = None,
        evidence: ProfessionalAssetVerification | None = None,
        admission: ProfessionalAssetVerification | None = None,
    ) -> dict:
        """Project effective admission into stable, user-facing review checks.

        The frontend must not reconstruct professional admission from optimistic
        manifest fields.  This projection is derived from the same filesystem
        checks used by planning and exposes only actions that are already real.
        """

        professional = claims_professional_identity(manifest)
        evidence = evidence if evidence is not None else (
            self.verify(manifest) if professional else None
        )
        admission = admission or self.verify_effective_generation_admission(manifest)
        if not professional:
            status = "technical_asset"
        elif admission.eligible and evidence is not None and evidence.eligible:
            status = "admitted"
        elif manifest.qualification.status == "reference_only":
            status = "reference_only"
        elif manifest.is_generation_eligible:
            status = "evidence_invalid"
        else:
            status = "blocked"

        failures = evidence.failures if evidence is not None else ()
        previews = list(published_previews or [])
        verified_views = sorted(
            str(preview["view"])
            for preview in previews
            if preview.get("available") is True and preview.get("qa_status") == "passed"
        )
        expected_views = {"front", "side", "top", "perspective", "closeup"}
        master = manifest.master_representation
        viewer = manifest.viewer_representation
        lineage_declared = bool(
            master
            and viewer
            and viewer.derived_from_representation_id == master.representation_id
            and manifest.source_file_sha256
            and manifest.qualification.verified_file_sha256 == viewer.sha256
        )
        checks = [
            _review_check(
                "identity_source",
                bool(
                    manifest.source_provenance
                    and manifest.source_file_sha256
                    and (not professional or (manifest.manufacturer and manifest.reference))
                ),
                "Identité et source",
                "La référence, la provenance et l’empreinte de la source sont documentées.",
                (
                    "L’identité constructeur, la provenance ou l’empreinte de la source "
                    "reste incomplète."
                ),
            ),
            _review_check(
                "usage_rights",
                bool(
                    manifest.license
                    and manifest.usage_rights.status == "project_authorized"
                    and manifest.usage_rights.project_use_authorized
                    and manifest.usage_rights.evidence
                ),
                "Droits d’utilisation",
                "Les droits d’utilisation pour ce projet sont explicitement autorisés et tracés.",
                (
                    "Les conditions sont documentées, mais aucune autorisation explicite pour "
                    "ce projet n’est enregistrée."
                    if manifest.license
                    else "Les droits d’utilisation ne sont pas documentés."
                ),
            ),
            _review_check(
                "geometry_scale",
                bool(
                    manifest.qualification.mesh_integrity_verified
                    and manifest.qualification.dimensions_verified
                    and manifest.dimensions_m
                    and manifest.bounding_box_m
                )
                and not _failure_mentions(
                    failures,
                    "qualified dimensions",
                    "bounding box",
                    "source units",
                    "geometry integrity",
                    "viewer representation",
                    "professional qa report",
                    "asset qa evidence",
                ),
                "Géométrie et échelle",
                "Le maillage, les dimensions et l’enveloppe sont contrôlés en mètres.",
                (
                    "La géométrie a pu être observée, mais ses dimensions complètes ou "
                    "son échelle restent à qualifier."
                ),
            ),
            _review_check(
                "pivot_orientation",
                bool(
                    manifest.qualification.pivot_verified
                    and manifest.qualification.orientation_verified
                )
                and not _failure_mentions(
                    failures, "professional qa report", "asset qa evidence", "viewer representation"
                ),
                "Repère d’installation",
                "Le pivot et l’orientation d’installation sont vérifiés.",
                "Le pivot et l’orientation d’installation restent à mesurer.",
            ),
            _review_check(
                "anchors_connectors",
                bool(manifest.anchors and manifest.connectors),
                "Ancrages et interfaces",
                "Les ancrages et connecteurs utilisables sont publiés.",
                "Les ancrages, les connecteurs et leur compatibilité mécanique restent à vérifier.",
                forced_incomplete=_failure_mentions(failures, "anchor", "connector"),
            ),
            _review_check(
                "master_viewer_lineage",
                lineage_declared
                and not _failure_mentions(
                    failures,
                    "master representation",
                    "viewer representation",
                    "runtime hash",
                    "representation lineage",
                ),
                "Lignée CAO vers viewer",
                "Le master neutre et le GLB viewer sont liés par leurs empreintes.",
                "Le master neutre, le GLB viewer ou leur lignée vérifiable reste incomplet.",
            ),
            _review_check(
                "qualification_previews",
                set(verified_views) == expected_views,
                "Vues de qualification",
                "Les cinq vues attendues sont présentes et leurs empreintes sont vérifiées.",
                "Les cinq vues attendues ne sont pas toutes publiées, valides et vérifiées.",
            ),
            _review_check(
                "professional_qa",
                bool(manifest.qa_evidence.status == "passed")
                and not _failure_mentions(failures, "professional qa report", "asset qa evidence"),
                "Contrôle qualité professionnel",
                "Le rapport QA est lié à l’asset, à sa version et à ses représentations.",
                "Le rapport QA professionnel reste absent, incomplet ou incohérent.",
            ),
            _review_check(
                "admission",
                admission.eligible,
                "Admission dans les designs",
                "Ce composant est admis par le gate effectif de génération.",
                "Ce composant ne peut pas encore entrer dans un design.",
            ),
        ]
        blockers = [
            {
                "code": check["check_id"],
                "message": check["detail"],
            }
            for check in checks
            if check["status"] != "passed"
        ]
        actions: list[dict[str, str]] = []
        if manifest.original_url:
            actions.append(
                {
                    "action_id": "open_vendor_source",
                    "kind": "external_source",
                    "label": "Ouvrir la source constructeur",
                    "url": manifest.original_url,
                }
            )
        for preview in previews:
            if preview.get("available") is True and preview.get("qa_status") == "passed":
                actions.append(
                    {
                        "action_id": f"view_verified_preview:{preview['view']}",
                        "kind": "internal_preview",
                        "label": f"Voir la vue vérifiée {preview['view']}",
                        "url": str(preview["url"]),
                    }
                )
        return {
            "status": status,
            "summary": _review_summary(status),
            "checks": checks,
            "blockers": blockers,
            "available_actions": actions,
        }


def claims_professional_identity(manifest: AssetManifest | dict[str, object]) -> bool:
    """Identify manifests whose product claims require professional evidence."""

    payload = (
        manifest.model_dump(mode="json")
        if isinstance(manifest, AssetManifest)
        else manifest
    )
    return _claims_professional_identity(payload)


def preview_image_matches(path: Path, width_px: int, height_px: int) -> bool:
    """Use the worker's image structure check before publishing preview actions."""

    return _inspect_png(path) == (width_px, height_px)


def _review_check(
    check_id: str,
    passed: bool,
    title: str,
    passed_detail: str,
    incomplete_detail: str,
    *,
    forced_incomplete: bool = False,
) -> dict[str, str]:
    passed = passed and not forced_incomplete
    return {
        "check_id": check_id,
        "status": "passed" if passed else "incomplete",
        "title": title,
        "detail": passed_detail if passed else incomplete_detail,
    }


def _failure_mentions(failures: tuple[str, ...], *fragments: str) -> bool:
    normalized = tuple(failure.casefold() for failure in failures)
    return any(fragment in failure for fragment in fragments for failure in normalized)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _review_summary(status: str) -> str:
    return {
        "admitted": "Les preuves requises sont valides pour l’import exact dans un design.",
        "reference_only": "La source peut être examinée, mais elle reste exclue des designs.",
        "evidence_invalid": (
            "Le manifest revendique une qualification que les preuves effectives "
            "ne confirment pas."
        ),
        "blocked": "Les preuves nécessaires à une qualification professionnelle sont incomplètes.",
        "technical_asset": "Composant technique interne sans revendication constructeur.",
    }[status]
