import { z } from "zod";
import { HttpUrlSchema, UnknownRecord, publicSchema } from "./schemaCore";


export const AssetPreviewSchema = publicSchema(
  UnknownRecord.extend({
    view: z.string(),
    url: z.string(),
    sha256: z.string().regex(/^[a-f0-9]{64}$/).nullish(),
    available: z.boolean().default(true),
    content_type: z.string().nullish(),
    width_px: z.number().int().positive().nullish(),
    height_px: z.number().int().positive().nullish(),
    qa_status: z
      .enum(["not_run", "passed", "failed", "review_required"])
      .default("not_run")
  })
);

export const QualifiedAssetInventoryEntrySchema = publicSchema(
  UnknownRecord.extend({
    asset_id: z.string(),
    type: z.string(),
    family: z.string().nullish(),
    subtype: z.string().nullish(),
    manufacturer: z.string().nullish(),
    reference: z.string().nullish(),
    source: z.string().nullish(),
    source_provenance: z.string().nullish(),
    original_url: HttpUrlSchema.nullish(),
    source_format: z.string().nullish(),
    dimensions_m: UnknownRecord.nullish(),
    license: z.string().nullish(),
    geometry_status: z.string().nullish(),
    asset_import_mode: z.string().optional(),
    generation_eligible: z.boolean().default(false),
    qualification_status: z.string(),
    allowed_generation_modes: z.array(z.string()).default([]),
    qualification_limitations: z.array(z.string()).default([]),
    qualified_file_hash_matches: z.boolean().nullish(),
    preview_set: z.array(AssetPreviewSchema).optional(),
    local_evidence_status: z.enum(["available", "partial", "unavailable", "not_published"]).optional(),
    reference_evidence_available: z.boolean().optional(),
    provenance_url: z.string().nullish(),
    visual_review_status: z
      .enum(["not_requested", "passed_advisory", "review_required", "failed"])
      .nullish(),
    fidelity_status: z
      .enum(["schematic", "technical_generic", "vendor_qualified"])
      .nullish(),
    qualification_version: z.string().nullish(),
    milestone_evidence_eligible: z.boolean().default(false),
    milestone_evidence_failures: z.array(z.string()).default([])
  })
);

export const AssetInventorySchema = publicSchema(
  UnknownRecord.extend({
    status: z.string(),
    asset_count: z.number(),
    missing_file_count: z.number(),
    real_glb_asset_count: z.number(),
    import_qualified_glb_count: z.number().int().nonnegative().default(0),
    generation_eligible_asset_count: z.number().int().nonnegative().default(0),
    professional_evidence_asset_count: z.number().int().nonnegative().default(0),
    professional_evidence_rejected_count: z.number().int().nonnegative().optional(),
    reference_evidence_missing_count: z.number().int().nonnegative().optional(),
    reference_only_asset_count: z.number().int().nonnegative().default(0),
    qualified_integrity_failure_count: z.number().int().nonnegative().default(0),
    entries: z.array(QualifiedAssetInventoryEntrySchema).default([]),
    missing_files: z.array(UnknownRecord).default([])
  })
);

export const AssetLibrarySummarySchema = publicSchema(
  UnknownRecord.extend({
    status: z.string(),
    schema_version: z.string(),
    catalog_available: z.boolean().default(false),
    file_count: z.number().int().nonnegative().optional(),
    unique_content_count: z.number().int().nonnegative().optional(),
    duplicate_file_count: z.number().int().nonnegative().optional(),
    generation_eligible_count: z.number().int().nonnegative().default(0),
    cad_with_reference_preview_count: z.number().int().nonnegative().default(0),
    reference_preview_link_count: z.number().int().nonnegative().default(0),
    claimed_dimension_counts: z.record(z.string(), z.number().int().nonnegative()).optional(),
    extension_counts: z.record(z.string(), z.number().int().nonnegative()).optional(),
    license_status: z.string().optional(),
    dwg_probe_available: z.boolean().optional(),
    limitations: z.array(z.string()).default([])
  })
);

export const AssetLibraryEntrySchema = publicSchema(
  UnknownRecord.extend({
    file_id: z.string(),
    relative_path: z.string(),
    extension: z.string(),
    size_bytes: z.number().int().nonnegative(),
    claimed_dimension: z.string(),
    category: z.string(),
    duplicate_of: z.string().nullish(),
    license_status: z.string(),
    qualification_status: z.string(),
    conversion_status: z.string(),
    generation_eligible: z.boolean().default(false),
    reference_preview_file_ids: z.array(z.string()).default([]),
    related_cad_file_ids: z.array(z.string()).default([]),
    retrieval_score: z.number().optional(),
    retrieval_evidence: publicSchema(
      UnknownRecord.extend({
        method: z.literal("corpus_idf_metadata"),
        matched_terms: z.record(z.string(), z.array(z.string())).default({}),
        query_coverage: z.number().min(0).max(1),
        geometry_verified: z.literal(false)
      })
    ).nullish()
  })
);

export const AssetLibrarySearchSchema = publicSchema(
  UnknownRecord.extend({
    query: z.string(),
    filters: z.record(z.string(), z.unknown()).default({}),
    result_count: z.number().int().nonnegative(),
    results: z.array(AssetLibraryEntrySchema).default([]),
    selection_policy: z.string(),
    generation_eligible: z.boolean().default(false),
    next_action: z.string()
  })
);

export const AssetLibraryProbeSchema = publicSchema(
  UnknownRecord.extend({
    file: AssetLibraryEntrySchema,
    probe_status: z.string(),
    tool: z.string(),
    parser_mode: z.string().nullish(),
    sanitized_non_finite_values: z.number().int().nonnegative().nullish(),
    sanitized_trailing_decimal_values: z.number().int().nonnegative().nullish(),
    dwg_version: z.string().nullish(),
    declared_unit: z.string().nullish(),
    unit_scale_to_meters: z.number().positive().nullish(),
    insunits_code: z.number().int().nullish(),
    display_unit_name: z.string().nullish(),
    unit_metadata_conflict: z.boolean().default(false),
    entity_counts: z.record(z.string(), z.number().int().nonnegative()).default({}),
    contains_acis_3d_solids: z.boolean(),
    contains_mesh_convertible_geometry: z.boolean(),
    conversion_route: z.string(),
    blender_ready: z.boolean(),
    generation_eligible: z.boolean(),
    limitations: z.array(z.string()).default([])
  })
);

export const AssetProvenanceSchema = publicSchema(
  UnknownRecord.extend({
    asset_id: z.string(),
    family: z.string(),
    subtype: z.string().nullish(),
    manufacturer: z.string().nullish(),
    reference: z.string().nullish(),
    source: z.string().nullish(),
    source_provenance: z.string().nullish(),
    original_url: HttpUrlSchema.nullish(),
    source_format: z.string(),
    source_file_sha256: z.string().regex(/^[a-f0-9]{64}$/).nullish(),
    license: z.string().nullish(),
    attribution_required: z.boolean().default(false),
    attribution: z.string().nullish(),
    geometry_status: z.string(),
    geometry_fidelity: z.string().nullish(),
    conversion_method: z.string().nullish(),
    generation_eligible: z.boolean().default(false),
    dimensions_m: UnknownRecord.nullish(),
    bounding_box_m: UnknownRecord.nullish(),
    qualification: publicSchema(
      UnknownRecord.extend({
        status: z.string(),
        allowed_generation_modes: z.array(z.string()).default([]),
        units: z.string().nullish(),
        mesh_integrity_verified: z.boolean().default(false),
        dimensions_verified: z.boolean().default(false),
        pivot_verified: z.boolean().default(false),
        orientation_verified: z.boolean().default(false),
        qualification_method: z.string().nullish(),
        limitations: z.array(z.string()).default([])
      })
    ),
    qualification_version: z.string().nullish(),
    qa: publicSchema(
      UnknownRecord.extend({
        status: z.string(),
        checks: z.array(z.string()).default([]),
        limitations: z.array(z.string()).default([])
      })
    ),
    milestone_evidence_eligible: z.boolean().default(false),
    milestone_evidence_failures: z.array(z.string()).default([]),
    usage_rights: publicSchema(
      UnknownRecord.extend({
        status: z.enum(["unknown", "review_only", "project_authorized"]),
        project_use_authorized: z.boolean(),
        derivative_use_authorized: z.boolean(),
        redistribution_authorized: z.boolean(),
        evidence: z.string().nullish()
      })
    ),
    local_evidence_status: z.enum(["available", "partial", "unavailable", "not_published"]),
    representations: z.array(UnknownRecord).default([]),
    previews: z.array(AssetPreviewSchema).default([]),
    review: publicSchema(
      UnknownRecord.extend({
        status: z.enum([
          "technical_asset",
          "reference_only",
          "blocked",
          "evidence_invalid",
          "admitted"
        ]),
        summary: z.string(),
        checks: z.array(
          publicSchema(
            UnknownRecord.extend({
              check_id: z.string(),
              status: z.enum(["passed", "incomplete"]),
              title: z.string(),
              detail: z.string()
            })
          )
        ).default([]),
        blockers: z.array(
          publicSchema(
            UnknownRecord.extend({
              code: z.string(),
              message: z.string()
            })
          )
        ).default([]),
        available_actions: z.array(z.discriminatedUnion("kind", [
          publicSchema(
            UnknownRecord.extend({
              action_id: z.string(),
              kind: z.literal("internal_preview"),
              label: z.string(),
              url: z.string().startsWith("/")
            })
          ),
          publicSchema(
            UnknownRecord.extend({
              action_id: z.string(),
              kind: z.literal("external_source"),
              label: z.string(),
              url: HttpUrlSchema
            })
          )
        ])).default([])
      })
    )
  })
);

export const ResolvedAdaptationCapabilitySchema = publicSchema(
  UnknownRecord.extend({
    capability_id: z.string(),
    asset_id: z.string().nullish(),
    profile_id: z.string(),
    label: z.string(),
    path: z.string(),
    value_type: z.string(),
    execution_tool: z.string(),
    effect: z.string(),
    description: z.string(),
    unit: z.string().nullish(),
    minimum: z.number().nullish(),
    maximum: z.number().nullish(),
    allowed_values: z.array(z.union([z.string(), z.number(), z.boolean()])).default([]),
    requires_regeneration: z.boolean().default(true)
  })
);

export const SceneAdaptationCapabilitiesSchema = publicSchema(
  UnknownRecord.extend({
    scene_id: z.string(),
    catalog_version: z.string(),
    catalog_hash: z.string(),
    capabilities: z.array(ResolvedAdaptationCapabilitySchema).default([]),
    unsupported_operations: z.array(z.string()).default([]),
    missing_profiles: z.array(z.string()).default([])
  })
);

export const AdaptationCapabilityCatalogSchema = publicSchema(
  UnknownRecord.extend({
    schema_version: z.string(),
    catalog_hash: z.string(),
    profiles: z.array(UnknownRecord).default([])
  })
);
