export type Severity = "info" | "warning" | "error" | "critical" | string;

export type StudioEvent = {
  event_id?: string;
  workflow_id?: string;
  event_type: string;
  created_at?: string;
  timestamp?: string;
  payload?: Record<string, unknown>;
};

export type WorkflowStatus = {
  workflow_id: string;
  status: string;
  version_id?: string | null;
  active_version_id?: string | null;
  artifacts: Record<string, string>;
  warnings: Array<Record<string, unknown>>;
  errors: Array<Record<string, unknown>>;
  llm_provider?: string | null;
  llm_fallback_used?: boolean | null;
  rag_context_count?: number | null;
  memory_hits?: number | null;
  memory_context_count?: number | null;
  generation_mode?: string | null;
  blender_available?: boolean | null;
  qa_score?: number | null;
  glb_inspection_summary?: Record<string, unknown> | null;
  geometry_validation_summary?: Record<string, unknown> | null;
  preview_inspection_summary?: Record<string, unknown> | null;
  asset_import_summary?: Record<string, unknown> | null;
  asset_imports?: AssetImportRecord[] | null;
  structural_qa_passed?: boolean | null;
  expected_objects_present?: boolean | null;
  quality_gates?: Array<Record<string, unknown>>;
  download_url?: string | null;
  tower_validation?: Record<string, unknown> | null;
  rf_validation?: Record<string, unknown> | null;
};

export type CreateDesignResponse = {
  workflow_id: string;
  status: string;
};

export type EditDesignResponse = {
  workflow_id: string;
  edit_id: string;
  status: string;
  version_id?: string | null;
  diff_summary?: Record<string, unknown> | null;
  patch?: Record<string, unknown> | null;
  validation_report?: Record<string, unknown> | null;
  artifacts?: Record<string, string> | null;
  generation_mode?: string | null;
  qa_score?: number | null;
  llm_provider?: string | null;
  llm_fallback_used?: boolean | null;
  errors: Array<Record<string, unknown>>;
  warnings: Array<Record<string, unknown>>;
};

export type DesignListItem = {
  workflow_id: string;
  status: string;
  created_at?: string | null;
  qa_score?: number | null;
  generation_mode?: string | null;
};

export type VersionInfo = {
  version_id: string;
  parent_version_id?: string | null;
  created_at: string;
  edit_description?: string | null;
  diff_summary?: Record<string, unknown> | null;
  status?: string | null;
  active: boolean;
  artifact_dir?: string | null;
  artifacts: Record<string, string>;
  qa_score?: number | null;
  generation_mode?: string | null;
};

export type AssetInventoryEntry = {
  asset_id: string;
  type: string;
  file: string;
  file_exists: boolean;
  asset_file_exists: boolean;
  asset_import_mode: string;
  effective_generation_mode: string;
  import_fallback_allowed: boolean;
  source: string;
  license?: string | null;
  attribution_required?: boolean;
  attribution?: string | null;
  original_url?: string | null;
  original_author?: string | null;
  status?: string;
  dimensions_m?: Record<string, number> | null;
  mount_zones?: Array<Record<string, unknown>>;
  warnings: string[];
};

export type AssetInventory = {
  status: string;
  asset_count: number;
  asset_count_by_type: Record<string, number>;
  missing_file_count: number;
  real_glb_asset_count: number;
  import_ready_asset_count: number;
  procedural_fallback_count: number;
  procedural_generation_required: boolean;
  entries: AssetInventoryEntry[];
  missing_files: AssetInventoryEntry[];
};

export type AssetImportRecord = {
  asset_id?: string;
  object_role?: string;
  import_mode?: string;
  effective_generation_mode?: string;
  asset_file_exists?: boolean;
  asset_import_success?: boolean;
  asset_dimensions_checked?: boolean;
  warnings?: string[];
  [key: string]: unknown;
};

export type DocumentPackSummary = {
  pack_id: string;
  status: string;
  document_count: number;
  high_priority_count: number;
  missing_blocking_count: number;
  conflict_count: number;
  can_generate_design: boolean;
  qa_score?: number | null;
  correction_count?: number;
  processing_warning_count?: number;
  tool_status?: Record<string, string>;
};

export type DocumentReference = {
  document_id: string;
  filename: string;
  extension: string;
  category: string;
  relevance_score: number;
  confidence: number;
  reason: string;
  extractability: string;
  priority: string;
  purpose: string;
  used_for_design: boolean;
  why_used_or_ignored: string;
  extraction_status: string;
  processing_tools: string[];
  processing_warnings: string[];
};

export type ExtractedField = {
  field: string;
  value?: unknown;
  status: string;
  confidence: number;
  sources?: Array<Record<string, unknown>>;
  values?: unknown[];
  severity?: string | null;
  resolution?: string | null;
  reason?: string | null;
};

export type DocumentPackBundle = {
  summary?: DocumentPackSummary;
  documents?: DocumentReference[];
  extractions?: ExtractedField[];
  spec?: Record<string, unknown>;
  conflicts?: ExtractedField[];
  missing?: ExtractedField[];
  qa?: Record<string, unknown>;
  processing?: Record<string, unknown>;
  trace?: StudioEvent[];
  events?: StudioEvent[];
  memory?: Record<string, unknown>;
};
