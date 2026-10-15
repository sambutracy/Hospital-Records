import { z } from "zod";
export const uuid = z.string().uuid();
export const contextSchema = z.object({
  id: uuid,
  workspace_id: uuid,
  kind: z.literal("patient"),
  label: z.string(),
  patient_display_name: z.string(),
  capacity: z.string(),
  capabilities: z.array(z.string()),
});
export const sessionSchema = z.object({
  contract_version: z.literal(1),
  actor: z.object({ id: uuid, display_name: z.string() }),
  contexts: z.array(contextSchema),
  default_context_id: uuid.nullable(),
  expires_at: z.number(),
  csrf_token: z.string(),
  supported_context_kinds: z.array(z.string()),
});
export type Session = z.infer<typeof sessionSchema>;
export type ActingContext = z.infer<typeof contextSchema>;
export const dateSchema = z.object({
  precision: z.enum(["unknown", "year", "month", "day"]),
  year: z.number().nullable(),
  month: z.number().nullable(),
  day: z.number().nullable(),
});
const privateUrl = z
  .string()
  .refine(
    (value) => value.startsWith("/api/") && !value.startsWith("//"),
    "Expected a same-origin protected API path",
  );
export const versionSchema = z.object({
  id: uuid,
  record_id: uuid,
  version_number: z.number(),
  original_filename: z.string(),
  media_type: z.string(),
  byte_size: z.number(),
  sha256: z.string(),
  uploaded_at: z.string(),
  content_kind: z.string(),
  supersedes_id: uuid.nullable(),
  download_url: privateUrl,
  image_details_url: privateUrl.nullable(),
});
export const metadataSchema = z.object({
  revision: z.number(),
  values: z.object({
    document_type: z.string().nullable(),
    document_date: dateSchema.nullable(),
    facility_name: z.string().nullable(),
  }),
  facility_maps_url: z.string().nullable(),
  verification: z.string(),
});
const jobSchema = z.object({
  id: uuid,
  source_version_id: uuid,
  attempt_number: z.number(),
  state: z.string(),
  error_code: z.string(),
});
export const recordSchema = z.object({
  id: uuid,
  current_version: versionSchema,
  metadata: metadataSchema,
  jobs: z.array(jobSchema),
});
export const recordsSchema = z.object({
  records: z.array(recordSchema),
  offset: z.number(),
  limit: z.number(),
  total: z.number(),
  has_more: z.boolean(),
  order: z.string(),
});
export const proposalSchema = z.object({
  id: uuid,
  values: z.object({
    document_type: z.string(),
    document_date: dateSchema,
    facility_name: z.string().nullable(),
    evidence: z.record(
      z.string(),
      z.object({ page: z.number(), quote: z.string() }).nullable(),
    ),
  }),
  model: z.string(),
  prompt_version: z.string(),
});
export const detailSchema = recordSchema.extend({
  versions: z.array(versionSchema),
  proposals: z.array(proposalSchema),
  metadata_history: z.array(
    z.object({
      id: uuid,
      field: z.string(),
      value: z.union([z.string(), dateSchema, z.null()]),
      origin: z.string(),
      review_state: z.string(),
      created_at: z.string(),
    }),
  ),
});
export type RecordItem = z.infer<typeof recordSchema>;
export type RecordDetail = z.infer<typeof detailSchema>;
export type SourceVersion = z.infer<typeof versionSchema>;
export type PartialDate = z.infer<typeof dateSchema>;
export const uploadSchema = z.object({
  created: z.boolean(),
  version: versionSchema,
});
export const statusSchema = z.object({
  configured: z.boolean(),
  model: z.string().nullable(),
  facility_search_enabled: z.boolean(),
  text_only: z.boolean().optional(),
});
export const imageSchema = z.object({
  preview_url: privateUrl.nullable().optional(),
  inspection: z.null().optional(),
  state: z.string().optional(),
});
export const facilitySchema = z.object({
  name: z.string(),
  address: z.string().optional(),
  selection_token: z.string(),
  maps_url: z.string().url(),
});
export const facilitiesSchema = z.object({
  results: z.array(facilitySchema),
  attribution: z.string(),
});
export type Facility = z.infer<typeof facilitySchema>;
export const packetSchema = z.object({
  id: uuid,
  purpose: z.string(),
  revision_id: uuid,
  approved_at: z.string(),
  items: z.array(
    z.object({
      source_version: versionSchema,
      metadata: z.object({
        document_type: z.string().nullable(),
        document_date: dateSchema.nullable(),
        facility_name: z.string().nullable(),
      }),
    }),
  ),
  access: z.string(),
});
export const packetsSchema = z.object({
  packets: z.array(
    z.object({ id: uuid, purpose: z.string(), created_at: z.string() }),
  ),
});
const citationSchema = z
  .object({
    quote: z.string(),
    source_version_id: uuid.optional(),
    download_url: privateUrl.optional(),
    page: z.number().optional(),
    locator: z.unknown().optional(),
  })
  .passthrough();
export const taskSchema = z.object({
  packet_id: uuid.nullable(),
  id: uuid,
  kind: z.string(),
  state: z.string(),
  error_code: z.string(),
  coverage: z.record(z.string(), z.unknown()),
  result: z
    .object({
      abstained: z.boolean().optional(),
      representation: z.enum(["source_excerpts"]).optional(),
      evidence_coverage: z
        .object({
          selected_sources: z.number().int().nonnegative(),
          model_context_sources: z.number().int().nonnegative(),
          cited_sources: z.number().int().nonnegative(),
        })
        .optional(),
      matches: z
        .array(
          z.object({
            record_id: uuid.optional(),
            source_version_id: uuid.optional(),
            reason: z.string(),
            citations: z.array(citationSchema),
          }),
        )
        .optional(),
      items: z
        .array(
          z.object({ text: z.string(), citations: z.array(citationSchema) }),
        )
        .optional(),
      definition: z.string().optional(),
    })
    .nullable(),
  sources: z.array(
    z.object({
      record_id: uuid,
      source_version_id: uuid,
      original_filename: z.string(),
      current_version: z.boolean(),
      metadata_changed_since_request: z.boolean(),
    }),
  ),
});
export type AssistantTask = z.infer<typeof taskSchema>;
export const tasksSchema = z.object({ tasks: z.array(taskSchema) });
