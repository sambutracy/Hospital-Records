import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  Files,
  Heart,
  CalendarDays,
  Users,
  Pill,
  RefreshCw,
} from "lucide-react";
import { usePatient } from "../../services/auth/session";
import { api, post } from "../../services/api/client";
import { packetSchema } from "../../services/api/contracts";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  Loading,
  Notice,
  PageHeader,
} from "../../design-system/primitives";
import { SelectField, TextField } from "../../design-system/fields";
import { concernList } from "../care/contracts";
import { dateLabel, localDay } from "../journal/contracts";
import { types } from "../records/RecordCard";
import {
  episodesSchema,
  observationsSchema,
  timelineSchema,
  type TimelineItem,
} from "./contracts";
import ObservationSummary from "./ObservationSummary";
import CareIntelligence from "../care-intelligence/CareIntelligence";

const kinds = [
  { value: "", label: "All event types" },
  { value: "note", label: "Personal notes" },
  { value: "symptom", label: "Symptom observations" },
  { value: "document", label: "Documents" },
  { value: "medication", label: "Medication history" },
  { value: "concern", label: "Health concerns" },
  { value: "episode", label: "Care groupings" },
  { value: "care_relationship", label: "Care relationships" },
];
const labels = {
  journal: "Journal",
  document: "Document",
  medication: "Medication history",
  concern: "Health concern",
  episode: "Care grouping",
  care_relationship: "Care relationship",
};
const icons = {
  journal: BookOpen,
  document: Files,
  medication: Pill,
  concern: Heart,
  episode: CalendarDays,
  care_relationship: Users,
};
function Entry({
  item,
  canPrepare,
  selected,
  toggle,
  disabled,
}: {
  item: TimelineItem;
  canPrepare: boolean;
  selected: boolean;
  toggle: () => void;
  disabled: boolean;
}) {
  const Icon = icons[item.kind];
  return (
    <li className="insights-event">
      <div className="insights-event-icon">
        <Icon size={20} aria-hidden="true" />
      </div>
      <article aria-labelledby={`insight-${item.source_id}`}>
        <div className="journal-entry-heading">
          <span className="eyebrow">{labels[item.kind]}</span>
          <span className="journal-private">Private</span>
        </div>
        <h3 id={`insight-${item.source_id}`}>{item.title}</h3>
        <p className="insights-date">
          <strong>{dateLabel(item.occurrence)}</strong> · {item.date_meaning}
        </p>
        <p className="journal-writing">{item.description}</p>
        <p className="insights-provenance">
          {item.provenance === "patient_reported"
            ? "Patient-reported"
            : item.provenance === "accepted_contribution"
              ? "Accepted contribution"
              : "Uploaded original"}{" "}
          · {item.review_status}
        </p>
        <details>
          <summary>Attribution and recorded details</summary>
          <dl className="insights-details">
            {item.details.map((detail) => (
              <div key={detail.label}>
                <dt>{detail.label}</dt>
                <dd>{detail.value}</dd>
              </div>
            ))}
          </dl>
          <p>
            Recorded in Comfort {new Date(item.recorded_at).toLocaleString()}.
            This timestamp is separate from the occurrence date.
          </p>
        </details>
        <div className="actions">
          {item.href.startsWith("/app/") ? (
            <Link to={item.href.slice(4)}>
              {item.kind === "journal"
                ? "Open observation"
                : item.kind === "document"
                  ? "Review record"
                  : "Open care details"}
            </Link>
          ) : (
            <a href={item.href}>
              {item.kind === "episode"
                ? "Open existing care grouping tools"
                : "Open medication history"}
            </a>
          )}
          {item.original_url && (
            <a href={item.original_url}>Open exact original</a>
          )}
        </div>
        {canPrepare && item.kind === "document" && (
          <label className="care-checkbox insights-select">
            <input
              type="checkbox"
              checked={selected}
              disabled={disabled}
              onChange={toggle}
            />{" "}
            Include {item.title} in private visit selection
          </label>
        )}
      </article>
    </li>
  );
}

export default function Insights() {
  const patient = usePatient(),
    client = useQueryClient(),
    navigate = useNavigate();
  const base = `/api/workspaces/${patient.workspace_id}/`,
    root = `/workspaces/${patient.workspace_id}`;
  const permitted =
    patient.capabilities.includes("manage_profile") &&
    patient.capabilities.includes("read_workspace_records");
  const canPrepare = patient.capabilities.includes("prepare_packet");
  const [draft, setDraft] = useState(() => ({
    from: localDay(
      new Date(new Date().getFullYear(), new Date().getMonth(), 1),
    ),
    to: localDay(),
    concern: "",
    kind: "",
    origin: "",
    episode: "",
    document_type: "",
  }));
  const [filters, setFilters] = useState(draft),
    [scope, setScope] = useState<"dated" | "undated">("dated"),
    [page, setPage] = useState(1),
    [validation, setValidation] = useState("");
  const [selected, setSelected] = useState<TimelineItem[]>([]),
    [purpose, setPurpose] = useState("");
  const concerns = useQuery({
    queryKey: [patient.workspace_id, "care", "concerns"],
    enabled: permitted,
    queryFn: ({ signal }) =>
      api(base + "care/concerns/", concernList, { signal }),
  });
  const episodes = useQuery({
    queryKey: [patient.workspace_id, "episodes"],
    enabled: permitted,
    queryFn: ({ signal }) =>
      api(base + "episodes/", episodesSchema, { signal }),
  });
  const params = new URLSearchParams({
    ...filters,
    date_scope: scope,
    page: String(page),
  });
  const timeline = useQuery({
    queryKey: [base, "insights", "timeline", params.toString()],
    enabled: permitted,
    queryFn: ({ signal }) =>
      api(base + "insights/timeline/?" + params, timelineSchema, { signal }),
  });
  const summaryParams = new URLSearchParams({
    from: filters.from,
    to: filters.to,
    concern: filters.concern,
  });
  const summary = useQuery({
    queryKey: [base, "insights", "observations", summaryParams.toString()],
    enabled: permitted,
    queryFn: ({ signal }) =>
      api(
        base + "insights/observations/?" + summaryParams,
        observationsSchema,
        { signal },
      ),
  });
  const create = useMutation({
    mutationFn: () =>
      post(base + "packets/", packetSchema, {
        purpose,
        source_version_ids: selected.map((item) => item.source_version_id),
      }),
    onSuccess: (packet) => {
      setSelected([]);
      void client.invalidateQueries({ queryKey: ["packets"] });
      navigate(`${root}/care/${packet.id}`);
    },
  });
  const refresh = () => {
    void timeline.refetch();
    void summary.refetch();
  };
  const change =
    (key: keyof typeof draft) =>
    (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setDraft({ ...draft, [key]: event.target.value });
  if (!permitted)
    return (
      <>
        <PageHeader title="Insights" />
        <Notice>
          Your current context does not permit access to this private history.
        </Notice>
      </>
    );
  return (
    <>
      <PageHeader
        title="Insights"
        eyebrow="A little perspective"
        action={
          <Button
            variant="secondary"
            onPress={refresh}
            isDisabled={timeline.isFetching || summary.isFetching}
          >
            <RefreshCw size={17} aria-hidden="true" /> Refresh
          </Button>
        }
      >
        Bring the days and the documents together, with room for what is still
        unknown.
      </PageHeader>
      <form
        className="panel insights-filters"
        aria-label="Insights filters"
        onSubmit={(event) => {
          event.preventDefault();
          const days =
            (Date.parse(draft.to) - Date.parse(draft.from)) / 86400000;
          if (!Number.isFinite(days) || days < 0 || days > 365) {
            setValidation(
              "Choose a start and end date spanning no more than 366 days.",
            );
            return;
          }
          setValidation("");
          setFilters({ ...draft });
          setPage(1);
        }}
      >
        <div className="form-grid">
          <TextField
            id="insights-from"
            label="From"
            inputProps={{
              type: "date",
              required: true,
              value: draft.from,
              onChange: change("from"),
            }}
          />
          <TextField
            id="insights-to"
            label="Through"
            inputProps={{
              type: "date",
              required: true,
              value: draft.to,
              onChange: change("to"),
            }}
          />
          <SelectField
            id="insights-concern"
            label="Health concern"
            options={[
              { value: "", label: "All concerns" },
              ...(concerns.data?.items ?? []).map((c) => ({
                value: c.id,
                label: c.values.title,
              })),
            ]}
            selectProps={{ value: draft.concern, onChange: change("concern") }}
          />
        </div>
        <details>
          <summary>Refine the care timeline</summary>
          <div className="form-grid">
            <SelectField
              id="insights-kind"
              label="Event type"
              options={kinds}
              selectProps={{ value: draft.kind, onChange: change("kind") }}
            />
            <SelectField
              id="insights-origin"
              label="Entry origin"
              options={[
                { value: "", label: "All origins" },
                {
                  value: "patient_reported",
                  label: "Patient-reported entries",
                },
                { value: "source_record", label: "Source documents" },
              ]}
              selectProps={{ value: draft.origin, onChange: change("origin") }}
            />
            <SelectField
              id="insights-episode"
              label="Care grouping"
              options={[
                { value: "", label: "All groupings" },
                ...(episodes.data?.episodes ?? []).map((e) => ({
                  value: e.id,
                  label: e.title,
                })),
              ]}
              selectProps={{
                value: draft.episode,
                onChange: change("episode"),
              }}
            />
            <SelectField
              id="insights-type"
              label="Document type"
              options={[
                { value: "", label: "All document types" },
                ...Object.entries(types).map(([value, label]) => ({
                  value,
                  label,
                })),
              ]}
              selectProps={{
                value: draft.document_type,
                onChange: change("document_type"),
              }}
            />
          </div>
        </details>
        <p className="care-access">
          Dates and concern apply to both views. Other filters apply to the
          timeline only. Concern and grouping filters follow saved links; they
          do not infer relationships.
        </p>
        {(concerns.error || episodes.error) && (
          <Notice tone="warning">
            Some saved filter choices could not be loaded.{" "}
            <Button
              variant="quiet"
              onPress={() => {
                void concerns.refetch();
                void episodes.refetch();
              }}
            >
              Retry filter choices
            </Button>
          </Notice>
        )}
        {validation && (
          <Notice live tone="error">
            {validation}
          </Notice>
        )}
        <Button type="submit">Apply filters</Button>
      </form>
      {summary.isLoading && <Loading>Counting recorded observations…</Loading>}
      {summary.error && (
        <Notice live tone="error">
          {summary.error.message}{" "}
          <Button variant="quiet" onPress={() => void summary.refetch()}>
            Retry observations
          </Button>
        </Notice>
      )}
      {summary.data && (
        <ObservationSummary
          key={summaryParams.toString()}
          data={summary.data}
        />
      )}
      <CareIntelligence key={`${patient.workspace_id}:${filters.from}:${filters.to}`} from={filters.from} to={filters.to} />
      <section className="insights-timeline" aria-labelledby="timeline-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">The thread of your care</p>
            <h2 id="timeline-heading">Care timeline</h2>
          </div>
          <Link to={`${root}/journal`}>Add a Journal observation</Link>
        </div>
        <p>
          Current document versions and active patient-reported entries. Drafts
          and archived entries are excluded. Partial dates remain partial; their
          possible date range is used for browsing, with the latest known start
          first.
        </p>
        <div
          className="actions"
          role="group"
          aria-label="Timeline date coverage"
        >
          <Button
            variant={scope === "dated" ? "primary" : "secondary"}
            aria-pressed={scope === "dated"}
            onPress={() => {
              setScope("dated");
              setPage(1);
            }}
          >
            Dated{timeline.data ? ` (${timeline.data.dated_count})` : ""}
          </Button>
          <Button
            variant={scope === "undated" ? "primary" : "secondary"}
            aria-pressed={scope === "undated"}
            onPress={() => {
              setScope("undated");
              setPage(1);
            }}
          >
            Undated{timeline.data ? ` (${timeline.data.undated_count})` : ""}
          </Button>
        </div>
        {scope === "undated" && (
          <Notice>
            These entries have no occurrence date. They cannot be placed inside
            the chosen date range; all undated entries matching your other
            filters appear here. Care groupings have no appointment date.
          </Notice>
        )}
        {timeline.data && !timeline.data.medications_included && (
          <Notice>
            Medication history is not included under your current permissions.
          </Notice>
        )}
        {timeline.isLoading && <Loading>Opening your care timeline…</Loading>}
        {timeline.error && (
          <Notice live tone="error">
            {timeline.error.message}{" "}
            <Button variant="quiet" onPress={() => void timeline.refetch()}>
              Retry timeline
            </Button>
          </Notice>
        )}
        {timeline.data?.items.length === 0 && (
          <EmptyState title="Nothing recorded in this view">
            Try another range or filter, or add an observation in Journal. An
            empty view does not prove that a care event did not happen.
          </EmptyState>
        )}
        <ol className="insights-events" aria-label="Care timeline events">
          {timeline.data?.items.map((item) => (
            <Entry
              key={item.id}
              item={item}
              canPrepare={canPrepare}
              selected={selected.some(
                (value) => value.source_version_id === item.source_version_id,
              )}
              disabled={
                create.isPending ||
                (selected.length >= 30 &&
                  !selected.some(
                    (value) =>
                      value.source_version_id === item.source_version_id,
                  ))
              }
              toggle={() =>
                setSelected((previous) =>
                  previous.some(
                    (value) =>
                      value.source_version_id === item.source_version_id,
                  )
                    ? previous.filter(
                        (value) =>
                          value.source_version_id !== item.source_version_id,
                      )
                    : [...previous, item],
                )
              }
            />
          ))}
        </ol>
        {timeline.data && (
          <nav
            className="actions journal-pagination"
            aria-label="Timeline pages"
          >
            <Button
              variant="secondary"
              isDisabled={page === 1 || timeline.isFetching}
              onPress={() => setPage(page - 1)}
            >
              Previous timeline page
            </Button>
            <span>Page {page}</span>
            <Button
              variant="secondary"
              isDisabled={!timeline.data.next_page || timeline.isFetching}
              onPress={() => setPage(timeline.data!.next_page!)}
            >
              Next timeline page
            </Button>
          </nav>
        )}
      </section>
      {selected.length > 0 && (
        <section
          className="panel form-section"
          aria-label="Private visit selection"
        >
          <h2>Prepare from your originals</h2>
          <p>
            {selected.length} exact document versions selected, out of a maximum
            of 30. Selection stays on this page until you save or leave.
          </p>
          <ul>
            {selected.map((item) => (
              <li key={item.source_version_id}>
                {item.title}
                <Button
                  variant="quiet"
                  isDisabled={create.isPending}
                  onPress={() =>
                    setSelected(
                      selected.filter(
                        (value) =>
                          value.source_version_id !== item.source_version_id,
                      ),
                    )
                  }
                >
                  Remove {item.title}
                </Button>
              </li>
            ))}
          </ul>
          <TextField
            id="insights-purpose"
            label="Purpose of your visit"
            inputProps={{
              value: purpose,
              maxLength: 180,
              onChange: (event) => setPurpose(event.target.value),
            }}
          />
          <p>
            Only the selected original documents and their reviewed details are
            included. Journal observations, medication entries and care
            relationships stay private and are not included.
          </p>
          <ConfirmDialog
            trigger="Prepare private visit selection"
            title="Save this private selection?"
            confirmLabel="Save private selection"
            disabled={!purpose.trim() || create.isPending}
            onConfirm={() => create.mutate()}
          >
            <p>{purpose}</p>
            <ul>
              {selected.map((item) => (
                <li key={item.id}>{item.title}</li>
              ))}
            </ul>
            <p>
              This freezes {selected.length} exact original versions with their
              currently reviewed details. It does not share information or send
              a request to Apertus. You can request an overview from the saved
              visit selection.
            </p>
          </ConfirmDialog>
          {create.error && (
            <Notice live tone="error">
              {create.error.message}
            </Notice>
          )}
        </section>
      )}
      <aside className="insights-next panel" aria-label="Next steps">
        <h2>Take the next step when you are ready</h2>
        <p>
          Look into an observation, review an original, or choose the documents
          you want to take to your next visit.
        </p>
        <div className="actions">
          <Link to={`${root}/records`}>Explore records and Apertus search</Link>
          <Link to={`${root}/care`}>Your private visit selections</Link>
        </div>
      </aside>
    </>
  );
}
