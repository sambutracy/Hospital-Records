import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { taskSchema, type AssistantTask } from "../../services/api/contracts";
import TaskHistory from "./TaskHistory";

function task(id: string, state: string, query: string, abstained = false) {
  return taskSchema.parse({
    id,
    packet_id: null,
    kind: "search",
    state,
    query,
    created_at: "2026-10-16T06:00:00Z",
    error_code: "",
    coverage: {},
    sources: [],
    result: state === "completed" ? { abstained } : null,
  });
}

const renderTask = (request: AssistantTask) => (
  <section aria-label={`${request.query} result`}>
    {request.query === "Family history"
      ? "Father had diabetes. Patient diagnosis is not documented."
      : `Saved result for ${request.query}`}
  </section>
);

describe("saved Apertus request presentation", () => {
  it("keeps active requests and the latest supported result visible, with older results collapsed", async () => {
    const user = userEvent.setup();
    const requests = [
      task("00000000-0000-4000-8000-000000000001", "queued", "New search"),
      task(
        "00000000-0000-4000-8000-000000000002",
        "completed",
        "No answer",
        true,
      ),
      task(
        "00000000-0000-4000-8000-000000000003",
        "completed",
        "Family history",
      ),
      task("00000000-0000-4000-8000-000000000004", "completed", "Older search"),
    ];
    render(<TaskHistory tasks={requests} renderTask={renderTask} />);

    expect(
      screen.getByRole("region", { name: "New search result" }),
    ).toBeVisible();
    expect(
      screen.getByRole("region", { name: "Family history result" }),
    ).toBeVisible();
    const oldDetails = screen.getByText("Older search").closest("details");
    const abstainedDetails = screen.getByText("No answer").closest("details");
    expect(oldDetails).not.toHaveAttribute("open");
    expect(abstainedDetails).not.toHaveAttribute("open");

    await user.click(screen.getByText("Older search"));
    expect(oldDetails).toHaveAttribute("open");
    expect(
      screen.getByRole("region", { name: "Older search result" }),
    ).toBeVisible();
    expect(
      screen.getByText(
        "Father had diabetes. Patient diagnosis is not documented.",
      ),
    ).toBeVisible();
  });

  it("keeps the latest completed abstention open when there is no supported result", () => {
    render(
      <TaskHistory
        tasks={[
          task(
            "00000000-0000-4000-8000-000000000005",
            "completed",
            "No supported match",
            true,
          ),
          task(
            "00000000-0000-4000-8000-000000000006",
            "failed",
            "Earlier failure",
          ),
        ]}
        renderTask={renderTask}
      />,
    );
    expect(
      screen.getByRole("region", { name: "No supported match result" }),
    ).toBeVisible();
    expect(
      screen.getByText("Earlier failure").closest("details"),
    ).not.toHaveAttribute("open");
  });
});
