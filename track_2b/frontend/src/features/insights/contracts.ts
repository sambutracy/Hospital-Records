import { z } from "zod";
import { dateSchema, uuid } from "../../services/api/contracts";
const localPath = z
  .string()
  .refine(
    (value) =>
      /^\/(app\/workspaces\/|workspaces\/|api\/workspaces\/)/.test(value) &&
      !/[\\\r\n]/.test(value),
    "Expected a protected local path",
  );
export const timelineItem = z.object({
  id: z.string(),
  kind: z.enum([
    "journal",
    "document",
    "medication",
    "concern",
    "episode",
    "care_relationship",
  ]),
  source_id: uuid,
  workspace_id: uuid,
  title: z.string(),
  description: z.string(),
  occurrence: dateSchema,
  date_meaning: z.string(),
  recorded_at: z.string(),
  provenance: z.enum([
    "patient_reported",
    "uploaded_record",
    "accepted_contribution",
  ]),
  review_status: z.string(),
  visibility: z.literal("private"),
  href: localPath,
  original_url: localPath.nullable(),
  source_version_id: uuid.nullable(),
  concern_id: uuid.nullable(),
  episode_id: uuid.nullable(),
  details: z.array(z.object({ label: z.string(), value: z.string() })),
});
export const timelineSchema = z.object({
  contract_version: z.literal(1),
  items: z.array(timelineItem),
  page: z.number(),
  next_page: z.number().nullable(),
  dated_count: z.number(),
  undated_count: z.number(),
  date_scope: z.enum(["dated", "undated"]),
  generated_at: z.string(),
  medications_included: z.boolean(),
  coverage: z.object({
    current_document_versions_only: z.literal(true),
    drafts_excluded: z.literal(true),
    archived_entries_excluded: z.literal(true),
    concern_links_are_explicit: z.literal(true),
    episode_dates_not_inferred: z.literal(true),
  }),
});
export const observationsSchema = z.object({
  contract_version: z.literal(1),
  from: z.string(),
  to: z.string(),
  concern_id: uuid.nullable(),
  exact_dated_observations: z.number(),
  days_with_observations: z.number(),
  days_in_range: z.number(),
  days_without_entries: z.number(),
  scored_observations: z.number(),
  unscored_observations: z.number(),
  partial_date_observations_excluded: z.number(),
  undated_observations_excluded: z.number(),
  chart_ready: z.boolean(),
  method: z.literal(
    "active_patient_reported_symptom_entries_by_exact_local_date_v1",
  ),
  interpretation: z.string(),
  bins: z.array(
    z.object({
      date: z.string(),
      observations: z.number(),
      scored_observations: z.number(),
      severity_min: z.number().nullable(),
      severity_max: z.number().nullable(),
    }),
  ),
});
export const episodesSchema = z.object({
  episodes: z.array(
    z.object({
      id: uuid,
      title: z.string(),
      source_version_ids: z.array(uuid),
    }),
  ),
});
export type TimelineItem = z.infer<typeof timelineItem>;
export type Observations = z.infer<typeof observationsSchema>;
