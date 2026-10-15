import { useState, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  CalendarDays,
  List,
  Plus,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { api, post } from "../../services/api/client";
import { usePatient } from "../../services/auth/session";
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
import Editor from "./Editor";
import {
  dateLabel,
  draftSchema,
  editFields,
  eventSchema,
  historySchema,
  initialFields,
  listSchema,
  localDay,
  type JournalEvent,
  type EditorState,
} from "./contracts";

function History({ base, event }: { base: string; event: JournalEvent }) {
  const [open, setOpen] = useState(false);
  const query = useQuery({
    queryKey: [base, event.id, "history", event.revision],
    enabled: open,
    queryFn: ({ signal }) =>
      api(base + event.id + "/history/", historySchema, { signal }),
  });
  return (
    <details
      className="care-history"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>Correction history</summary>
      {query.isLoading && <Loading />}
      {query.error && <Notice tone="error">{query.error.message}</Notice>}
      {query.data && (
        <>
          <ol className="journal-history">
            {query.data.history.map((row) => (
              <li key={row.revision}>
                <p>
                  <strong>Revision {row.revision}</strong> ·{" "}
                  {new Date(row.recorded_at).toLocaleString()} ·{" "}
                  {row.snapshot.status}
                </p>
                <p>
                  {dateLabel(row.snapshot.occurrence)} · Patient-reported{" "}
                  {row.snapshot.category}
                </p>
                <p className="journal-writing">{row.snapshot.description}</p>
                {row.snapshot.severity !== null && (
                  <p>Reported severity: {row.snapshot.severity} / 10</p>
                )}
              </li>
            ))}
          </ol>
          {query.data.truncated && (
            <Notice>The latest 100 revisions are shown.</Notice>
          )}
        </>
      )}
    </details>
  );
}

export default function Journal() {
  const { eventId } = useParams();
  const patient = usePatient(),
    client = useQueryClient(),
    base = `/api/workspaces/${patient.workspace_id}/journal/`;
  const canManage =
    patient.capabilities.includes("manage_profile") &&
    patient.capabilities.includes("read_workspace_records");
  const [view, setView] = useState<"day" | "list">("day"),
    [day, setDay] = useState(localDay());
  const [from, setFrom] = useState(
      localDay(new Date(new Date().getFullYear(), new Date().getMonth(), 1)),
    ),
    [to, setTo] = useState(localDay());
  const [category, setCategory] = useState(""),
    [concern, setConcern] = useState(""),
    [archived, setArchived] = useState(false),
    [undated, setUndated] = useState(false),
    [page, setPage] = useState(1);
  const [editor, setEditor] = useState<EditorState | null>(
    () => client.getQueryData<EditorState>([base, "editor"]) ?? null,
  );
  const [message, setMessage] = useState(""),
    [error, setError] = useState(""),
    [working, setWorking] = useState(false);
  const feedback = useRef<HTMLDivElement>(null);
  const concerns = useQuery({
    queryKey: [patient.workspace_id, "care", "concerns"],
    enabled: canManage,
    queryFn: ({ signal }) =>
      api(
        `/api/workspaces/${patient.workspace_id}/care/concerns/`,
        concernList,
        { signal },
      ),
  });
  const recovery = useQuery({
    queryKey: [base, "draft"],
    enabled: canManage,
    queryFn: ({ signal }) => api(base + "draft/", draftSchema, { signal }),
  });
  const params = new URLSearchParams({
    from: view === "day" ? day : from,
    to: view === "day" ? day : to,
    category,
    concern,
    status: archived ? "archived" : "active",
    page: String(page),
    undated: String(view === "list" && undated),
  });
  const validRange = Boolean(
    params.get("from") &&
      params.get("to") &&
      params.get("from")! <= params.get("to")!,
  );
  const entries = useQuery({
    queryKey: [base, "list", params.toString()],
    enabled: canManage && validRange && !eventId,
    queryFn: ({ signal }) => api(base + "?" + params, listSchema, { signal }),
  });
  const selectedEntry = useQuery({
    queryKey: [base, "detail", eventId],
    enabled: canManage && Boolean(eventId),
    queryFn: ({ signal }) => api(base + eventId + "/", eventSchema, { signal }),
  });
  const displayed = eventId
    ? selectedEntry.data
      ? [selectedEntry.data]
      : []
    : entries.data?.items;
  const displayQuery = eventId ? selectedEntry : entries;
  const refresh = () => {
    void client.invalidateQueries({ queryKey: [base] });
  };
  const close = () => {
    client.removeQueries({ queryKey: [base, "editor"] });
    setEditor(null);
    refresh();
  };
  const saved = (event: JournalEvent) => {
    client.removeQueries({ queryKey: [base, "editor"] });
    setEditor(null);
    setMessage(
      event.revision === 1
        ? "Observation saved privately."
        : "Correction saved. Earlier revisions remain in history.",
    );
    setError("");
    refresh();
    setTimeout(() => feedback.current?.focus(), 0);
  };
  const filter =
    (setter: (value: string) => void) =>
    (event: React.ChangeEvent<HTMLSelectElement | HTMLInputElement>) => {
      setter(event.target.value);
      setPage(1);
    };
  const changeStatus = async (event: JournalEvent) => {
    setWorking(true);
    setError("");
    try {
      await post(base + event.id + "/status/", eventSchema, {
        status: event.status === "active" ? "archived" : "active",
        expected_revision: event.revision,
      });
      setMessage(
        event.status === "active"
          ? "Observation archived. Its history remains available."
          : "Observation restored.",
      );
      refresh();
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "This change was not saved.",
      );
    } finally {
      setWorking(false);
    }
  };
  const switchDay = (offset: number) => {
    const value = new Date(day + "T12:00:00");
    value.setDate(value.getDate() + offset);
    setDay(localDay(value));
    setPage(1);
  };
  if (!canManage)
    return (
      <>
        <PageHeader title="Journal" />
        <Notice>
          Your current context does not permit private Journal access.
        </Notice>
      </>
    );
  return (
    <>
      <PageHeader
        title={eventId ? "Journal observation" : "Journal"}
        eyebrow="The days between appointments"
        action={
          !editor &&
          !eventId && (
            <Button
              isDisabled={!recovery.data || Boolean(recovery.data.draft)}
              onPress={() => {
                setMessage("");
                setEditor({ fields: initialFields(day) });
              }}
            >
              <Plus size={18} aria-hidden="true" /> Add observation
            </Button>
          )
        }
      >
        A place for what you notice, how you feel, and what you want to
        remember.
      </PageHeader>
      {eventId && (
        <p>
          <Link to={`/workspaces/${patient.workspace_id}/journal`}>
            Back to Journal
          </Link>{" "}
          ·{" "}
          <Link to={`/workspaces/${patient.workspace_id}/insights`}>
            Back to Insights
          </Link>
        </p>
      )}
      <div ref={feedback} tabIndex={-1}>
        {message && (
          <Notice live tone="success">
            {message}
          </Notice>
        )}
        {error && (
          <Notice live tone="error">
            {error}
          </Notice>
        )}
      </div>
      {recovery.error && (
        <Notice tone="error">
          We could not check your recovery draft. {recovery.error.message}{" "}
          <Button
            variant="quiet"
            onPress={() => {
              void recovery.refetch();
            }}
          >
            Retry
          </Button>
        </Notice>
      )}
      {editor ? (
        <Editor
          base={base}
          initial={editor.fields}
          eventId={editor.eventId}
          baseRevision={editor.revision}
          recovery={editor.recovery}
          concerns={concerns.data?.items ?? []}
          onDone={saved}
          onClose={close}
        />
      ) : (
        <>
          {recovery.data?.draft && (
            <section
              className="journal-recovery"
              aria-label="Private recovery draft"
            >
              <BookOpen aria-hidden="true" />
              <div>
                <h2>A thought you left here</h2>
                <p>
                  Private draft saved{" "}
                  {new Date(recovery.data.draft.updated_at).toLocaleString()}.
                  It has not been published to Journal.
                </p>
                <Button
                  variant="secondary"
                  onPress={() => {
                    const draft = recovery.data!.draft!;
                    setEditor({
                      fields: draft.fields,
                      eventId: draft.event_id,
                      revision: draft.base_revision,
                      recovery: draft,
                    });
                  }}
                >
                  Resume private draft
                </Button>
              </div>
            </section>
          )}
          {!eventId && (
            <section
              className="journal-controls panel"
              aria-label="Journal navigation"
            >
              <div
                className="journal-view-switch"
                role="group"
                aria-label="Journal view"
              >
                <Button
                  variant={view === "day" ? "primary" : "secondary"}
                  aria-pressed={view === "day"}
                  onPress={() => {
                    setView("day");
                    setPage(1);
                  }}
                >
                  <CalendarDays size={18} aria-hidden="true" /> Day
                </Button>
                <Button
                  variant={view === "list" ? "primary" : "secondary"}
                  aria-pressed={view === "list"}
                  onPress={() => {
                    setView("list");
                    setPage(1);
                  }}
                >
                  <List size={18} aria-hidden="true" /> List
                </Button>
              </div>
              {view === "day" ? (
                <div className="journal-day-switch">
                  <Button
                    variant="quiet"
                    aria-label="Previous day"
                    onPress={() => switchDay(-1)}
                  >
                    <ChevronLeft aria-hidden="true" />
                  </Button>
                  <TextField
                    id="journal-selected-day"
                    label="Selected day"
                    inputProps={{
                      type: "date",
                      value: day,
                      required: true,
                      onChange: filter(setDay),
                    }}
                  />
                  <Button
                    variant="quiet"
                    aria-label="Next day"
                    onPress={() => switchDay(1)}
                  >
                    <ChevronRight aria-hidden="true" />
                  </Button>
                  <Button
                    variant="quiet"
                    onPress={() => {
                      setDay(localDay());
                      setPage(1);
                    }}
                  >
                    Today
                  </Button>
                </div>
              ) : (
                <div className="form-grid">
                  <TextField
                    id="journal-from"
                    label="From"
                    inputProps={{
                      type: "date",
                      value: from,
                      onChange: filter(setFrom),
                    }}
                  />
                  <TextField
                    id="journal-to"
                    label="To"
                    inputProps={{
                      type: "date",
                      value: to,
                      onChange: filter(setTo),
                    }}
                  />
                </div>
              )}
              <div className="form-grid">
                <SelectField
                  id="journal-filter-category"
                  label="Entry type"
                  options={[
                    { value: "", label: "All types" },
                    { value: "note", label: "Personal notes" },
                    { value: "symptom", label: "Symptoms" },
                  ]}
                  selectProps={{
                    value: category,
                    onChange: filter(setCategory),
                  }}
                />
                <SelectField
                  id="journal-filter-concern"
                  label="Health concern"
                  options={[
                    { value: "", label: "All concerns" },
                    ...(concerns.data?.items ?? []).map((item) => ({
                      value: item.id,
                      label: item.values.title,
                    })),
                  ]}
                  selectProps={{ value: concern, onChange: filter(setConcern) }}
                />
              </div>
              {concerns.error && (
                <Notice tone="warning">
                  Concern filters are unavailable. Notes can still be recorded
                  without a new concern link.
                </Notice>
              )}
              <div className="care-filters">
                <label className="care-checkbox">
                  <input
                    type="checkbox"
                    checked={archived}
                    onChange={(event) => {
                      setArchived(event.target.checked);
                      setPage(1);
                    }}
                  />{" "}
                  Show archived entries
                </label>
                {view === "list" && (
                  <label className="care-checkbox">
                    <input
                      type="checkbox"
                      checked={undated}
                      onChange={(event) => {
                        setUndated(event.target.checked);
                        setPage(1);
                      }}
                    />{" "}
                    Include undated entries
                  </label>
                )}
              </div>
              <p className="care-access">
                Your entries stay private. Adding a concern does not share them
                with anyone.
              </p>
            </section>
          )}
          {!eventId && !validRange && (
            <Notice tone="error">Choose a valid start and end date.</Notice>
          )}
          {displayQuery.isLoading && <Loading>Opening your Journal…</Loading>}
          {displayQuery.error && (
            <Notice tone="error">
              {displayQuery.error.message}{" "}
              {!eventId && "Choose a range of up to 366 days."}{" "}
              <Button
                variant="quiet"
                onPress={() => {
                  void displayQuery.refetch();
                }}
              >
                Retry
              </Button>
            </Notice>
          )}
          {!eventId && entries.data?.items.length === 0 && (
            <EmptyState
              title={
                archived
                  ? "No archived observations in this view"
                  : "Room for what you noticed"
              }
            >
              {archived
                ? "Archived entries remain available with their correction history."
                : "Nothing is recorded in this view. You can add a few words whenever it is useful. A blank day tells us nothing about how you felt."}
            </EmptyState>
          )}
          <div className="journal-entries" aria-label="Journal entries">
            {displayed?.map((event) => (
              <article
                key={event.id}
                className="panel journal-entry"
                aria-labelledby={`entry-${event.id}`}
              >
                <div className="journal-entry-heading">
                  <span className="eyebrow">
                    {event.values.category === "symptom"
                      ? "Symptom"
                      : "Personal note"}{" "}
                    · Patient-reported
                  </span>
                  <span className="journal-private">
                    Private{event.status === "archived" ? " · Archived" : ""}
                  </span>
                </div>
                <h2 id={`entry-${event.id}`}>
                  {dateLabel(event.values.occurrence)}
                </h2>
                {event.values.time && (
                  <p>
                    {event.values.time} · {event.values.timezone}
                    {event.values.fold === 1 ? " · second occurrence" : ""}
                  </p>
                )}
                <p className="journal-writing">{event.values.description}</p>
                {event.values.severity !== null && (
                  <p>
                    Reported severity:{" "}
                    <strong>{event.values.severity} / 10</strong>
                  </p>
                )}
                {event.values.concern_id && (
                  <p>
                    Associated with{" "}
                    <Link
                      to={`/workspaces/${patient.workspace_id}/care/concerns`}
                    >
                      {concerns.data?.items.find(
                        (c) => c.id === event.values.concern_id,
                      )?.values.title ?? "saved health concern"}
                    </Link>
                  </p>
                )}
                <p className="journal-recorded">
                  Recorded {new Date(event.created_at).toLocaleString()} ·
                  Revision {event.revision}
                </p>
                <div className="actions">
                  {event.status === "active" && (
                    <Button
                      variant="secondary"
                      isDisabled={
                        !recovery.data ||
                        Boolean(recovery.data.draft) ||
                        working
                      }
                      onPress={() => {
                        setMessage("");
                        setEditor({
                          fields: editFields(event),
                          eventId: event.id,
                          revision: event.revision,
                        });
                      }}
                    >
                      Correct entry
                    </Button>
                  )}
                  <ConfirmDialog
                    trigger={
                      event.status === "active"
                        ? "Archive entry"
                        : "Restore entry"
                    }
                    title={
                      event.status === "active"
                        ? "Archive this observation?"
                        : "Restore this observation?"
                    }
                    confirmLabel={
                      event.status === "active" ? "Archive" : "Restore"
                    }
                    disabled={working}
                    onConfirm={() => {
                      void changeStatus(event);
                    }}
                  >
                    <p>
                      {event.status === "active"
                        ? "It will leave the active Journal view. Earlier revisions remain in history."
                        : "It will return to the active Journal view with its history preserved."}
                    </p>
                  </ConfirmDialog>
                </div>
                <History base={base} event={event} />
              </article>
            ))}
          </div>
          {!eventId && entries.data && (
            <nav
              className="actions journal-pagination"
              aria-label="Journal pages"
            >
              <Button
                variant="secondary"
                isDisabled={page === 1 || entries.isFetching}
                onPress={() => setPage(page - 1)}
              >
                Previous page
              </Button>
              <span>Page {page}</span>
              <Button
                variant="secondary"
                isDisabled={!entries.data.next_page || entries.isFetching}
                onPress={() => setPage(entries.data!.next_page!)}
              >
                Next page
              </Button>
            </nav>
          )}
        </>
      )}
    </>
  );
}
