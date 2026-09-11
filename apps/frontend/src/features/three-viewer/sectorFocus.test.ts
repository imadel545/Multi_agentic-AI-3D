import { describe, expect, it } from "vitest";
import { ComponentProofsSchema } from "../../api/schemas";
import { sectorMechanicalFocusRoots } from "./sectorFocus";

const componentProofs = ComponentProofsSchema.parse({
  schema_version: "1.0.0",
  workflow_id: "wf_focus",
  components: [
    {
      component_id: "antennas",
      role_id: "sector_antenna",
      origin: "catalog",
      strategy: "reuse",
      generation_strategy: "imported_glb_exact",
      quantity: 2,
      instances: [
        {
          instance_id: "S1",
          object_role: "antenna",
          semantic_root: "antenna_S1",
          geometry_source: "imported_glb_exact",
          qa: null
        },
        {
          instance_id: "S2",
          object_role: "antenna",
          semantic_root: "antenna_S2",
          geometry_source: "imported_glb_exact",
          qa: null
        }
      ],
      qa: null
    },
    {
      component_id: "mounts",
      role_id: "antenna_mount",
      origin: "builder",
      strategy: "compose",
      generation_strategy: "procedural",
      quantity: 2,
      instances: [
        {
          instance_id: "S2",
          object_role: "mount_bracket",
          semantic_root: "mount_S2",
          geometry_source: "builder",
          qa: null
        }
      ],
      qa: null
    },
    {
      component_id: "radios",
      role_id: "remote_radio",
      origin: "builder",
      strategy: "compose",
      generation_strategy: "procedural",
      quantity: 2,
      instances: [
        {
          instance_id: "S2",
          object_role: "radio",
          semantic_root: "radio_S2",
          geometry_source: "builder",
          qa: null
        }
      ],
      qa: null
    },
    {
      component_id: "cables",
      role_id: "sector_cable_route",
      origin: "builder",
      strategy: "compose",
      generation_strategy: "procedural",
      quantity: 2,
      instances: [
        {
          instance_id: "S2",
          object_role: "cable",
          semantic_root: "cable_S2_to_base",
          geometry_source: "builder",
          qa: null
        }
      ],
      qa: null
    }
  ],
  geometry_programs: []
});

describe("sectorMechanicalFocusRoots", () => {
  it("frames the proven local subassembly for either a panel or its cable route", () => {
    const expected = ["antenna_S2", "mount_S2", "radio_S2"];

    expect(sectorMechanicalFocusRoots(componentProofs, "antenna_S2")).toEqual(expected);
    expect(sectorMechanicalFocusRoots(componentProofs, "cable_S2_to_base")).toEqual(expected);
  });

  it("does not infer a sector from an unproven or legacy root name", () => {
    expect(sectorMechanicalFocusRoots(componentProofs, "antenna_S9")).toEqual([]);
    expect(sectorMechanicalFocusRoots(null, "antenna_S2")).toEqual([]);
  });
});
