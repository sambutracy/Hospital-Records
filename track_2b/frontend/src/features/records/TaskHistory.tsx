import type { ReactNode } from "react";
import type { AssistantTask } from "../../services/api/contracts";

const activeStates = new Set(["queued", "processing", "waiting_model"]);
const statusLabels: Record<string, string> = {
  queued: "Queued",
  processing: "Processing",
  waiting_model: "Waiting for model",
  completed: "Completed",
  failed: "Could not complete",
  cancelled: "Cancelled",
};

export default function TaskHistory({
  tasks,
  renderTask,
}: {
  tasks: AssistantTask[];
  renderTask: (task: AssistantTask) => ReactNode;
}) {
  const latestResult =
    tasks.find(
      (task) =>
        task.state === "completed" && task.result && !task.result.abstained,
    ) ?? tasks.find((task) => task.state === "completed");

  return (
    <div
      className="task-list assistant-history"
      aria-label="Saved Apertus requests"
    >
      {tasks.map((task) =>
        activeStates.has(task.state) ||
        task.id === tasks[0]?.id ||
        task.id === latestResult?.id ? (
          <div key={task.id}>{renderTask(task)}</div>
        ) : (
          <details className="assistant-history-row" key={task.id}>
            <summary>
              <span className="assistant-history-title">
                {task.kind === "search"
                  ? task.query || "Related-record search"
                  : task.kind === "packet_overview"
                    ? "Visit draft"
                    : "Term explanation"}
              </span>
              <span className="assistant-history-status">
                {statusLabels[task.state] ?? "Saved"}
              </span>
              {task.created_at && (
                <time dateTime={task.created_at}>
                  {new Date(task.created_at).toLocaleDateString(undefined, {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                </time>
              )}
            </summary>
            {renderTask(task)}
          </details>
        ),
      )}
    </div>
  );
}
