import { useEffect, useRef, useState } from "react";
import { useForm, type UseFormReturn } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { usePatient } from "../../services/auth/session";
import { post, ApiError } from "../../services/api/client";
import { Button, ConfirmDialog, Notice } from "../../design-system/primitives";
import {
  TextField,
  SelectField,
  TextAreaField,
} from "../../design-system/fields";
import {
  schemas,
  type CareKind,
  type CareEntry,
  type Concern,
  type Practitioner,
} from "./contracts";
const dateForm = z
  .object({
    precision: z.enum(["unknown", "year", "month", "day"]),
    year: z.string(),
    month: z.string(),
    day: z.string(),
  })
  .superRefine((v, ctx) => {
    if (v.precision === "unknown") return;
    const y = Number(v.year),
      m = Number(v.month),
      d = Number(v.day);
    if (!/^\d{1,4}$/.test(v.year) || y < 1 || y > 9999)
      ctx.addIssue({
        code: "custom",
        path: ["year"],
        message: "Enter a year from 1 to 9999.",
      });
    if (
      v.precision !== "year" &&
      (!/^\d{1,2}$/.test(v.month) || m < 1 || m > 12)
    )
      ctx.addIssue({
        code: "custom",
        path: ["month"],
        message: "Enter a month from 1 to 12.",
      });
    if (v.precision === "day") {
      const calendar = new Date(0);
      calendar.setUTCFullYear(y, m - 1, d);
      calendar.setUTCHours(0, 0, 0, 0);
      if (
        !/^\d{1,2}$/.test(v.day) ||
        d < 1 ||
        calendar.getUTCFullYear() !== y ||
        calendar.getUTCMonth() !== m - 1 ||
        calendar.getUTCDate() !== d
      )
        ctx.addIssue({
          code: "custom",
          path: ["day"],
          message: "Enter a valid calendar day.",
        });
    }
  });
export const careFormSchema = (kind: CareKind) =>
  z
    .object({
      title: z.string().trim().max(180),
      description: z.string().max(1000),
      kind: z.enum([
        "issue",
        "investigation",
        "injury",
        "condition",
        "episode",
      ]),
      certainty: z.enum(["unconfirmed", "patient_reported_diagnosis"]),
      name: z.string().trim().max(160),
      specialty: z.string().max(120),
      facility: z.string().max(180),
      notes: z.string().max(500),
      practitioner_id: z.string(),
      concern_id: z.string(),
      role: z.string().trim().max(120),
      participation: z.enum(["current", "historical"]),
      onset: dateForm,
      start_date: dateForm,
      end_date: dateForm,
    })
    .superRefine((v, ctx) => {
      const field =
        kind === "concerns"
          ? "title"
          : kind === "practitioners"
            ? "name"
            : "role";
      if (!v[field].trim())
        ctx.addIssue({
          code: "custom",
          path: [field],
          message: "Enter a name or role.",
        });
      if (
        kind === "assignments" &&
        !z.string().uuid().safeParse(v.practitioner_id).success
      )
        ctx.addIssue({
          code: "custom",
          path: ["practitioner_id"],
          message: "Choose a saved doctor.",
        });
      if (
        kind === "assignments" &&
        v.concern_id &&
        !z.string().uuid().safeParse(v.concern_id).success
      )
        ctx.addIssue({
          code: "custom",
          path: ["concern_id"],
          message: "Choose a saved concern.",
        });
      if (
        kind === "assignments" &&
        v.start_date.precision !== "unknown" &&
        v.end_date.precision !== "unknown"
      ) {
        const from =
          Number(v.start_date.year) * 10000 +
          (Number(v.start_date.month) || 1) * 100 +
          (Number(v.start_date.day) || 1);
        const to =
          Number(v.end_date.year) * 10000 +
          (Number(v.end_date.month) || 12) * 100 +
          (Number(v.end_date.day) || 31);
        if (from > to)
          ctx.addIssue({
            code: "custom",
            path: ["end_date", "year"],
            message: "The end cannot be before the start.",
          });
      }
    });
type Values = z.infer<ReturnType<typeof careFormSchema>>;
const blankDate = {
  precision: "unknown" as const,
  year: "",
  month: "",
  day: "",
};
const defaults: Values = {
  title: "",
  description: "",
  kind: "issue",
  certainty: "unconfirmed",
  name: "",
  specialty: "",
  facility: "",
  notes: "",
  practitioner_id: "",
  concern_id: "",
  role: "Doctor",
  participation: "historical",
  onset: blankDate,
  start_date: blankDate,
  end_date: blankDate,
};
function dateInput(value: unknown) {
  const date = value as {
    precision: typeof blankDate.precision;
    year: number | null;
    month: number | null;
    day: number | null;
  };
  return {
    precision: date.precision,
    year: date.year?.toString() ?? "",
    month: date.month?.toString() ?? "",
    day: date.day?.toString() ?? "",
  };
}
function initial(entry?: CareEntry, doctorId?: string): Values {
  const result = { ...defaults, practitioner_id: doctorId ?? "" };
  if (!entry) return result;
  Object.assign(result, entry.values);
  for (const field of ["onset", "start_date", "end_date"] as const)
    if (field in entry.values)
      result[field] = dateInput(
        (entry.values as Record<string, unknown>)[field],
      );
  result.concern_id = result.concern_id ?? "";
  return result;
}
function dateOutput(value: Values["onset"]) {
  return {
    precision: value.precision,
    year: value.precision === "unknown" ? null : Number(value.year),
    month: ["month", "day"].includes(value.precision)
      ? Number(value.month)
      : null,
    day: value.precision === "day" ? Number(value.day) : null,
  };
}
function PartialDateFields({
  name,
  label,
  form,
}: {
  name: "onset" | "start_date" | "end_date";
  label: string;
  form: UseFormReturn<Values>;
}) {
  const precision = form.watch(`${name}.precision`);
  const errors = form.formState.errors[name];
  return (
    <fieldset className="care-date">
      <legend>{label}</legend>
      <div className="form-grid">
        <SelectField
          id={`${name}-precision`}
          label="Date detail"
          options={[
            { value: "unknown", label: "Unknown" },
            { value: "year", label: "Year only" },
            { value: "month", label: "Month and year" },
            { value: "day", label: "Full date" },
          ]}
          selectProps={form.register(`${name}.precision`)}
        />
        {precision !== "unknown" && (
          <TextField
            id={`${name}-year`}
            label="Year"
            error={errors?.year?.message}
            inputProps={{
              ...form.register(`${name}.year`),
              inputMode: "numeric",
              maxLength: 4,
            }}
          />
        )}
        {["month", "day"].includes(precision) && (
          <TextField
            id={`${name}-month`}
            label="Month (1–12)"
            error={errors?.month?.message}
            inputProps={{
              ...form.register(`${name}.month`),
              inputMode: "numeric",
              maxLength: 2,
            }}
          />
        )}
        {precision === "day" && (
          <TextField
            id={`${name}-day`}
            label="Day"
            error={errors?.day?.message}
            inputProps={{
              ...form.register(`${name}.day`),
              inputMode: "numeric",
              maxLength: 2,
            }}
          />
        )}
      </div>
    </fieldset>
  );
}
export default function CareEditor({
  kind,
  entry,
  doctorId,
  concerns,
  practitioners,
  onClose,
  onSaved,
  onReload,
}: {
  kind: CareKind;
  entry?: CareEntry;
  doctorId?: string;
  concerns: Concern[];
  practitioners: Practitioner[];
  onClose: () => void;
  onSaved: () => void;
  onReload: () => Promise<void>;
}) {
  const patient = usePatient();
  const cache = useQueryClient();
  const heading = useRef<HTMLHeadingElement>(null);
  const [savedDraft] = useState(() =>
    cache.getQueryData<Values>(["care", "draft", "values"]),
  );
  const form = useForm<Values>({
    resolver: zodResolver(careFormSchema(kind)),
    defaultValues: savedDraft ?? initial(entry, doctorId),
  });
  const {
    register,
    formState: { errors, isDirty: changed },
    handleSubmit,
  } = form;
  const isDirty = changed || !!savedDraft;
  useEffect(() => {
    heading.current?.focus({ preventScroll: false });
  }, []);
  useEffect(() => {
    const subscription = form.watch(() =>
      cache.setQueryData(["care", "draft", "values"], form.getValues()),
    );
    return () => subscription.unsubscribe();
  }, [form, cache]);
  useEffect(() => {
    if (!isDirty) return;
    const before = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const link = (event: MouseEvent) => {
      const anchor = (event.target as Element).closest?.("a[href]");
      if (anchor) {
        if (!window.confirm("Leave without saving these care details?")) {
          event.preventDefault();
          event.stopPropagation();
        } else {
          cache.removeQueries({ queryKey: ["care", "draft"] });
        }
      }
    };
    window.addEventListener("beforeunload", before);
    document.addEventListener("click", link, true);
    return () => {
      window.removeEventListener("beforeunload", before);
      document.removeEventListener("click", link, true);
    };
  }, [isDirty, cache]);
  const save = useMutation({
    mutationFn: (values: Values) => {
      const payload =
        kind === "concerns"
          ? {
              title: values.title,
              description: values.description,
              kind: values.kind,
              certainty: values.certainty,
              onset: dateOutput(values.onset),
            }
          : kind === "practitioners"
            ? {
                name: values.name,
                specialty: values.specialty,
                facility: values.facility,
                notes: values.notes,
              }
            : {
                practitioner_id: values.practitioner_id,
                concern_id: values.concern_id || null,
                role: values.role,
                participation: values.participation,
                start_date: dateOutput(values.start_date),
                end_date: dateOutput(values.end_date),
                notes: values.notes,
              };
      return post(
        `/api/workspaces/${patient.id}/care/${kind}/${entry ? `${entry.id}/` : ""}`,
        schemas[kind] as z.ZodType<CareEntry>,
        { values: payload, expected_revision: entry?.revision ?? 0 },
      );
    },
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ["care"] });
      onSaved();
    },
  });
  const conflict = save.error instanceof ApiError && save.error.status === 409;
  const field = (
    name:
      | "title"
      | "description"
      | "name"
      | "specialty"
      | "facility"
      | "notes"
      | "role",
    label: string,
    maxLength: number,
  ) =>
    name === "description" || name === "notes" ? (
      <TextAreaField
        id={`care-${name}`}
        label={label}
        error={errors[name]?.message}
        inputProps={{ ...register(name), maxLength }}
      />
    ) : (
      <TextField
        id={`care-${name}`}
        label={label}
        error={errors[name]?.message}
        inputProps={{ ...register(name), maxLength }}
      />
    );
  return (
    <section className="panel form-section" aria-labelledby="care-editor-title">
      <h2 id="care-editor-title" tabIndex={-1} ref={heading}>
        {entry ? "Edit" : kind === "assignments" ? "Link" : "Add"}{" "}
        {kind === "concerns"
          ? "health concern"
          : kind === "practitioners"
            ? "doctor"
            : "care relationship"}
      </h2>
      <p className="form-section">
        Saved as your report. This does not verify a diagnosis, a doctor’s
        identity, or permission to view your records.
      </p>
      <form onSubmit={handleSubmit((v) => save.mutate(v))} className="stack">
        <fieldset disabled={save.isPending} className="care-fields">
          <div className="form-grid">
            {kind === "concerns" ? (
              <>
                {field("title", "Concern name", 180)}
                <SelectField
                  id="concern-kind"
                  label="Type of concern"
                  options={[
                    { value: "issue", label: "Health issue" },
                    { value: "investigation", label: "Investigation" },
                    { value: "injury", label: "Injury" },
                    { value: "condition", label: "Condition" },
                    { value: "episode", label: "Care episode" },
                  ]}
                  selectProps={register("kind")}
                />
                <SelectField
                  id="concern-certainty"
                  label="What is known?"
                  help="A reported diagnosis remains patient-reported; Comfort does not clinically verify it."
                  options={[
                    {
                      value: "unconfirmed",
                      label: "Unconfirmed / still investigating",
                    },
                    {
                      value: "patient_reported_diagnosis",
                      label: "I have been told a diagnosis",
                    },
                  ]}
                  selectProps={register("certainty")}
                />
                {field(
                  "description",
                  "Description in your words (optional)",
                  1000,
                )}
              </>
            ) : kind === "practitioners" ? (
              <>
                {field("name", "Doctor’s name", 160)}
                {field("specialty", "Specialty (optional)", 120)}
                {field("facility", "Facility (optional)", 180)}
                {field("notes", "Notes (optional)", 500)}
              </>
            ) : (
              <>
                <SelectField
                  id="assignment-doctor"
                  label="Doctor"
                  error={errors.practitioner_id?.message}
                  options={[
                    { value: "", label: "Choose a doctor" },
                    ...practitioners
                      .filter((p) => p.status === "active")
                      .map((p) => ({ value: p.id, label: p.values.name })),
                  ]}
                  selectProps={register("practitioner_id")}
                />
                <SelectField
                  id="assignment-concern"
                  label="Health concern"
                  error={errors.concern_id?.message}
                  options={[
                    { value: "", label: "General care / no specific concern" },
                    ...concerns
                      .filter((c) => c.status === "active")
                      .map((c) => ({ value: c.id, label: c.values.title })),
                  ]}
                  selectProps={register("concern_id")}
                />
                {field("role", "Role in your care", 120)}
                <SelectField
                  id="assignment-participation"
                  label="Participation"
                  options={[
                    { value: "historical", label: "Historical" },
                    { value: "current", label: "Current" },
                  ]}
                  selectProps={register("participation")}
                />
                {field("notes", "Relationship notes (optional)", 500)}
              </>
            )}
          </div>
          {kind === "concerns" && (
            <PartialDateFields
              name="onset"
              label="When it began (optional)"
              form={form}
            />
          )}
          {kind === "assignments" && (
            <>
              <PartialDateFields
                name="start_date"
                label="Care started (optional)"
                form={form}
              />
              <PartialDateFields
                name="end_date"
                label="Care ended (optional)"
                form={form}
              />
            </>
          )}
        </fieldset>
        {save.isError && (
          <Notice tone="error" live>
            {save.error.message}
            {conflict &&
              " Your entries are still here. Reloading discards this unsaved draft."}
          </Notice>
        )}
        {conflict && (
          <ConfirmDialog
            trigger="Reload latest details"
            title="Discard draft and reload?"
            confirmLabel="Reload"
            onConfirm={() => {
              void onReload();
            }}
          >
            <p>Check the saved revision before entering your changes again.</p>
          </ConfirmDialog>
        )}
        <div className="actions">
          <Button type="submit" isDisabled={save.isPending || conflict}>
            {save.isPending ? "Saving…" : "Save care details"}
          </Button>
          {isDirty ? (
            <ConfirmDialog
              trigger="Cancel editing"
              title="Discard unsaved details?"
              confirmLabel="Discard draft"
              disabled={save.isPending}
              onConfirm={onClose}
            >
              <p>Your saved care information will stay as it is.</p>
            </ConfirmDialog>
          ) : (
            <Button
              variant="secondary"
              isDisabled={save.isPending}
              onPress={onClose}
            >
              Cancel editing
            </Button>
          )}
        </div>
      </form>
    </section>
  );
}
