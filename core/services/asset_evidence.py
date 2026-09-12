from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.contracts.assets import AssetManifest
from core.qa.gltf_integrity import inspect_gltf_integrity
from core.services.professional_asset_worker_gate import (
    claims_professional_identity as _claims_professional_identity,
)
from core.services.professional_asset_worker_gate import (
    professional_evidence_failures,
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


def claims_professional_identity(manifest: AssetManifest | dict[str, object]) -> bool:
    """Identify manifests whose product claims require professional evidence."""

    payload = (
        manifest.model_dump(mode="json")
        if isinstance(manifest, AssetManifest)
        else manifest
    )
    return _claims_professional_identity(payload)
