import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { usePatient } from "../../services/auth/session";
import { api, post, ApiError, upload } from "../../services/api/client";
import {
  detailSchema,
  metadataSchema,
  imageSchema,
  statusSchema,
  facilitiesSchema,
  uploadSchema,
  type RecordDetail,
  type Facility,
} from "../../services/api/contracts";
import {
  Button,
  ConfirmDialog,
  FieldError,
  Loading,
  Notice,
  PageHeader,
} from "../../design-system/primitives";
import { partialDate, processingLabel, typeLabel, types } from "./RecordCard";
import { validateFile } from "./Upload";
const formSchema = z
  .object({
    document_type: z.enum([
      "lab_report",
      "referral",
      "consultation_note",
      "prescription",
      "discharge_summary",
      "imaging_report",
      "medical_image",
      "other",
    ]),
    precision: z.enum(["unknown", "year", "month", "day"]),
    year: z.string(),
    month: z.string(),
    day: z.string(),
    facility_name: z.string().max(180),
  })
  .superRefine((value, ctx) => {
    if (value.precision === "unknown") return;
    const year = Number(value.year),
      month = Number(value.month),
      day = Number(value.day);
    if (!/^\d{1,4}$/.test(value.year) || year < 1 || year > 9999)
      ctx.addIssue({
        code: "custom",
        path: ["year"],
        message: "Enter a year from 1 to 9999.",
      });
    if (
      ["month", "day"].includes(value.precision) &&
      (!/^\d{1,2}$/.test(value.month) || month < 1 || month > 12)
    )
      ctx.addIssue({
        code: "custom",
        path: ["month"],
        message: "Enter a month from 1 to 12.",
      });
    const days = new Date(0);
    days.setUTCFullYear(year, month, 0);
    if (
      value.precision === "day" &&
      (!/^\d{1,2}$/.test(value.day) || day < 1 || day > days.getUTCDate())
    )
      ctx.addIssue({
        code: "custom",
        path: ["day"],
        message: "Enter a valid day for this month.",
      });
  });
type ReviewForm = z.infer<typeof formSchema>;
function valuesFor(record: RecordDetail): ReviewForm {
  const values = record.metadata.values;
  const date = values.document_date;
  return {
    document_type: (values.document_type ??
      "other") as ReviewForm["document_type"],
    facility_name: values.facility_name ?? "",
    precision: date?.precision ?? "unknown",
    year: date?.year?.toString() ?? "",
    month: date?.month?.toString() ?? "",
    day: date?.day?.toString() ?? "",
  };
}
function Review({
  record,
  reload,
}: {
  record: RecordDetail;
  reload: () => Promise<RecordDetail | undefined>;
}) {
  const patient = usePatient();
  const client = useQueryClient();
  const [base, setBase] = useState({
    revision: record.metadata.revision,
    version: record.current_version.id,
  });
  const [conflict, setConflict] = useState(false);
  const [saved, setSaved] = useState(false);
  const [proposalId, setProposalId] = useState<string | undefined>();
  const [facilityQuery, setFacilityQuery] = useState("");
  const [location, setLocation] = useState<Facility | null>(null);
  const form = useForm<ReviewForm>({
    resolver: zodResolver(formSchema),
    defaultValues: valuesFor(record),
  });
  const precision = form.watch("precision");
  const status = useQuery({
    queryKey: ["assistant-status"],
    queryFn: ({ signal }) =>
      api(`/api/workspaces/${patient.id}/assistant/status/`, statusSchema, {
        signal,
      }),
  });
  const places = useMutation({
    mutationFn: () =>
      post(
        `/api/workspaces/${patient.id}/facilities/search/`,
        facilitiesSchema,
        { query: facilityQuery },
      ),
  });
  const save = useMutation({
    mutationFn: (values: ReviewForm) =>
      post(
        `/api/workspaces/${patient.id}/records/${record.id}/review/`,
        metadataSchema,
        {
          expected_revision: base.revision,
          source_version_id: base.version,
          proposal_id: proposalId,
          values: {
            document_type: values.document_type,
            facility_name: values.facility_name.trim() || null,
            document_date: {
              precision: values.precision,
              year: values.precision === "unknown" ? null : Number(values.year),
              month: ["month", "day"].includes(values.precision)
                ? Number(values.month)
                : null,
              day: values.precision === "day" ? Number(values.day) : null,
            },
          },
          ...(location ? { facility_selection: location.selection_token } : {}),
        },
      ),
    onSuccess: async () => {
      setSaved(true);
      const latest = await reload();
      if (latest)
        setBase({
          revision: latest.metadata.revision,
          version: latest.current_version.id,
        });
      void client.invalidateQueries({ queryKey: ["records"] });
      void client.invalidateQueries({ queryKey: ["home-records"] });
    },
    onError: (error) => {
      setSaved(false);
      if (error instanceof ApiError && error.status === 409) setConflict(true);
    },
  });
  const error = (key: keyof ReviewForm) => form.formState.errors[key]?.message;
  return (
    <section className="panel stack">
      <h2>Review document details</h2>
      <p>
        Keep uncertain details unknown. Your review confirms these document
        labels, not the medical findings.
      </p>
      {record.proposals.length > 0 && (
        <details>
          <summary>Evidence-backed AI suggestions</summary>
          {record.proposals.map((proposal) => (
            <article key={proposal.id} className="form-section">
              <h3>AI proposal · {proposal.model}</h3>
              <p>
                {typeLabel(proposal.values.document_type)} ·{" "}
                {partialDate(proposal.values.document_date)} ·{" "}
                {proposal.values.facility_name ?? "Facility unknown"}
              </p>
              {Object.entries(proposal.values.evidence).map(
                ([field, evidence]) =>
                  evidence && (
                    <blockquote key={field} className="quote">
                      <p>{evidence.quote}</p>
                      <small>
                        {field.replaceAll("_", " ")} · source page{" "}
                        {evidence.page}
                      </small>
                    </blockquote>
                  ),
              )}
              <Button
                variant="secondary"
                onPress={() => {
                  form.reset({
                    document_type: proposal.values
                      .document_type as ReviewForm["document_type"],
                    facility_name: proposal.values.facility_name ?? "",
                    precision: proposal.values.document_date.precision,
                    year: proposal.values.document_date.year?.toString() ?? "",
                    month:
                      proposal.values.document_date.month?.toString() ?? "",
                    day: proposal.values.document_date.day?.toString() ?? "",
                  });
                  setProposalId(proposal.id);
                  setLocation(null);
                  setSaved(false);
                }}
              >
                Use as a starting point
              </Button>
            </article>
          ))}
        </details>
      )}
      <form
        className="stack"
        onSubmit={form.handleSubmit(
          (values) => {
            setSaved(false);
            save.mutate(values);
          },
          () => {
            setSaved(false);
          },
        )}
      >
        <div className="field">
          <label htmlFor="document-type">Document type</label>
          <select id="document-type" {...form.register("document_type")}>
            {Object.entries(types).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <fieldset>
          <legend>Document date</legend>
          <div className="form-grid">
            <div className="field full-width">
              <label htmlFor="precision">How much of the date is known?</label>
              <select id="precision" {...form.register("precision")}>
                <option value="unknown">Unknown</option>
                <option value="year">Year only</option>
                <option value="month">Month and year</option>
                <option value="day">Exact day</option>
              </select>
            </div>
            {precision !== "unknown" && (
              <div className="field">
                <label htmlFor="year">Year</label>
                <input
                  id="year"
                  inputMode="numeric"
                  {...form.register("year")}
                  aria-invalid={!!error("year")}
                  aria-describedby={error("year") ? "year-error" : undefined}
                />
                <FieldError id="year-error">{error("year")}</FieldError>
              </div>
            )}
            {["month", "day"].includes(precision) && (
              <div className="field">
                <label htmlFor="month">Month (1–12)</label>
                <input
                  id="month"
                  inputMode="numeric"
                  {...form.register("month")}
                  aria-invalid={!!error("month")}
                  aria-describedby={error("month") ? "month-error" : undefined}
                />
                <FieldError id="month-error">{error("month")}</FieldError>
              </div>
            )}
            {precision === "day" && (
              <div className="field">
                <label htmlFor="day">Day</label>
                <input
                  id="day"
                  inputMode="numeric"
                  {...form.register("day")}
                  aria-invalid={!!error("day")}
                  aria-describedby={error("day") ? "day-error" : undefined}
                />
                <FieldError id="day-error">{error("day")}</FieldError>
              </div>
            )}
          </div>
        </fieldset>
        <div className="field">
          <label htmlFor="facility">Issuing facility</label>
          <input
            id="facility"
            {...form.register("facility_name", {
              onChange: () => setLocation(null),
            })}
            aria-invalid={!!error("facility_name")}
            aria-describedby="facility-help"
          />
          <small id="facility-help">
            Leave blank if unknown. A facility name does not grant anyone
            access.
          </small>
          <FieldError id="facility-error">{error("facility_name")}</FieldError>
        </div>
        {status.data?.facility_search_enabled ? (
          <div className="stack">
            <div className="field">
              <label htmlFor="hospital-query">Find the hospital location</label>
              <input
                id="hospital-query"
                value={facilityQuery}
                onChange={(event) => setFacilityQuery(event.target.value)}
                maxLength={160}
              />
            </div>
            <Button
              variant="secondary"
              isDisabled={places.isPending || facilityQuery.trim().length < 3}
              onPress={() => places.mutate()}
            >
              Search hospitals
            </Button>
            {places.isError && (
              <Notice tone="error">{places.error.message}</Notice>
            )}
            {places.data && (
              <>
                <p>{places.data.attribution}</p>
                {places.data.results.length === 0 && (
                  <p>
                    No hospitals found. Try a town or keep the name you entered.
                  </p>
                )}
                {places.data.results.map((place) => (
                  <Button
                    key={place.selection_token}
                    variant="secondary"
                    onPress={() => {
                      setLocation(place);
                      form.setValue("facility_name", place.name, {
                        shouldValidate: true,
                      });
                    }}
                  >
                    {place.name}
                    {place.address ? ` · ${place.address}` : ""}
                  </Button>
                ))}
              </>
            )}
            {location && (
              <Notice>
                Selected location: {location.name}. It will be saved when you
                confirm the document details.
              </Notice>
            )}
          </div>
        ) : (
          <Notice>
            Hospital location lookup is unavailable here. You can enter the
            facility name directly.
          </Notice>
        )}
        {save.isError && (
          <Notice tone="error" live>
            {save.error.message}
          </Notice>
        )}
        {conflict && (
          <Notice tone="warning">
            <p>
              Your entries are retained. Load the current source and details,
              compare them with your entries, then save again.
            </p>
            <Button
              variant="secondary"
              onPress={async () => {
                const latest = await reload();
                if (latest) {
                  setBase({
                    revision: latest.metadata.revision,
                    version: latest.current_version.id,
                  });
                  setProposalId(undefined);
                  setConflict(false);
                  save.reset();
                }
              }}
            >
              Load current details
            </Button>
          </Notice>
        )}
        {saved && (
          <Notice tone="success" live>
            Details reviewed by you. They are not clinician-verified.
          </Notice>
        )}
        <Button type="submit" isDisabled={save.isPending || conflict}>
          {save.isPending ? "Saving details…" : "Confirm document details"}
        </Button>
      </form>
    </section>
  );
}
export default function Detail() {
  const patient = usePatient();
  const { recordId } = useParams();
  const client = useQueryClient();
  const base = `/api/workspaces/${patient.id}/`;
  const query = useQuery({
    queryKey: ["record", recordId],
    queryFn: ({ signal }) =>
      api(base + `records/${recordId}/`, detailSchema, { signal }),
    refetchInterval: (query) =>
      ["queued", "processing", "waiting_model"].includes(
        query.state.data?.jobs[0]?.state ?? "",
      )
        ? 12000
        : false,
    refetchIntervalInBackground: false,
  });
  const record = query.data;
  const image = useQuery({
    queryKey: ["image", record?.current_version.id],
    enabled: !!record?.current_version.image_details_url,
    queryFn: ({ signal }) =>
      api(record!.current_version.image_details_url!, imageSchema, { signal }),
    refetchInterval: (query) =>
      query.state.data?.inspection === null ? 12000 : false,
  });
  const [newFile, setNewFile] = useState<File | null>(null);
  const [versionError, setVersionError] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);
  const retry = useMutation({
    mutationFn: () =>
      post(
        base + `jobs/${record!.jobs[0].id}/retry/`,
        z.object({ id: z.string(), state: z.string() }),
        {},
      ),
    onSuccess: () => query.refetch(),
  });
  async function addVersion() {
    if (!newFile || !record) return;
    const validation = validateFile(newFile);
    if (validation) {
      setVersionError(validation);
      return;
    }
    setVersionError("");
    setProgress(0);
    abort.current = new AbortController();
    try {
      uploadSchema.parse(
        await upload(
          base + `records/${record.id}/versions/`,
          newFile,
          record.current_version.content_kind,
          setProgress,
          abort.current.signal,
        ),
      );
      setNewFile(null);
      await query.refetch();
      void client.invalidateQueries({ queryKey: ["records"] });
    } catch (error) {
      if (!abort.current.signal.aborted)
        setVersionError(
          error instanceof Error
            ? error.message
            : "Version could not be saved.",
        );
    } finally {
      setProgress(null);
    }
  }
  if (query.isPending) return <Loading />;
  if (query.isError || !record)
    return (
      <Notice tone="error" live>
        {query.error?.message ?? "Record unavailable"}
        <p>
          <Link to="../records">Return to records</Link>
        </p>
      </Notice>
    );
  return (
    <>
      <nav aria-label="Breadcrumb" className="breadcrumbs">
        <Link to="../records">Records</Link> / Original and details
      </nav>
      <PageHeader title={record.current_version.original_filename}>
        {processingLabel(record.jobs[0]?.state ?? "")}
      </PageHeader>
      <div className="detail-grid">
        <section className="detail-source">
          <div className="panel stack">
            <h2>Your exact original</h2>
            <a
              className="button button--primary"
              href={record.current_version.download_url}
            >
              Download original · version{" "}
              {record.current_version.version_number}
            </a>
            <dl className="source-info">
              <dt>Format</dt>
              <dd>{record.current_version.media_type}</dd>
              <dt>File size</dt>
              <dd>{(record.current_version.byte_size / 1024).toFixed(1)} KB</dd>
              <dt>Document date</dt>
              <dd>{partialDate(record.metadata.values.document_date)}</dd>
              <dt>Facility</dt>
              <dd>
                {record.metadata.values.facility_name ??
                  "Unknown or not reviewed"}
              </dd>
              <dt>Review</dt>
              <dd>
                {record.metadata.revision
                  ? "Details reviewed by you"
                  : "Details not reviewed"}{" "}
                · not clinician-verified
              </dd>
            </dl>
            {image.data?.preview_url && (
              <>
                <img
                  className="preview-image"
                  src={image.data.preview_url}
                  alt="Technical preview of this uploaded original"
                />
                <Notice tone="warning">
                  This preview is for identifying the file. It is not suitable
                  for clinical interpretation.
                </Notice>
              </>
            )}
            {record.current_version.media_type === "application/dicom" && (
              <Notice>
                DICOM pixels are not rendered here. Download the original for a
                suitable medical viewer.
              </Notice>
            )}
            <details>
              <summary>Source integrity</summary>
              <p>SHA-256</p>
              <p className="quote">{record.current_version.sha256}</p>
            </details>
          </div>
          {["failed", "waiting_model"].includes(record.jobs[0]?.state) &&
            patient.capabilities.includes("upload_source") && (
              <div className="panel stack">
                <p>
                  Your original is saved. You can request another processing
                  attempt.
                </p>
                <Button
                  variant="secondary"
                  isDisabled={retry.isPending}
                  onPress={() => retry.mutate()}
                >
                  Retry reading this file
                </Button>
                {retry.isError && (
                  <Notice tone="error">{retry.error.message}</Notice>
                )}
              </div>
            )}
          <section className="panel stack">
            <h2>Original versions</h2>
            {record.versions.map((version) => (
              <p key={version.id}>
                <a href={version.download_url}>
                  Download version {version.version_number}
                </a>{" "}
                · {version.original_filename}
              </p>
            ))}
            {patient.capabilities.includes("upload_source") && (
              <>
                <label className="field" htmlFor="new-version">
                  Add a corrected original
                  <input
                    id="new-version"
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png,.dcm,.dicom"
                    onChange={(event) =>
                      setNewFile(event.target.files?.[0] ?? null)
                    }
                  />
                </label>
                <ConfirmDialog
                  trigger="Save a new version"
                  title="Keep a corrected original?"
                  confirmLabel="Save new version"
                  disabled={!newFile || progress !== null}
                  onConfirm={() => void addVersion()}
                >
                  <p>
                    {newFile?.name} will become the current original. Earlier
                    versions and existing consultation selections stay
                    unchanged.
                  </p>
                </ConfirmDialog>
                {progress !== null && (
                  <progress
                    max={100}
                    value={progress}
                    aria-label="New version upload progress"
                  />
                )}
                {versionError && <Notice tone="error">{versionError}</Notice>}
              </>
            )}
          </section>
        </section>
        <div className="stack">
          {patient.capabilities.includes("review_metadata") ? (
            <Review
              key={record.id}
              record={record}
              reload={async () => {
                const result = await query.refetch();
                return result.data;
              }}
            />
          ) : (
            <Notice>
              You can read this original, but you do not have permission to
              review its details.
            </Notice>
          )}
          <section className="panel">
            <h2>Document detail history</h2>
            <p>Corrections retain the earlier assertions and their origin.</p>
            {record.metadata_history.length ? (
              <ol className="history-list">
                {record.metadata_history.map((item) => (
                  <li key={item.id}>
                    <strong>{item.field.replaceAll("_", " ")}</strong>
                    <p>
                      {typeof item.value === "object" && item.value !== null
                        ? partialDate(item.value)
                        : (item.value ?? "Unknown")}
                    </p>
                    <small>
                      {item.origin.replaceAll("_", " ")} ·{" "}
                      {new Date(item.created_at).toLocaleString()}
                    </small>
                  </li>
                ))}
              </ol>
            ) : (
              <p>No details have been reviewed yet.</p>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
