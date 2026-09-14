from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from core.contracts.assets import AssetManifest
from core.contracts.scene import SceneSpec

if TYPE_CHECKING:
    from core.services.asset_registry import AssetRegistry


@lru_cache(maxsize=1)
def project_geometry_roles() -> frozenset[str]:
    path = Path(__file__).resolve().parents[2] / "assets/capabilities/project_geometry_policy.json"
    policy = json.loads(path.read_text())
    roles = policy["generated_roles"]
    if (
        policy.get("schema_version") != "1.0.0"
        or not roles
        or not all(isinstance(role, str) and role.strip() == role and role for role in roles)
    ):
        raise ValueError("INVALID_PROJECT_GEOMETRY_POLICY")
    return frozenset(roles)


def has_external_geometry_source(manifest: AssetManifest) -> bool:
    """Internal demonstration meshes cannot become library sources by being saved."""
    return manifest.source in {"vendor_supplied", "cc0", "cc_by", "royalty_free"} and (
        manifest.license != "internal_project_generated"
    )


def library_first_scene_violations(
    scene: SceneSpec,
    *,
    registry: AssetRegistry | None = None,
    generated_roles: frozenset[str] = frozenset(),
) -> list[str]:
    """Enforce library priority while allowing explicitly scoped project geometry.

    Legacy V1 adds undeclared equipment. V2 instead separates exact imports
    from declared project geometry, for which retrieval must find no admitted
    reusable source. Standard equipment cannot use this exception.
    """

    if scene.schema_version != "2.0.0":
        return ["scene.schema_version:legacy_component_construction"]
    violations: list[str] = []
    if scene.tower is not None or scene.sectors or scene.accessory_assets:
        violations.append("scene:legacy_physical_components")
    if not scene.geometry_programs:
        violations.append("scene:no_catalog_programs")
    if scene.assembly_plan is not None:
        violations.append("scene.assembly_plan:unverified_catalog_only_execution")
    for program_index, program in enumerate(scene.geometry_programs):
        if not program.nodes:
            violations.append(f"geometry_programs[{program_index}]:empty")
            continue
        if registry is not None and any(node.kind != "exact_asset" for node in program.nodes):
            from core.services.qualified_asset_retriever import QualifiedAssetCandidateRetriever

            candidates = QualifiedAssetCandidateRetriever(
                registry, external_sources_only=True
            ).search({"semantic_role": program.semantic_role})
            if candidates:
                violations.append(f"geometry_programs[{program_index}]:reusable_source_exists")
        for node_index, node in enumerate(program.nodes):
            if node.kind != "exact_asset" and program.semantic_role not in generated_roles:
                violations.append(
                    f"geometry_programs[{program_index}].nodes[{node_index}]:{node.kind}"
                )
            elif node.kind == "exact_asset" and registry is not None:
                try:
                    manifest = registry.get(node.asset_id)
                    admitted = registry.is_generation_admitted(manifest)
                    external = has_external_geometry_source(manifest)
                except (KeyError, LookupError, ValueError):
                    admitted = external = False
                if not admitted or not external:
                    violations.append(f"geometry_programs[{program_index}]:source_not_admitted")
    return violations
