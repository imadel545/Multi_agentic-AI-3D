"""Resolve selections against certified evidence, never against names supplied by a client."""

import hashlib
import json
from pathlib import Path

from core.contracts.scene import SceneSpec
from core.contracts.versioning import SceneVersion
from core.services.adaptation_capabilities import AdaptationCapabilityService


def resolve_targeted_edit(
    version: SceneVersion,
    target: str,
    expected_version_id: str | None,
    service: AdaptationCapabilityService | None,
) -> tuple[set[str], str]:
    # Caller must first obtain this version with get_verified_active_version under
    # the workflow operation lock. Older certificates without proofs cannot target.
    if expected_version_id != version.version_id:
        raise ValueError(
            "Le design a changé. Rechargez la vue et sélectionnez à nouveau le composant."
        )
    if service is None or not version.artifact_dir:
        raise ValueError("Les capacités de modification de cette sélection sont indisponibles.")
    directory = Path(version.artifact_dir)
    try:
        certificate = json.loads((directory / "completion_certificate.json").read_text())
        raw = (directory / "component_proofs.json").read_bytes()
        proofs = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise ValueError("Les preuves certifiées de cette sélection sont indisponibles.") from exc
    certified = [
        item
        for item in certificate.get("artifacts", [])
        if item.get("logical_name") == "component_proofs"
    ]
    if (
        certificate.get("status") != "issued"
        or len(certified) != 1
        or certified[0].get("sha256") != hashlib.sha256(raw).hexdigest()
    ):
        raise ValueError("Les preuves du composant ne sont pas certifiées pour cette version.")
    return resolve_proof_scope(version.scene, proofs, target, service)


def resolve_proof_scope(
    scene: SceneSpec,
    proofs: dict,
    target: str,
    service: AdaptationCapabilityService,
) -> tuple[set[str], str]:
    matches = [
        (component, instance)
        for component in proofs.get("components", [])
        for instance in component.get("instances", [])
        if instance.get("semantic_root") == target
    ]
    # Geometry programs have one group root and currently no per-instance proof.
    # Do not expose an individual-instance edit by rebuilding a repeated program.
    for program in proofs.get("geometry_programs", []):
        program_id = program.get("geometry_program", {}).get("program_id")
        if target == f"program_{program_id}":
            matches.append((program, None))
    if len(matches) != 1:
        raise ValueError("La sélection est inconnue ou ambiguë dans les preuves de cette version.")
    component, instance = matches[0]
    if component.get("qa", {}).get("passed") is not True:
        raise ValueError("La géométrie sélectionnée ne dispose pas de preuves valides.")
    context = ""
    paths: set[str] = set()
    if instance is None:
        program_id = component["geometry_program"]["program_id"]
        indices = [
            i
            for i, program in enumerate(scene.geometry_programs)
            if program.program_id == program_id and program.requested_quantity == 1
        ]
        if len(indices) == 1:
            prefix = f"/geometry_programs/{indices[0]}"
            paths = {
                capability.path
                for capability in service.resolve(scene).capabilities
                if capability.path == prefix or capability.path.startswith(prefix + "/")
            }
            context = f"composant {scene.geometry_programs[indices[0]].semantic_role}"
    elif instance.get("qa", {}).get("passed") is True:
        for index, sector in enumerate(scene.sectors):
            if instance.get("instance_id") != sector.sector_id:
                continue
            prefix = f"/sectors/{index}/"
            if (
                instance.get("object_role") == "antenna"
                and component.get("asset_id") == sector.antenna_asset_id
            ):
                paths = {
                    prefix + field
                    for field in (
                        "install_height_m",
                        "azimuth_deg",
                        "mechanical_tilt_deg",
                        "electrical_tilt_deg",
                        "beamwidth_deg",
                        "include_label",
                        "include_cable",
                    )
                }
                context = f"antenne secteur {index + 1}"
            elif (
                instance.get("object_role") == "radio"
                and component.get("asset_id") == sector.radio_asset_id
            ):
                paths = {
                    prefix + "radio_geometry_profile/" + field
                    for field in ("vertical_offset_m", "radial_inset_m")
                }
                context = f"RRU secteur {index + 1}"
    declared = set(service.resolve(scene).allowed_paths)
    paths &= declared
    if not paths:
        raise ValueError(
            "Ce composant ne dispose pas encore de modification ciblée prise en charge."
        )
    return paths, context
