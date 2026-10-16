import { z } from "zod";
import { dateSchema, uuid } from "../../services/api/contracts";

export const valuesSchema = z.object({
  category: z.enum(["note", "symptom"]),
  description: z.string().min(1).max(2000),
  occurrence: dateSchema,
  time: z.string().nullable(),
  timezone: z.string(),
  fold: z.number().int().nullable(),
  severity: z.number().int().min(0).max(10).nullable(),
  concern_id: uuid.nullable(),
});
export const eventSchema = z.object({
  contract_version: z.literal(1),
  id: uuid,
  revision: z.number().int().positive(),
  status: z.enum(["active", "archived"]),
  created_at: z.string(),
  updated_at: z.string(),
  created_by_id: uuid,
  updated_by_id: uuid,
  provenance: z.literal("patient_reported"),
  visibility: z.literal("private"),
  values: valuesSchema,
  occurred_at: z.string().nullable(),
});
export const listSchema = z.object({
  contract_version: z.literal(1),
  items: z.array(eventSchema),
  next_page: z.number().int().nullable(),
  from: z.string(),
  to: z.string(),
});
export const fieldsSchema = z.object({
  category: z.enum(["note", "symptom"]),
  description: z.string().max(2000),
  precision: z.enum(["unknown", "year", "month", "day"]),
  year: z.string().max(4),
  month: z.string().max(2),
  day: z.string().max(2),
  time: z.string().max(5),
  timezone: z.string().max(64),
  fold: z.string().max(1),
  severity: z.string().max(2),
  concern_id: z.string().max(36),
});
export const draftSchema = z.object({
  contract_version: z.literal(1),
  draft: z
    .object({
      id: uuid,
      revision: z.number().int().positive(),
      event_id: uuid.nullable(),
      base_revision: z.number().int().nonnegative(),
      fields: fieldsSchema,
      updated_at: z.string(),
    })
    .nullable(),
});
const aiEvidenceSchema = z.record(
  z.string(),
  z.object({ quote: z.string(), start: z.number().int(), end: z.number().int(),
    origin: z.enum(["source_extraction", "apertus_quote"]).optional() }),
);
export const journalAIRequestSchema = z.object({
  id: uuid,
  draft_revision: z.number().int().positive(),
  state: z.enum(["queued", "processing", "waiting_model", "completed", "failed"]),
  error_code: z.string().nullable(),
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  model: z.string().nullable(),
  prompt_version: z.string().nullable(),
  latency_seconds: z.number().nullable(),
  queue_wait_seconds: z.number().nullable(),
  inference_seconds: z.number().nullable(),
  validation_seconds: z.number().nullable(),
  stale: z.boolean(),
  expired: z.boolean(),
  review: z.enum(["accepted", "edited", "rejected", "abandoned"]).nullable(),
  proposal: z.object({
    fields: fieldsSchema,
    evidence: aiEvidenceSchema,
    unknown: z.array(z.string()),
    ambiguities: z.array(z.string()),
    schema_version: z.string(),
    model: z.string(),
    generated_at: z.string(),
    expires_at: z.string(),
    review: z.enum(["accepted", "edited", "rejected", "abandoned"]).nullable(),
  }).nullable(),
});
export const journalAIRequestsSchema = z.object({
  requests: z.array(journalAIRequestSchema),
});
export const historySchema = z.object({
  contract_version: z.literal(1),
  truncated: z.boolean(),
  history: z.array(
    z.object({
      revision: z.number(),
      actor_id: uuid,
      recorded_at: z.string(),
      snapshot: z.object({
        description: z.string(),
        category: z.string(),
        status: z.string(),
        occurrence: dateSchema,
        severity: z.number().nullable(),
        timezone_name: z.string(),
      }),
    }),
  ),
});
export type JournalEvent = z.infer<typeof eventSchema>;
export type Draft = NonNullable<z.infer<typeof draftSchema>["draft"]>;
export type Fields = z.infer<typeof fieldsSchema>;
export type EditorState = {
  fields: Fields;
  eventId?: string | null;
  revision?: number;
  recovery?: Draft;
};
export function localDay(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
export function initialFields(
  day: string,
  category: Fields["category"] = "note",
): Fields {
  const [year, month, date] = day.split("-");
  return {
    category,
    description: "",
    precision: "day",
    year,
    month,
    day: date,
    time: "",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    fold: "",
    severity: "",
    concern_id: "",
  };
}
export function editFields(event: JournalEvent): Fields {
  const v = event.values;
  return {
    category: v.category,
    description: v.description,
    precision: v.occurrence.precision,
    year: String(v.occurrence.year ?? ""),
    month: String(v.occurrence.month ?? ""),
    day: String(v.occurrence.day ?? ""),
    time: v.time ?? "",
    timezone: v.timezone,
    fold: v.fold === null ? "" : String(v.fold),
    severity: v.severity === null ? "" : String(v.severity),
    concern_id: v.concern_id ?? "",
  };
}
export function toValues(fields: Fields) {
  const { precision } = fields;
  const year = precision === "unknown" ? null : Number(fields.year);
  const month =
    precision === "month" || precision === "day" ? Number(fields.month) : null;
  const day = precision === "day" ? Number(fields.day) : null;
  if (!fields.description.trim())
    throw new Error("Describe what you would like to record.");
  if (
    year !== null &&
    (!/^\d{1,4}$/.test(fields.year) || year < 1 || year > 9999)
  )
    throw new Error("Enter a valid year.");
  if (
    month !== null &&
    (!/^\d{1,2}$/.test(fields.month) || month < 1 || month > 12)
  )
    throw new Error("Enter a month from 1 to 12.");
  if (day !== null) {
    const check = new Date(0);
    check.setUTCFullYear(year!, month! - 1, day);
    if (
      !/^\d{1,2}$/.test(fields.day) ||
      day < 1 ||
      check.getUTCDate() !== day ||
      check.getUTCMonth() !== month! - 1
    )
      throw new Error("Enter a valid calendar date.");
  }
  if (fields.time && precision !== "day")
    throw new Error(
      "A time needs a complete date. Clear the time or choose an exact day.",
    );
  if (
    fields.category === "symptom" &&
    fields.severity !== "" &&
    (!/^\d{1,2}$/.test(fields.severity) || Number(fields.severity) > 10)
  )
    throw new Error("Use a severity from 0 to 10, or leave it blank.");
  return valuesSchema.parse({
    category: fields.category,
    description: fields.description.trim(),
    occurrence: { precision, year, month, day },
    time: fields.time || null,
    timezone: fields.timezone,
    fold: fields.time && fields.fold !== "" ? Number(fields.fold) : null,
    severity:
      fields.category === "symptom" && fields.severity !== ""
        ? Number(fields.severity)
        : null,
    concern_id: fields.concern_id || null,
  });
}
export function dateLabel(parts: z.infer<typeof dateSchema>) {
  if (parts.precision === "unknown") return "Date unknown";
  if (parts.precision === "year") return `${parts.year} · year only`;
  const month = new Intl.DateTimeFormat(undefined, {
    month: "long",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(2000, parts.month! - 1, 1)));
  return parts.precision === "month"
    ? `${month} ${parts.year} · month only`
    : `${parts.day} ${month} ${parts.year}`;
}
