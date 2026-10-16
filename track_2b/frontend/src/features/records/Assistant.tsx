import { useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePatient } from "../../services/auth/session";
import { api, post } from "../../services/api/client";
import {
  statusSchema,
  tasksSchema,
  taskSchema,
  type AssistantTask,
} from "../../services/api/contracts";
import { Button, Notice } from "../../design-system/primitives";
import TaskHistory from "./TaskHistory";
import VisitBrief from "../care/VisitBrief";
const pending = new Set(["queued", "processing", "waiting_model"]);
export function TaskCard({
  task,
  workerAvailable,
}: {
  task: AssistantTask;
  workerAvailable?: boolean;
}) {
  const patient = usePatient();
  const client = useQueryClient();
  const cancel = useMutation({
    mutationFn: () =>
      post(
        `/api/workspaces/${patient.id}/assistant/tasks/${task.id}/cancel/`,
        taskSchema,
        {},
      ),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["assistant-tasks"] }),
  });
  const result = task.result;
  const brief = result?.representation === "visit_brief" ? result : null;
  const legacyResult = result?.representation !== "visit_brief" ? result : null;
  return (
    <article className="panel stack assistant-task">
      <h3>
        {task.kind === "search"
          ? "Related-record search"
          : task.kind === "packet_overview"
            ? "Visit brief draft"
            : "Term explanation"}
      </h3>
      {task.kind === "search" && task.query && (
        <p>
          Search: <strong>{task.query}</strong>
        </p>
      )}
      <Notice tone={task.state === "failed" ? "warning" : "info"} live>
        {{
          queued:
            workerAvailable === false
              ? "Your request is saved. Processing is currently unavailable; it will remain queued until the service returns."
              : "Your request is saved and queued. Requests run one at a time.",
          processing:
            "Apertus is working. You can leave and return to this saved request.",
          waiting_model: "Your request is saved and waiting for model access.",
          completed:
            legacyResult?.limitation_code === "no_readable_report_text"
              ? "A readable report is needed. No AI overview was generated."
              : brief
                ? brief.abstained
                  ? "Request finished · no source overview returned."
                  : "Private AI draft · review before using or sharing."
                : "AI suggestions · review against their sources.",
          failed:
            task.error_code === "no_readable_report_text"
              ? "Add a written report with readable text before requesting an overview. Your originals are unchanged."
              : task.error_code === "cancelled_by_user"
                ? "This request was cancelled."
                : "Apertus could not complete this request. Your originals are unchanged.",
          cancelled: "This request was cancelled.",
        }[task.state] ?? "Request saved."}
      </Notice>
      {legacyResult?.limitation_code === "no_readable_report_text" && (
        <p>
          Wait for text reading to finish, or add a readable written report,
          then request a new overview. Dates and filenames alone cannot describe
          your health history.
        </p>
      )}
      {task.sources.some(
        (source) =>
          !source.current_version || source.metadata_changed_since_request,
      ) && (
        <Notice tone="warning">
          Some originals or document details changed after this request. This
          draft still refers to its saved source versions.
        </Notice>
      )}
      {task.context_changed_since_request && (
        <Notice tone="warning">
          Your private context changed after this request. This draft uses the
          details saved when you requested it.
        </Notice>
      )}
      {brief && <VisitBrief result={brief} />}
      {legacyResult?.abstained && (
        <p>
          No supported answer was returned. This does not establish that your
          history contains no relevant record.
        </p>
      )}
      {legacyResult?.representation === "source_excerpts" && (
        <p className="assistant-excerpt-intro">
          Apertus selected these exact source excerpts. Review the originals for
          context; this is not a complete summary.
          {legacyResult.evidence_coverage &&
            ` Excerpts cite ${legacyResult.evidence_coverage.cited_sources} of ${legacyResult.evidence_coverage.selected_sources} selected source records.`}
        </p>
      )}
      {(legacyResult?.matches ?? []).map((match, index) => (
        <section key={index} className="assistant-result">
          <span className="assistant-interpretation-label">
            AI selection note
          </span>
          <p>{match.reason}</p>
          {match.citations.map((citation, i) => (
            <blockquote key={i} className="quote">
              <p>{citation.quote}</p>
              {citation.download_url && (
                <a href={citation.download_url}>Read the exact original</a>
              )}
            </blockquote>
          ))}
        </section>
      ))}
      {(legacyResult?.items ?? []).map((item, index) => (
        <section key={index} className="assistant-result">
          {legacyResult?.representation === "source_excerpts" ? (
            <blockquote className="quote">
              {item.citations.map((citation, i) => (
                <p key={i}>{citation.quote}</p>
              ))}
              {item.citations[0]?.download_url && (
                <a href={item.citations[0].download_url}>
                  Read the exact original
                </a>
              )}
            </blockquote>
          ) : (
            <>
              <span className="assistant-interpretation-label">
                AI-generated draft
              </span>
              <p>{item.text}</p>
              {item.citations.map((citation, i) => (
                <blockquote className="quote" key={i}>
                  <p>{citation.quote}</p>
                  {citation.download_url && (
                    <a href={citation.download_url}>Read the exact original</a>
                  )}
                </blockquote>
              ))}
            </>
          )}
        </section>
      ))}
      <details className="assistant-request-details">
        <summary>Request details</summary>
        {task.created_at && (
          <p>
            <time dateTime={task.created_at}>
              Requested {new Date(task.created_at).toLocaleString()}
            </time>
          </p>
        )}
        {task.state === "completed" &&
          typeof task.latency_seconds === "number" && (
            <p>
              Completed in {Math.max(1, Math.round(task.latency_seconds))}{" "}
              seconds of processing.
            </p>
          )}
        {!brief && (
          <p>
            {typeof task.coverage.included_records === "number"
              ? `${task.coverage.included_records} source records included. `
              : ""}
            This request uses a bounded snapshot, not your complete health
            history.
          </p>
        )}
      </details>
      {pending.has(task.state) && (
        <Button
          variant="secondary"
          isDisabled={cancel.isPending}
          onPress={() => cancel.mutate()}
        >
          Cancel request
        </Button>
      )}
      {cancel.isError && (
        <Notice tone="error" live>
          {cancel.error.message}
        </Notice>
      )}
      {!brief && (
        <small>
          Citations are checked for source structure. They do not prove medical
          correctness.
        </small>
      )}
    </article>
  );
}
export default function Assistant({
  query = "",
  packetId,
}: {
  query?: string;
  packetId?: string;
}) {
  const patient = usePatient();
  const formId = useId();
  const [visitFocus, setVisitFocus] = useState("");
  const [patientGoals, setPatientGoals] = useState("");
  const [patientQuestions, setPatientQuestions] = useState("");
  const [includeContext, setIncludeContext] = useState({
    profile: false,
    medications: false,
    journal: false,
    care: false,
  });
  const canUsePrivateContext = patient.capabilities.includes("manage_profile");
  const canUseMedications =
    canUsePrivateContext && patient.capabilities.includes("manage_medications");
  const base = `/api/workspaces/${patient.id}/`;
  const client = useQueryClient();
  const status = useQuery({
    queryKey: ["assistant-status"],
    queryFn: ({ signal }) =>
      api(base + "assistant/status/", statusSchema, { signal }),
    refetchInterval: 10000,
  });
  const tasks = useQuery({
    queryKey: ["assistant-tasks"],
    queryFn: ({ signal }) =>
      api(base + "assistant/tasks/", tasksSchema, { signal }),
    refetchInterval: (query) =>
      query.state.data?.tasks.some((task) => pending.has(task.state))
        ? 3000
        : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: "always",
    refetchOnReconnect: "always",
  });
  const mutation = useMutation({
    mutationFn: () =>
      post(
        base + "assistant/tasks/",
        taskSchema,
        packetId
          ? {
              kind: "packet_overview",
              parameters: {
                packet_id: packetId,
                visit_brief: true,
                visit_focus: visitFocus.trim(),
                patient_goals: patientGoals.trim(),
                patient_questions: patientQuestions.trim(),
                include_context: {
                  profile: canUsePrivateContext && includeContext.profile,
                  medications: canUseMedications && includeContext.medications,
                  journal: canUsePrivateContext && includeContext.journal,
                  care: canUsePrivateContext && includeContext.care,
                },
              },
            }
          : { kind: "search", parameters: { query } },
      ),
    onSuccess: (task) => {
      client.setQueryData(
        ["assistant-tasks"],
        (previous: { tasks: AssistantTask[] } | undefined) => ({
          tasks: [
            task,
            ...(previous?.tasks ?? []).filter((item) => item.id !== task.id),
          ],
        }),
      );
      void client.invalidateQueries({ queryKey: ["assistant-tasks"] });
    },
  });
  const activeRequest = tasks.data?.tasks.find(
    (task) =>
      task.kind === (packetId ? "packet_overview" : "search") &&
      pending.has(task.state),
  );
  return (
    <section className="form-section">
      <h2>
        {packetId
          ? "Prepare with Apertus"
          : "Find related records with Apertus"}
      </h2>
      <p>
        {packetId
          ? "Apertus organizes your selected records into a visit brief. Add what you want to discuss."
          : "Ask only when you need help. Results remain suggestions for your review."}
      </p>
      {packetId && (
        <div className="visit-brief-form form-section">
          <label className="field" htmlFor={`${formId}-purpose`}>
            <span>Purpose / What has changed or brings you here</span>
            <textarea
              id={`${formId}-purpose`}
              value={visitFocus}
              maxLength={600}
              rows={3}
              onChange={(event) => setVisitFocus(event.target.value)}
              disabled={mutation.isPending}
            />
          </label>
          <div className="form-grid">
            <label className="field" htmlFor={`${formId}-goals`}>
              <span>What matters to you</span>
              <textarea
                id={`${formId}-goals`}
                value={patientGoals}
                maxLength={600}
                rows={3}
                onChange={(event) => setPatientGoals(event.target.value)}
                disabled={mutation.isPending}
              />
            </label>
            <label className="field" htmlFor={`${formId}-questions`}>
              <span>Questions for this visit</span>
              <textarea
                id={`${formId}-questions`}
                value={patientQuestions}
                maxLength={600}
                rows={3}
                onChange={(event) => setPatientQuestions(event.target.value)}
                disabled={mutation.isPending}
              />
            </label>
          </div>
          {canUsePrivateContext && (
            <fieldset className="visit-brief-context">
              <legend>Add private context (optional)</legend>
              <p id={`${formId}-privacy`}>
                Used only for this draft. These details are not added to shared
                records.
              </p>
              {(
                [
                  ["profile", "Personal health details"],
                  ...(canUseMedications
                    ? [["medications", "Medicines and prescriptions"]]
                    : []),
                  ["journal", "Journal observations"],
                  ["care", "Conditions and care team"],
                ] as [keyof typeof includeContext, string][]
              ).map(([key, label]) => (
                <label className="checkbox" key={key}>
                  <input
                    type="checkbox"
                    checked={includeContext[key]}
                    onChange={(event) =>
                      setIncludeContext((current) => ({
                        ...current,
                        [key]: event.target.checked,
                      }))
                    }
                    aria-describedby={`${formId}-privacy`}
                    disabled={mutation.isPending}
                  />
                  {label}
                </label>
              ))}
            </fieldset>
          )}
        </div>
      )}
      <div className="actions form-section">
        <Button
          variant="secondary"
          isDisabled={
            mutation.isPending ||
            !!activeRequest ||
            (!packetId && query.trim().length < 3) ||
            status.isError
          }
          onPress={() => mutation.mutate()}
        >
          {mutation.isPending
            ? "Saving request…"
            : packetId
              ? "Create visit brief"
              : "Find related records"}
        </Button>
        <Button
          variant="quiet"
          isDisabled={tasks.isFetching}
          onPress={() => void tasks.refetch()}
        >
          Refresh results
        </Button>
        {status.data && !status.data.configured && (
          <span>Requests will wait until model access is configured.</span>
        )}
        {status.data?.configured && status.data.worker?.available === false && (
          <Notice tone="warning">
            Processing is currently unavailable. Saved requests will stay queued
            until the service returns.
          </Notice>
        )}
      </div>
      {mutation.isError && (
        <Notice tone="error" live>
          {mutation.error.message}
        </Notice>
      )}
      {activeRequest && packetId && activeRequest.packet_id !== packetId && (
        <Notice>
          Another visit overview is in progress.{" "}
          <a
            href={`/app/workspaces/${patient.id}/care/${activeRequest.packet_id}`}
          >
            Open its saved visit selection
          </a>
          .
        </Notice>
      )}
      {mutation.isSuccess && (
        <Notice live>
          Request saved. You can return here to read its status.
        </Notice>
      )}
      {tasks.isError && <Notice tone="error">{tasks.error.message}</Notice>}
      <TaskHistory
        tasks={(tasks.data?.tasks ?? []).filter((task) =>
          packetId
            ? task.kind === "packet_overview" && task.packet_id === packetId
            : task.kind === "search",
        )}
        renderTask={(task) => (
          <TaskCard
            task={task}
            workerAvailable={status.data?.worker?.available}
          />
        )}
      />
    </section>
  );
}
