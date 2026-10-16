import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePatient } from "../../services/auth/session";
import { api, post } from "../../services/api/client";
import { Button, Notice, Loading } from "../../design-system/primitives";
import { TextAreaField } from "../../design-system/fields";
import { dateLabel } from "../journal/contracts";
import {
  candidatesSchema,
  statusSchema,
  tasksSchema,
  taskSchema,
  type Candidate,
} from "./contracts";

const categories = {
  source_excerpt: "Selected source excerpt",
  documented_followup: "Documented follow-up request",
  question_to_ask: "Passage you may wish to ask about",
  ambiguous_instruction: "Instruction needing clarification",
};
const pending = ["queued", "processing", "waiting_model"];

export default function CareIntelligence({
  from,
  to,
  packetId,
}: {
  from?: string;
  to?: string;
  packetId?: string;
}) {
  const patient = usePatient(),
    cache = useQueryClient();
  const base = `/api/workspaces/${patient.workspace_id}/care-ai/`;
  const kind = packetId ? "followup_actions" : "history_exploration";
  const [open, setOpen] = useState(false),
    [undated, setUndated] = useState(false),
    [selected, setSelected] = useState<Candidate[]>([]);
  const [active, setActive] = useState<string | null>(null),
    [edits, setEdits] = useState<Record<number, string>>({});
  const status = useQuery({
    queryKey: [base, "status"],
    queryFn: ({ signal }) => api(base + "status/", statusSchema, { signal }),
    retry: false,
  });
  const allowed = status.data?.enabled === true;
  const historyParams = new URLSearchParams({
    kind,
    ...(packetId ? { packet_id: packetId } : {}),
  });
  const history = useQuery({
    queryKey: [base, "tasks", historyParams.toString()],
    enabled: allowed,
    queryFn: ({ signal }) =>
      api(base + "tasks/?" + historyParams, tasksSchema, { signal }),
  });
  const selectedId = active ?? history.data?.tasks[0]?.id;
  const detail = useQuery({
    queryKey: [base, "task", selectedId],
    enabled: allowed && !!selectedId,
    queryFn: ({ signal }) =>
      api(base + `tasks/${selectedId}/`, taskSchema, { signal }),
    refetchInterval: (query) =>
      query.state.data && pending.includes(query.state.data.state)
        ? 2000
        : false,
  });
  const candidateParams = new URLSearchParams({
    from: from ?? "",
    to: to ?? "",
    include_undated: String(undated),
  });
  const candidates = useQuery({
    queryKey: [base, "candidates", candidateParams.toString()],
    enabled: allowed && open && !packetId,
    queryFn: ({ signal }) =>
      api(base + "candidates/?" + candidateParams, candidatesSchema, {
        signal,
      }),
  });
  const create = useMutation({
    mutationFn: () =>
      post(
        base + "tasks/",
        taskSchema,
        packetId
          ? { kind, packet_id: packetId }
          : {
              kind,
              from,
              to,
              include_undated: undated,
              selected: selected.map(({ kind, id, revision }) => ({
                kind,
                id,
                revision,
              })),
            },
      ),
    onSuccess: (value) => {
      setActive(value.id);
      setEdits({});
      cache.setQueryData([base, "task", value.id], value);
      void history.refetch();
    },
  });
  const task = detail.data;
  const review = useMutation({
    mutationFn: (outcome: "kept" | "edited" | "rejected") =>
      post(base + `tasks/${selectedId}/review/`, taskSchema, {
        outcome,
        ...(outcome === "edited"
          ? {
              texts: task!.result!.items.map(
                (item, i) => edits[i] ?? item.text,
              ),
            }
          : {}),
      }),
    onSuccess: (value) => cache.setQueryData([base, "task", value.id], value),
  });
  if (!allowed) return null;
  const busy = create.isPending || (!!task && pending.includes(task.state));
  const displayed = task?.review?.planning_draft ?? task?.result?.items ?? [];
  return (
    <section
      className="panel form-section"
      aria-label={packetId ? "Follow-up planning" : "Explore health history"}
    >
      <h2>
        {packetId ? "Find follow-up actions" : "Explore my health history"}
      </h2>
      <p>
        {packetId
          ? "Apertus can find instructions explicitly written in this frozen visit selection. All selected documents need readable written reports."
          : "Choose the exact observations and records Apertus may organize. It will return source-linked excerpts from this selection."}
      </p>
      <p>
        Private and unconfirmed until you review. This action does not change
        records, schedule care, send reminders or share information.
      </p>
      {!packetId && (
        <>
          <p>
            Range: {from} to {to}. Choose at most twelve items. Partial dates
            keep their original precision.
          </p>
          <Button variant="secondary" onPress={() => setOpen(!open)}>
            {open ? "Hide evidence choices" : "Choose evidence"}
          </Button>
          {open && (
            <>
              <label className="care-checkbox">
                <input
                  type="checkbox"
                  checked={undated}
                  disabled={busy}
                  onChange={(e) => {
                    setUndated(e.target.checked);
                    setSelected([]);
                  }}
                />{" "}
                Include evidence with unknown dates
              </label>
              {candidates.isPending && (
                <Loading>Finding your evidence choices…</Loading>
              )}
              {candidates.error && (
                <Notice live tone="error">
                  {candidates.error.message}
                </Notice>
              )}
              {candidates.data?.browse_capped && (
                <Notice tone="warning">
                  Only the latest {candidates.data.limit_per_type} entries of
                  each type were checked. This list may omit older evidence.
                </Notice>
              )}
              {candidates.data?.items.length === 0 && (
                <p>
                  No evidence found in this browse window. This does not
                  establish absence from your history.
                </p>
              )}
              <fieldset>
                <legend>
                  Explicit evidence selection · {selected.length}/12
                </legend>
                {candidates.data?.items.map((item) => {
                  const checked = selected.some(
                    (row) => row.kind === item.kind && row.id === item.id,
                  );
                  return (
                    <label className="care-checkbox" key={item.kind + item.id}>
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={busy || (!checked && selected.length >= 12)}
                        onChange={() =>
                          setSelected(
                            checked
                              ? selected.filter(
                                  (row) =>
                                    row.kind !== item.kind ||
                                    row.id !== item.id,
                                )
                              : [...selected, item],
                          )
                        }
                      />
                      {item.title} · {item.kind} · {dateLabel(item.occurrence)}{" "}
                      · revision {item.revision} ·{" "}
                      {item.provenance.replaceAll("_", " ")}
                    </label>
                  );
                })}
              </fieldset>
            </>
          )}
        </>
      )}
      <div className="actions">
        <Button
          isDisabled={busy || (!packetId && selected.length === 0)}
          onPress={() => create.mutate()}
        >
          {create.isPending
            ? "Saving request…"
            : packetId
              ? "Find follow-up actions"
              : "Explore selected evidence"}
        </Button>
      </div>
      {create.error && (
        <Notice live tone="error">
          {create.error.message}
        </Notice>
      )}
      {history.error && <Notice tone="error">{history.error.message}</Notice>}
      {!!history.data?.tasks.length && (
        <details>
          <summary>Previous private requests</summary>
          {history.data.tasks.map((row) => (
            <div key={row.id}>
              <Button
                variant="quiet"
                onPress={() => {
                  setActive(row.id);
                  setEdits({});
                }}
              >
                {new Date(row.created_at).toLocaleString()} · {row.state}
              </Button>
            </div>
          ))}
        </details>
      )}
      {detail.error && (
        <Notice live tone="error">
          {detail.error.message}
        </Notice>
      )}
      {task && (
        <div aria-live="polite">
          {pending.includes(task.state) && (
            <Notice>
              {task.state === "processing"
                ? "Apertus is working on your selected evidence."
                : task.state === "waiting_model"
                  ? "Waiting for the configured local model."
                  : "Request queued for the existing worker."}{" "}
              Your sources are unchanged.
            </Notice>
          )}
          {task.state === "failed" && (
            <Notice tone="error">
              The request could not complete ({task.error_code}). Your sources
              are unchanged. A new request requires your action.
            </Notice>
          )}
          {task.result && (
            <>
              <p>
                {task.coverage.scope} {task.coverage.selected_count} snapshots
                included; {task.coverage.truncated_sources} shortened.
              </p>
              {task.result.abstained && (
                <Notice>
                  No supported excerpts were returned for this selection.
                </Notice>
              )}
              {task.review?.outcome === "rejected" ? (
                <Notice>Proposal rejected. No planning draft was kept.</Notice>
              ) : (
                <ol>
                  {displayed.map((item, index) => (
                    <li key={index} className="form-section">
                      <h3>{categories[item.category]}</h3>
                      <p>
                        {item.source.provenance === "patient_reported"
                          ? "Patient-reported"
                          : "Document-sourced"}{" "}
                        · {dateLabel(item.source.occurrence)} ·{" "}
                        {item.source.date_meaning}
                      </p>
                      {item.source.use_status && (
                        <p>
                          Medication status:{" "}
                          {item.source.use_status.replaceAll("_", " ")}
                        </p>
                      )}
                      {task.review ? (
                        <p className="journal-writing">
                          {item.text}
                          {item.patient_edited && " (Patient edited)"}
                        </p>
                      ) : (
                        <TextAreaField
                          id={`care-ai-${task.id}-${index}`}
                          label={`Planning draft ${index + 1}`}
                          inputProps={{
                            value: edits[index] ?? item.text,
                            maxLength: 500,
                            onChange: (e) =>
                              setEdits({ ...edits, [index]: e.target.value }),
                          }}
                        />
                      )}
                      {item.citations.map((citation, i) => (
                        <blockquote key={i}>{citation.quote}</blockquote>
                      ))}
                      <a href={item.source.href}>
                        Open cited source · revision {item.source.revision}
                      </a>
                      {item.source.truncated && (
                        <p>The selected source excerpt was shortened.</p>
                      )}
                    </li>
                  ))}
                </ol>
              )}
              {!!task.result.limitations.length && (
                <p>
                  Limitations:{" "}
                  {task.result.limitations
                    .map((value) => value.replaceAll("_", " "))
                    .join(", ")}
                </p>
              )}
              {!task.review && (
                <div className="actions">
                  <Button
                    isDisabled={review.isPending}
                    onPress={() =>
                      review.mutate(
                        Object.keys(edits).length ? "edited" : "kept",
                      )
                    }
                  >
                    Keep private planning draft
                  </Button>
                  <Button
                    variant="secondary"
                    isDisabled={review.isPending}
                    onPress={() => review.mutate("rejected")}
                  >
                    Reject proposal
                  </Button>
                </div>
              )}
              {task.review && (
                <Notice>
                  Patient review: {task.review.outcome}. This remains a private
                  planning draft.
                </Notice>
              )}
              {review.error && (
                <Notice live tone="error">
                  {review.error.message}
                </Notice>
              )}
              <details>
                <summary>Request details</summary>
                <p>
                  Reference: {task.id}. Model: {task.model}. Generation:{" "}
                  {task.usage.inference_seconds?.toFixed(1) ?? "unknown"}{" "}
                  seconds. Queue:{" "}
                  {task.queue_wait_seconds?.toFixed(1) ?? "unknown"} seconds.
                  Total worker time:{" "}
                  {task.latency_seconds?.toFixed(1) ?? "unknown"} seconds.
                </p>
              </details>
            </>
          )}
        </div>
      )}
    </section>
  );
}
