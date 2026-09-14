import { z } from "zod";
import { UnknownRecord, publicSchema } from "./schemaCore";

export const DocumentPackCapabilitiesSchema = publicSchema(
  UnknownRecord.extend({
    document_pack_status: z.string(),
    supported_upload_format: z.string(),
    supported_extensions: z.array(z.string()).default([]),
    limitations: z.array(z.string()).default([]),
    limits: UnknownRecord.extend({
      max_zip_size_mb: z.number().positive().optional(),
      max_member_size_mb: z.number().positive().optional(),
      max_member_count: z.number().int().positive().optional(),
      max_uncompressed_size_mb: z.number().positive().optional(),
      processing_mode: z.string().optional(),
      execution: z.string().optional()
    }).optional(),
    truth: UnknownRecord.default({}),
    capabilities: z.record(z.string(), UnknownRecord).default({})
  })
);

export const DocumentPackSummarySchema = publicSchema(
  UnknownRecord.extend({
    pack_id: z.string(),
    status: z.string(),
    document_count: z.number().int().nonnegative().default(0)
  })
);
