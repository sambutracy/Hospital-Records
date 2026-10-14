import { z } from "zod";
import { uuid, dateSchema } from "../../services/api/contracts";
export const concernValues = z.object({
  title: z.string(),
  description: z.string(),
  kind: z.enum(["issue", "investigation", "injury", "condition", "episode"]),
  certainty: z.enum(["unconfirmed", "patient_reported_diagnosis"]),
  onset: dateSchema,
});
export const practitionerValues = z.object({
  name: z.string(),
  specialty: z.string(),
  facility: z.string(),
  notes: z.string(),
});
export const assignmentValues = z.object({
  practitioner_id: uuid,
  concern_id: uuid.nullable(),
  role: z.string(),
  participation: z.enum(["current", "historical"]),
  start_date: dateSchema,
  end_date: dateSchema,
  notes: z.string(),
});
const envelope = z.object({
  id: uuid,
  revision: z.number().int().positive(),
  status: z.enum(["active", "archived"]),
  updated_at: z.string(),
  provenance: z.literal("patient_reported"),
  access_effect: z.literal("none"),
});
export const concernSchema = envelope.extend({ values: concernValues });
export const practitionerSchema = envelope.extend({
  values: practitionerValues,
});
export const assignmentSchema = envelope.extend({ values: assignmentValues });
export const concernList = z.object({ items: z.array(concernSchema) });
export const practitionerList = z.object({
  items: z.array(practitionerSchema),
});
export const assignmentList = z.object({ items: z.array(assignmentSchema) });
export const historySchema = z.object({
  history: z.array(
    z.object({
      revision: z.number(),
      created_at: z.string(),
      snapshot: z.record(z.string(), z.unknown()),
    }),
  ),
});
export const circleSchema = z.object({
  contacts: z.array(
    z.object({
      id: uuid,
      status: z.string(),
      values: z.object({
        full_name: z.string(),
        relationship: z.string(),
        is_next_of_kin: z.boolean(),
        is_emergency_contact: z.boolean(),
      }),
    }),
  ),
});
export type Concern = z.infer<typeof concernSchema>;
export type Practitioner = z.infer<typeof practitionerSchema>;
export type Assignment = z.infer<typeof assignmentSchema>;
export type CareEntry = Concern | Practitioner | Assignment;
export type CareKind = "concerns" | "practitioners" | "assignments";
export const schemas = {
  concerns: concernSchema,
  practitioners: practitionerSchema,
  assignments: assignmentSchema,
};
export const unknownDate = {
  precision: "unknown" as const,
  year: null,
  month: null,
  day: null,
};
