from __future__ import annotations

from typing import TYPE_CHECKING

from core.contracts.assets import AssetManifest
from core.contracts.scene import SceneSpec

if TYPE_CHECKING:
    from core.services.asset_registry import AssetRegistry


def has_external_geometry_source(manifest: AssetManifest) -> bool:
    """Internal demonstration meshes cannot become library sources by being saved."""
    return manifest.source in {"vendor_supplied", "cc0", "cc_by", "royalty_free"} and (
        manifest.license != "internal_project_generated"
    )


def catalog_only_scene_violations(
    scene: SceneSpec, *, registry: AssetRegistry | None = None
) -> list[str]:
    """Return physical geometry paths that are not exact admitted asset imports.

    SceneSpec V1 workers add internal tower, foundation and equipment geometry,
    even when one input asset is exact. Catalog-only execution therefore accepts
    only SceneSpec V2 programs whose every node is a hash-pinned exact asset.
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
        for node_index, node in enumerate(program.nodes):
            if node.kind != "exact_asset":
                violations.append(
                    f"geometry_programs[{program_index}].nodes[{node_index}]:{node.kind}"
                )
            elif registry is not None:
                try:
                    manifest = registry.get(node.asset_id)
                    admitted = registry.is_generation_admitted(manifest)
                    external = has_external_geometry_source(manifest)
                except (KeyError, LookupError, ValueError):
                    admitted = external = False
                if not admitted or not external:
                    violations.append(f"geometry_programs[{program_index}]:source_not_admitted")
    return violations
