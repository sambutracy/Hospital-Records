import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { usePatient } from "../../services/auth/session";
import { api, post } from "../../services/api/client";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  Loading,
  Notice,
  PageHeader,
} from "../../design-system/primitives";
import { partialDate } from "../records/RecordCard";
import CareNavigation from "./CareNavigation";
import CareEditor from "./CareEditor";
import {
  concernList,
  practitionerList,
  assignmentList,
  circleSchema,
  historySchema,
  schemas,
  type CareEntry,
  type CareKind,
  type Concern,
} from "./contracts";
type Editor = { kind: CareKind; entry?: CareEntry; doctorId?: string };
function snapshotValue(value: unknown): string {
  if (value === null) return "Not specified";
  if (typeof value === "string" || typeof value === "number")
    return String(value);
  if (value && typeof value === "object" && "precision" in value) {
    const parsed =
      concernList.shape.items.element.shape.values.shape.onset.safeParse(value);
    if (parsed.success) return partialDate(parsed.data);
  }
  return "Not specified";
}
function History({ kind, id }: { kind: CareKind; id: string }) {
  const patient = usePatient();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  const query = useQuery({
    queryKey: ["care", "history", kind, id],
    queryFn: ({ signal }) =>
      api(
        `/api/workspaces/${patient.id}/care/${kind}/${id}/history/`,
        historySchema,
        { signal },
      ),
  });
  return (
    <section
      className="panel form-section"
      aria-label="Care correction history"
    >
      <h2 tabIndex={-1} ref={heading}>
        Saved revision history
      </h2>
      <p>
        Earlier patient-reported values are kept when you correct or archive an
        entry.
      </p>
      {query.isPending ? (
        <Loading />
      ) : query.isError ? (
        <Notice tone="error">{query.error.message}</Notice>
      ) : (
        query.data.history.map((h) => (
          <details className="care-history" key={h.revision}>
            <summary>
              Revision {h.revision} · {new Date(h.created_at).toLocaleString()}
            </summary>
            <dl className="source-info">
              {Object.entries(h.snapshot)
                .filter(
                  ([name]) =>
                    !["revision", "practitioner_id", "concern_id"].includes(
                      name,
                    ),
                )
                .map(([name, value]) => (
                  <div key={name}>
                    <dt>{name.replaceAll("_", " ")}</dt>
                    <dd>{snapshotValue(value)}</dd>
                  </div>
                ))}
            </dl>
          </details>
        ))
      )}
    </section>
  );
}
export default function Relationships({ page }: { page: "concerns" | "team" }) {
  const patient = usePatient();
  const cache = useQueryClient();
  const base = `/api/workspaces/${patient.id}/care/`;
  const allowed =
    patient.capabilities.includes("manage_profile") &&
    patient.capabilities.includes("read_workspace_records");
  const concerns = useQuery({
    queryKey: ["care", "concerns"],
    enabled: allowed,
    queryFn: ({ signal }) => api(base + "concerns/", concernList, { signal }),
  });
  const doctors = useQuery({
    queryKey: ["care", "practitioners"],
    enabled: allowed,
    queryFn: ({ signal }) =>
      api(base + "practitioners/", practitionerList, { signal }),
  });
  const assignments = useQuery({
    queryKey: ["care", "assignments"],
    enabled: allowed,
    queryFn: ({ signal }) =>
      api(base + "assignments/", assignmentList, { signal }),
  });
  const contacts = useQuery({
    queryKey: ["care", "contacts"],
    enabled: allowed && page === "team",
    queryFn: ({ signal }) =>
      api(`/api/workspaces/${patient.id}/care-circle/`, circleSchema, {
        signal,
      }),
  });
  const [editor, setEditor] = useState<Editor | null>(
    () => cache.getQueryData<Editor>(["care", "draft", "editor"]) ?? null,
  );
  const wasEditing = useRef(!!editor);
  useEffect(() => {
    if (wasEditing.current && !editor)
      document.getElementById("care-add")?.focus();
    wasEditing.current = !!editor;
  }, [editor]);
  const [history, setHistory] = useState<{ kind: CareKind; id: string } | null>(
    null,
  );
  const [showArchived, setShowArchived] = useState(false);
  const [filter, setFilter] = useState("");
  const [message, setMessage] = useState(() =>
    cache.getQueryData(["care", "draft", "values"])
      ? "Your unsaved care draft is restored in this patient context. Review it before saving."
      : "",
  );
  const state = useMutation({
    mutationFn: ({ kind, item }: { kind: CareKind; item: CareEntry }) =>
      post(
        base + `${kind}/${item.id}/status/`,
        schemas[kind] as z.ZodType<CareEntry>,
        {
          status: item.status === "active" ? "archived" : "active",
          expected_revision: item.revision,
        },
      ),
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ["care"] });
      setMessage(
        "Care entry updated. Its history and separate access permissions are preserved.",
      );
    },
  });
  const edit = (value: Editor) => {
    cache.removeQueries({ queryKey: ["care", "draft"] });
    cache.setQueryData(["care", "draft", "editor"], value);
    setEditor(value);
    setHistory(null);
    setMessage("");
  };
  const title = (item: CareEntry) =>
    "title" in item.values
      ? item.values.title
      : "name" in item.values
        ? item.values.name
        : item.values.role;
  const controls = (kind: CareKind, item: CareEntry) => (
    <div className="actions">
      {item.status === "active" && (
        <Button
          variant="secondary"
          onPress={() => edit({ kind, entry: item })}
          isDisabled={!!editor || state.isPending}
        >
          Edit {title(item)}
        </Button>
      )}
      <Button variant="quiet" onPress={() => setHistory({ kind, id: item.id })}>
        History for {title(item)}
      </Button>
      <ConfirmDialog
        trigger={`${item.status === "active" ? "Archive" : "Restore"} ${title(item)}`}
        title={
          item.status === "active"
            ? "Archive this care entry?"
            : "Restore this care entry?"
        }
        confirmLabel={item.status === "active" ? "Archive" : "Restore"}
        disabled={state.isPending || !!editor}
        onConfirm={() => state.mutate({ kind, item })}
      >
        <p>
          {item.status === "active"
            ? "This hides the entry from your active list. Related entries and earlier revisions remain saved."
            : "This returns the entry to your active list. A relationship needs an active doctor and concern to be restored."}
        </p>
        <p>Existing sharing permissions are managed separately.</p>
      </ConfirmDialog>
    </div>
  );
  const reload = async () => {
    if (!editor) return;
    const result = await (editor.kind === "concerns"
      ? concerns.refetch()
      : editor.kind === "practitioners"
        ? doctors.refetch()
        : assignments.refetch());
    if (result.error) {
      setMessage(
        "The latest revision could not be loaded. Your draft is still open.",
      );
      return;
    }
    const latest = result.data?.items.find(
      (item) => item.id === editor.entry?.id,
    );
    if (latest?.status === "active") {
      cache.removeQueries({ queryKey: ["care", "draft"] });
      const next = { ...editor, entry: latest };
      cache.setQueryData(["care", "draft", "editor"], next);
      setEditor(next);
    } else {
      cache.removeQueries({ queryKey: ["care", "draft"] });
      setEditor(null);
      setMessage(
        "This entry is archived or unavailable. Return to the saved list before editing.",
      );
    }
  };
  const close = () => {
    cache.removeQueries({ queryKey: ["care", "draft"] });
    setEditor(null);
  };
  const visible = (item: CareEntry) => showArchived || item.status === "active";
  const concernName = (id: string | null) =>
    id
      ? (concerns.data?.items.find((c) => c.id === id)?.values.title ??
        "Concern unavailable")
      : "General care";
  const concernDates = (c: Concern) => partialDate(c.values.onset);
  return (
    <>
      <PageHeader
        eyebrow="MY CARE"
        title={page === "concerns" ? "Health concerns" : "Your Care Team"}
      >
        {page === "concerns"
          ? "Start with your own words. An issue can stay uncertain while you investigate it."
          : "Keep a record of the people who have helped with your care, across visits and facilities."}
      </PageHeader>
      <CareNavigation />
      {!allowed ? (
        <Notice>
          Care relationship tools are unavailable in your current authorized
          context.
        </Notice>
      ) : (
        <>
          <Notice>
            Patient-reported information. Adding a doctor or contact does not
            verify their identity or grant record access.
          </Notice>
          <div className="section-heading">
            <h2>{page === "concerns" ? "Your concerns" : "Doctors"}</h2>
            <Button
              id="care-add"
              onPress={() =>
                edit({
                  kind: page === "concerns" ? "concerns" : "practitioners",
                })
              }
              isDisabled={!!editor}
            >
              Add {page === "concerns" ? "health concern" : "doctor"}
            </Button>
          </div>
          <div className="care-filters">
            <label className="care-checkbox">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
              />
              Show archived entries
            </label>
            {page === "team" && (
              <div className="field">
                <label htmlFor="care-filter">Filter doctors by concern</label>
                <select
                  id="care-filter"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  <option value="">All concerns</option>
                  {concerns.data?.items
                    .filter((c) => c.status === "active")
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.values.title}
                      </option>
                    ))}
                </select>
              </div>
            )}
          </div>
          {message && (
            <Notice live tone="success">
              {message}
            </Notice>
          )}
          {state.isError && (
            <Notice tone="error" live>
              {state.error.message}
            </Notice>
          )}
          {concerns.isPending || doctors.isPending || assignments.isPending ? (
            <Loading />
          ) : concerns.isError || doctors.isError || assignments.isError ? (
            <Notice tone="error">
              {concerns.error?.message ??
                doctors.error?.message ??
                assignments.error?.message}
              <Button
                variant="secondary"
                onPress={() => {
                  void cache.invalidateQueries({ queryKey: ["care"] });
                }}
              >
                Try again
              </Button>
            </Notice>
          ) : (
            <>
              {editor && (
                <CareEditor
                  key={`${editor.kind}:${editor.entry?.id ?? editor.doctorId ?? "new"}:${editor.entry?.revision ?? 0}`}
                  {...editor}
                  concerns={concerns.data.items}
                  practitioners={doctors.data.items}
                  onClose={close}
                  onSaved={() => {
                    close();
                    setMessage(
                      "Saved to your care information. No access permission was created.",
                    );
                  }}
                  onReload={reload}
                />
              )}
              {page === "concerns" ? (
                <div className="record-grid">
                  {concerns.data.items.filter(visible).map((c) => (
                    <article className="record-card" key={c.id}>
                      <div className="badges">
                        <span className="badge">
                          {c.status === "archived"
                            ? "Archived"
                            : c.values.certainty === "unconfirmed"
                              ? "Unconfirmed"
                              : "Reported diagnosis"}
                        </span>
                        <span className="badge">Patient-reported</span>
                      </div>
                      <h3>{c.values.title}</h3>
                      <p>{c.values.description || "No description added."}</p>
                      <p>Began: {concernDates(c)}</p>
                      <p>
                        {
                          assignments.data.items.filter(
                            (a) =>
                              a.status === "active" &&
                              a.values.concern_id === c.id,
                          ).length
                        }{" "}
                        linked care relationships
                      </p>
                      <Link to="../care/team">
                        Find doctors in your Care Team
                      </Link>
                      {controls("concerns", c)}
                    </article>
                  ))}
                  {!concerns.data.items.filter(visible).length && (
                    <EmptyState title="You do not need a diagnosis to begin">
                      Add the concern or investigation you want to keep track
                      of.
                    </EmptyState>
                  )}
                </div>
              ) : (
                <>
                  <div className="record-grid">
                    {doctors.data.items
                      .filter(visible)
                      .filter(
                        (d) =>
                          !filter ||
                          assignments.data.items.some(
                            (a) =>
                              visible(a) &&
                              a.values.practitioner_id === d.id &&
                              a.values.concern_id === filter,
                          ),
                      )
                      .map((d) => (
                        <article className="record-card" key={d.id}>
                          <div className="badges">
                            <span className="badge">
                              {d.status === "archived"
                                ? "Archived doctor"
                                : "Patient-reported doctor"}
                            </span>
                            <span className="badge">Identity unverified</span>
                          </div>
                          <h3>{d.values.name}</h3>
                          <p>
                            {d.values.specialty || "Specialty not recorded"} ·{" "}
                            {d.values.facility || "Facility not recorded"}
                          </p>
                          {d.values.notes && <p>{d.values.notes}</p>}
                          <p className="care-access">
                            Access: this relationship grants no record access.
                          </p>
                          {assignments.data.items
                            .filter(
                              (a) =>
                                a.values.practitioner_id === d.id && visible(a),
                            )
                            .map((a) => (
                              <section
                                className="care-relationship"
                                key={a.id}
                                aria-label={`${a.values.role} relationship`}
                              >
                                <h4>{concernName(a.values.concern_id)}</h4>
                                <p>
                                  {a.values.role} ·{" "}
                                  {a.values.participation === "current"
                                    ? "Current"
                                    : "Historical"}
                                  {a.status === "archived"
                                    ? " · Archived relationship"
                                    : ""}
                                </p>
                                <p>
                                  {partialDate(a.values.start_date)} —{" "}
                                  {partialDate(a.values.end_date)}
                                </p>
                                {a.values.notes && <p>{a.values.notes}</p>}
                                {controls("assignments", a)}
                              </section>
                            ))}
                          {d.status === "active" && (
                            <Button
                              variant="secondary"
                              onPress={() =>
                                edit({ kind: "assignments", doctorId: d.id })
                              }
                              isDisabled={!!editor}
                            >
                              Link a concern for {d.values.name}
                            </Button>
                          )}
                          {controls("practitioners", d)}
                        </article>
                      ))}
                  </div>
                  {!doctors.data.items.filter(visible).length && (
                    <EmptyState title="Remember who helped">
                      Add a doctor from a past visit, then connect them to a
                      concern.
                    </EmptyState>
                  )}
                  {filter &&
                    !doctors.data.items
                      .filter(visible)
                      .some((d) =>
                        assignments.data.items.some(
                          (a) =>
                            visible(a) &&
                            a.values.practitioner_id === d.id &&
                            a.values.concern_id === filter,
                        ),
                      ) && (
                      <Notice>
                        No doctors match this concern. Choose All concerns to
                        add a relationship.
                      </Notice>
                    )}
                  <section className="quiet-section">
                    <h2>Family and support contacts</h2>
                    <p>
                      Your existing care circle is shown here. “Guardian” is a
                      reported relationship; legal authority is not verified
                      here.
                    </p>
                    {contacts.isPending ? (
                      <Loading />
                    ) : contacts.isError ? (
                      <Notice tone="error">{contacts.error.message}</Notice>
                    ) : (
                      <div className="record-grid">
                        {contacts.data.contacts.map((c) => (
                          <article className="record-card" key={c.id}>
                            <h3>{c.values.full_name}</h3>
                            <p>
                              {c.values.relationship.replaceAll("_", " ")}
                              {c.values.is_next_of_kin ? " · Next of kin" : ""}
                              {c.values.is_emergency_contact
                                ? " · Emergency contact"
                                : ""}
                            </p>
                            <p>
                              Access: saving this contact grants no record
                              access.
                            </p>
                          </article>
                        ))}
                        {!contacts.data.contacts.length && (
                          <p>No support contacts saved yet.</p>
                        )}
                      </div>
                    )}
                    <a href={`/workspaces/${patient.id}/profile/`}>
                      Manage your existing care circle
                    </a>
                  </section>
                  <section className="quiet-section">
                    <h2>Identity and access are separate</h2>
                    <p>
                      These doctor entries are private notes, not registered
                      clinician accounts. Verified professional affiliations and
                      delegated acting contexts are pending a trusted
                      verification workflow.
                    </p>
                    <a href={`/workspaces/${patient.id}/`}>
                      View existing sharing and access tools
                    </a>
                  </section>
                </>
              )}
              {history && (
                <>
                  <History key={`${history.kind}:${history.id}`} {...history} />
                  <Button variant="quiet" onPress={() => setHistory(null)}>
                    Close revision history
                  </Button>
                </>
              )}
            </>
          )}
        </>
      )}
    </>
  );
}
