import type { ComponentProofs } from "../../api/schemas";

const sectorMechanicalRoles = new Set(["antenna", "mount_bracket", "radio", "rru"]);

/**
 * Derive a local camera subject from published component-proof identities.
 *
 * A cable route can run from a radio to the base of the tower. It remains
 * selectable and editable, but including its full length in the camera bounds
 * makes the local sector unreadable. The proof's instance_id is the stable
 * association; names are never parsed to guess a sector.
 */
export function sectorMechanicalFocusRoots(
  componentProofs: ComponentProofs | null,
  selectedSemanticRoot: string | null
): string[] {
  if (!componentProofs || !selectedSemanticRoot) {
    return [];
  }
  const instances = componentProofs.components.flatMap((component) => component.instances);
  const selected = instances.find((instance) => instance.semantic_root === selectedSemanticRoot);
  if (!selected) {
    return [];
  }
  return Array.from(
    new Set(
      instances
        .filter(
          (instance) =>
            instance.instance_id === selected.instance_id &&
            sectorMechanicalRoles.has(instance.object_role.toLowerCase())
        )
        .map((instance) => instance.semantic_root)
    )
  ).sort();
}
