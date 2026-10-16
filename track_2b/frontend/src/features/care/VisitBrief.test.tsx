import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ContextScope } from "../../services/auth/session";
import {
  taskSchema,
  visitBriefSchema,
  type VisitBriefResult,
} from "../../services/api/contracts";
import { context, recordId, versionId, workspaceId } from "../../test/fixtures";
import Assistant, { TaskCard } from "../records/Assistant";
import VisitBrief from "./VisitBrief";

afterEach(() => vi.restoreAllMocks());

const source = {
  quote: "Surgery scheduled for 2 January 2026.",
  source_version_id: versionId,
  label: "Fictional clinic note",
  date_label: "20 December 2025",
  provenance: "Documented in record",
  download_url: `/api/workspaces/${workspaceId}/versions/${versionId}/original/`,
};
const brief: VisitBriefResult = {
  representation: "visit_brief",
  abstained: false,
  packet_purpose: "Discuss hip pain and mobility",
  sections: [
    {
      id: "followup",
      title: "Pending decisions and follow-ups",
      priority: "high",
      items: [
        {
          text: "Surgery scheduled for 2 January 2026.",
          source_kind: "document",
          caution:
            "Historical plan; completion is not confirmed in these sources.",
          citations: [source],
        },
      ],
    },
    {
      id: "purpose",
      title: "Purpose of this visit",
      priority: "critical",
      items: [
        {
          text: "I want to discuss changes in walking.",
          source_kind: "patient",
          citations: [
            {
              quote: "I want to discuss changes in walking.",
              label: "Your visit note",
              date_label: "16 October 2026",
              provenance: "Patient reported",
            },
          ],
        },
      ],
    },
    {
      id: "basics",
      title: "Basic health information",
      priority: "contextual",
      items: [],
    },
  ],
  critical_gaps: [
    {
      id: "allergies",
      text: "Allergy status is not established by the selected sources.",
    },
  ],
  coverage_summary: {
    selected_documents: 2,
    represented_documents: 1,
    context_items: 1,
    truncated_documents: 1,
    duplicate_passages_merged: 1,
  },
  patient_context: true,
  generated_at: "2026-10-16T06:00:00Z",
  review_required: true,
  limitations: ["Selected sources may not include later changes."],
};
const queued = {
  id: recordId,
  packet_id: recordId,
  kind: "packet_overview",
  state: "queued",
  error_code: "",
  coverage: {},
  sources: [],
  result: null,
};

function requests() {
  const posted: Record<string, unknown>[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, options) => {
    if (String(input).endsWith("/status/"))
      return new Response(
        JSON.stringify({
          configured: true,
          model: "local-apertus",
          facility_search_enabled: false,
          worker: { available: true, state: "ready" },
        }),
      );
    if (options?.method === "POST") {
      posted.push(JSON.parse(String(options.body)));
      return new Response(JSON.stringify(queued), { status: 202 });
    }
    return new Response(
      JSON.stringify({ tasks: posted.length ? [queued] : [] }),
    );
  });
  return posted;
}

describe("Apertus visit brief", () => {
  it("preserves abstention and distinguishes copied preparation from an AI overview", () => {
    const result = visitBriefSchema.parse({
      ...brief,
      abstained: true,
      coverage_summary: { ...brief.coverage_summary, represented_documents: 0 },
      sections: brief.sections.filter((section) => section.id === "purpose"),
    });
    render(
      <ContextScope context={context}>
        <TaskCard
          task={taskSchema.parse({
            ...queued,
            state: "completed",
            result,
          })}
        />
      </ContextScope>,
    );
    expect(result.abstained).toBe(true);
    expect(
      screen.getByText("Request finished · no source overview returned."),
    ).toBeVisible();
    expect(
      screen.getByText(/Apertus did not select supported source evidence/),
    ).toBeVisible();
    expect(
      screen.getByText("I want to discuss changes in walking.", {
        selector: ".visit-brief-statement",
      }),
    ).toBeVisible();
    expect(
      screen.queryByText("Private AI draft · review before using or sharing."),
    ).not.toBeInTheDocument();
  });
  it("prioritizes the visit purpose, preserves historical uncertainty and exposes exact evidence on demand", async () => {
    const user = userEvent.setup();
    render(<VisitBrief result={brief} />);
    const headings = screen
      .getAllByRole("heading")
      .map((heading) => heading.textContent);
    expect(headings.indexOf("Purpose of this visit")).toBeLessThan(
      headings.indexOf("Pending decisions and follow-ups"),
    );
    expect(
      screen.queryByRole("heading", { name: "Basic health information" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Historical plan; completion is not confirmed/),
    ).toBeInTheDocument();
    expect(screen.getByText(/20 December 2025/)).toBeInTheDocument();
    expect(
      screen.getByText(/Allergy status is not established/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Fictional clinic note" }),
    ).toHaveAttribute("href", source.download_url);
    const sourceDetails = screen
      .getAllByText("Supporting excerpts")[1]
      .closest("details");
    expect(sourceDetails).not.toHaveAttribute("open");
    await user.click(screen.getAllByText("Supporting excerpts")[1]);
    expect(sourceDetails).toHaveAttribute("open");
  });

  it("keeps draft provenance distinct from source verification and warns when its private context changes", () => {
    const { container } = render(
      <ContextScope context={context}>
        <TaskCard
          task={taskSchema.parse({
            ...queued,
            state: "completed",
            context_changed_since_request: true,
            result: brief,
          })}
        />
      </ContextScope>,
    );
    expect(
      screen.getByText("Private AI draft · review before using or sharing."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Your private context changed/),
    ).toBeInTheDocument();
    expect(container.querySelectorAll(".visit-brief-statement")).toHaveLength(
      2,
    );
    expect(
      screen.queryByText(/Apertus selected these exact source excerpts/),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/1 of 2 selected records represented/),
    ).toBeInTheDocument();
  });

  it("rejects external or executable source links before rendering", () => {
    for (const href of [
      "javascript:alert(1)",
      "https://outside.example/record",
      "//outside.example/record",
    ]) {
      expect(
        visitBriefSchema.safeParse({
          ...brief,
          sections: [
            {
              ...brief.sections[0],
              items: [
                {
                  ...brief.sections[0].items[0],
                  citations: [{ ...source, href }],
                },
              ],
            },
          ],
        }).success,
      ).toBe(false);
    }
  });

  it("requires explicit private-context selection, submits patient intent and prevents duplicate queued requests", async () => {
    const posted = requests();
    render(
      <ContextScope
        context={{
          ...context,
          capabilities: [
            ...context.capabilities,
            "manage_profile",
            "manage_medications",
          ],
        }}
      >
        <Assistant packetId={recordId} />
      </ContextScope>,
    );
    const user = userEvent.setup();
    const checkboxes = await screen.findAllByRole("checkbox");
    expect(checkboxes).toHaveLength(4);
    checkboxes.forEach((checkbox) => expect(checkbox).not.toBeChecked());
    expect(screen.getByLabelText("Questions for this visit")).toHaveAttribute(
      "maxlength",
      "600",
    );
    await user.type(
      screen.getByLabelText("Purpose / What has changed or brings you here"),
      "Walking has become harder.",
    );
    await user.type(
      screen.getByLabelText("What matters to you"),
      "Staying independent.",
    );
    await user.type(
      screen.getByLabelText("Questions for this visit"),
      "What follow-up was documented?",
    );
    await user.click(
      screen.getByRole("checkbox", { name: "Medicines and prescriptions" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Create visit brief" }),
    );
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toEqual({
      kind: "packet_overview",
      parameters: {
        packet_id: recordId,
        visit_brief: true,
        visit_focus: "Walking has become harder.",
        patient_goals: "Staying independent.",
        patient_questions: "What follow-up was documented?",
        include_context: {
          profile: false,
          medications: true,
          journal: false,
          care: false,
        },
      },
    });
    await screen.findByText(/Your request is saved and queued/);
    expect(
      screen.getByRole("button", { name: "Create visit brief" }),
    ).toBeDisabled();
  });

  it("hides private context when acting without profile authority and submits no private opt-ins", async () => {
    const posted = requests();
    render(
      <ContextScope context={context}>
        <Assistant packetId={recordId} />
      </ContextScope>,
    );
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    await userEvent
      .setup()
      .click(await screen.findByRole("button", { name: "Create visit brief" }));
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({
      parameters: {
        include_context: {
          profile: false,
          medications: false,
          journal: false,
          care: false,
        },
      },
    });
  });

  it("does not offer medication context without separate medication authority", async () => {
    requests();
    render(
      <ContextScope
        context={{
          ...context,
          capabilities: [...context.capabilities, "manage_profile"],
        }}
      >
        <Assistant packetId={recordId} />
      </ContextScope>,
    );
    expect(await screen.findAllByRole("checkbox")).toHaveLength(3);
    expect(
      screen.queryByRole("checkbox", { name: "Medicines and prescriptions" }),
    ).not.toBeInTheDocument();
  });
});
