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
const pending = new Set(["queued", "processing", "waiting_model"]);
export function TaskCard({ task }: { task: AssistantTask }) {
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
  return (
    <article className="panel stack">
      <h3>
        {task.kind === "search"
          ? "Related-record search"
          : task.kind === "packet_overview"
            ? "Visit overview draft"
            : "Term explanation"}
      </h3>
      <Notice tone={task.state === "failed" ? "warning" : "info"}>
        {{
          queued: "Your request is saved and queued.",
          processing:
            "Apertus is working. You can leave and return to this saved request.",
          waiting_model: "Your request is saved and waiting for model access.",
          completed: "AI suggestions · review against their sources.",
          failed:
            task.error_code === "no_readable_report_text"
              ? "Add a written report with readable text before requesting an overview. Your originals are unchanged."
              : task.error_code === "cancelled_by_user"
                ? "This request was cancelled."
                : "Apertus could not complete this request. Your originals are unchanged.",
          cancelled: "This request was cancelled.",
        }[task.state] ?? "Request saved."}
      </Notice>
      {task.sources.some(
        (source) =>
          !source.current_version || source.metadata_changed_since_request,
      ) && (
        <Notice tone="warning">
          Some originals or document details changed after this request. This
          draft still refers to its saved source versions.
        </Notice>
      )}
      <p>
        {typeof task.coverage.included_records === "number"
          ? `${task.coverage.included_records} source records included. `
          : ""}
        This request uses a bounded snapshot, not your complete health history.
      </p>
      {result?.abstained && (
        <p>
          No supported answer was returned. This does not establish that your
          history contains no relevant record.
        </p>
      )}
      {(result?.matches ?? []).map((match, index) => (
        <section key={index}>
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
      {(result?.items ?? []).map((item, index) => (
        <section key={index}>
          <p>{item.text}</p>
          {item.citations.map((citation, i) => (
            <blockquote className="quote" key={i}>
              <p>{citation.quote}</p>
              {citation.download_url && (
                <a href={citation.download_url}>Read the exact original</a>
              )}
            </blockquote>
          ))}
        </section>
      ))}
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
      <small>
        Citations are checked for source structure. They do not prove medical
        correctness.
      </small>
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
  const base = `/api/workspaces/${patient.id}/`;
  const client = useQueryClient();
  const status = useQuery({
    queryKey: ["assistant-status"],
    queryFn: ({ signal }) =>
      api(base + "assistant/status/", statusSchema, { signal }),
  });
  const tasks = useQuery({
    queryKey: ["assistant-tasks"],
    queryFn: ({ signal }) =>
      api(base + "assistant/tasks/", tasksSchema, { signal }),
    refetchInterval: (query) =>
      query.state.data?.tasks.some((task) => pending.has(task.state))
        ? 15000
        : false,
    refetchIntervalInBackground: false,
  });
  const mutation = useMutation({
    mutationFn: () =>
      post(
        base + "assistant/tasks/",
        taskSchema,
        packetId
          ? { kind: "packet_overview", parameters: { packet_id: packetId } }
          : { kind: "search", parameters: { query } },
      ),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["assistant-tasks"] }),
  });
  return (
    <section className="form-section">
      <h2>
        {packetId
          ? "Source-linked visit draft"
          : "Find related records with Apertus"}
      </h2>
      <p>
        Ask only when you need help. Results remain suggestions for your review.
      </p>
      <div className="actions form-section">
        <Button
          variant="secondary"
          isDisabled={
            mutation.isPending ||
            (!packetId && query.trim().length < 3) ||
            status.isError
          }
          onPress={() => mutation.mutate()}
        >
          {packetId ? "Request an overview draft" : "Find related records"}
        </Button>
        {status.data && !status.data.configured && (
          <span>Requests will wait until model access is configured.</span>
        )}
      </div>
      {mutation.isError && (
        <Notice tone="error" live>
          {mutation.error.message}
        </Notice>
      )}
      {mutation.isSuccess && (
        <Notice live>
          Request saved. You can return here to read its status.
        </Notice>
      )}
      {tasks.isError && <Notice tone="error">{tasks.error.message}</Notice>}
      <div className="task-list">
        {tasks.data?.tasks
          .filter((task) =>
            packetId
              ? task.kind === "packet_overview" && task.packet_id === packetId
              : task.kind === "search",
          )
          .map((task) => (
            <TaskCard key={task.id} task={task} />
          ))}
      </div>
    </section>
  );
}
