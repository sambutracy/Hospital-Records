import { z } from "zod";
import { dateSchema, uuid } from "../../services/api/contracts";
const local = z
  .string()
  .refine(
    (value) =>
      /^\/(app\/workspaces\/|api\/workspaces\/|workspaces\/)/.test(value) &&
      !/[\\\r\n]/.test(value),
  );
const source = z.object({
  kind: z.string(),
  source_id: uuid,
  revision: z.number().int(),
  provenance: z.enum(["patient_reported", "document_sourced"]),
  occurrence: dateSchema,
  date_meaning: z.string(),
  href: local,
  truncated: z.boolean(),
  use_status: z.string().optional(),
});
const item = z.object({
  text: z.string(),
  category: z.enum([
    "source_excerpt",
    "documented_followup",
    "question_to_ask",
    "ambiguous_instruction",
  ]),
  citations: z.array(
    z.object({
      evidence_id: z.string(),
      quote: z.string(),
      start: z.number().int(),
      end: z.number().int(),
      snapshot_sha256: z.string(),
    }),
  ),
  source,
  patient_edited: z.boolean().optional(),
});
export const taskSchema = z.object({
  id: uuid,
  kind: z.enum(["history_exploration", "followup_actions"]),
  state: z.enum([
    "queued",
    "processing",
    "waiting_model",
    "completed",
    "failed",
  ]),
  error_code: z.string().nullable(),
  packet_revision_id: uuid.nullable(),
  model: z.string().nullable(),
  created_at: z.string(),
  coverage: z.object({
    selected_count: z.number(),
    truncated_sources: z.number(),
    scope: z.string(),
  }),
  result: z
    .object({
      items: z.array(item),
      limitations: z.array(z.string()),
      abstained: z.boolean(),
      status: z.literal("private_unconfirmed"),
    })
    .nullable(),
  latency_seconds: z.number().nullable(),
  queue_wait_seconds: z.number().nullable(),
  usage: z.object({ inference_seconds: z.number().optional() }),
  review: z
    .object({
      outcome: z.enum(["kept", "edited", "rejected"]),
      planning_draft: z.array(item).nullable(),
    })
    .nullable(),
});
export const statusSchema = z.object({
  enabled: z.boolean(),
  selection_limit: z.number().int(),
});
export const tasksSchema = z.object({ tasks: z.array(taskSchema) });
export const candidatesSchema = z.object({
  items: z.array(
    z.object({
      kind: z.enum(["journal", "document", "medication", "concern", "episode"]),
      id: uuid,
      revision: z.number().int(),
      title: z.string(),
      occurrence: dateSchema,
      provenance: z.string(),
    }),
  ),
  browse_capped: z.boolean(),
  limit_per_type: z.number(),
  selection_limit: z.number(),
  coverage: z.string(),
});
export type Candidate = z.infer<typeof candidatesSchema>["items"][number];
