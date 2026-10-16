import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import axe from "axe-core";
import { context, workspaceId } from "../../test/fixtures";
import CareIntelligence from "./CareIntelligence";

vi.mock("../../services/auth/session", () => ({
  usePatient: () => ({
    ...context,
    capabilities: [...context.capabilities, "manage_profile"],
  }),
}));
const sourceId = "77777777-7777-4777-8777-777777777777",
  taskId = "88888888-8888-4888-8888-888888888888";
const occurrence = { precision: "month", year: 2026, month: 10, day: null };
const quote = "Fictional symptom observation; no nausea.";
const json = (value: unknown) =>
  new Response(JSON.stringify(value), {
    headers: { "Content-Type": "application/json" },
  });
function setup(packet = false, enabled = true) {
  const posts: { url: string; body: Record<string, unknown> }[] = [];
  const item = {
    text: packet ? "Return for review on 2026-10-20." : quote,
    category: packet ? "documented_followup" : "source_excerpt",
    citations: [
      {
        evidence_id: "e1",
        quote: packet ? "Return for review on 2026-10-20." : quote,
        start: 0,
        end: quote.length,
        snapshot_sha256: "a".repeat(64),
      },
    ],
    source: {
      kind: packet ? "document" : "journal",
      source_id: sourceId,
      revision: 2,
      provenance: packet ? "document_sourced" : "patient_reported",
      occurrence,
      date_meaning: packet ? "Document date" : "Patient-reported occurrence",
      href: `/app/workspaces/${workspaceId}/journal/${sourceId}`,
      truncated: false,
    },
  };
  const task = {
    id: taskId,
    kind: packet ? "followup_actions" : "history_exploration",
    state: "queued",
    error_code: null,
    packet_revision_id: null,
    model: null,
    created_at: "2026-10-16T09:00:00Z",
    result: null,
    coverage: {
      selected_count: 1,
      truncated_sources: 0,
      scope: "Only explicitly selected evidence is included.",
    },
    latency_seconds: null,
    queue_wait_seconds: null,
    usage: {},
    review: null,
  };
  const completed = {
    ...task,
    state: "completed",
    model: "local-apertus",
    result: {
      items: [item],
      limitations: ["selected_evidence_only"],
      abstained: false,
      status: "private_unconfirmed",
    },
    latency_seconds: 12,
    queue_wait_seconds: 1,
    usage: { inference_seconds: 10 },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/status/"))
        return json({ enabled, selection_limit: 12 });
      if (url.includes("/candidates/?"))
        return json({
          items: [
            {
              kind: "journal",
              id: sourceId,
              revision: 2,
              title: "Fictional observation",
              occurrence,
              provenance: "patient_reported",
            },
          ],
          browse_capped: false,
          limit_per_type: 50,
          selection_limit: 12,
          coverage: "Selected evidence only",
        });
      if (init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        posts.push({ url, body });
        if (url.endsWith("/review/"))
          return json({
            ...completed,
            review: {
              outcome: body.outcome,
              planning_draft:
                body.outcome === "rejected"
                  ? null
                  : [
                      {
                        ...item,
                        text: body.texts?.[0] ?? item.text,
                        patient_edited: body.outcome === "edited",
                      },
                    ],
            },
          });
        return json(task);
      }
      if (url.includes("/tasks/?")) return json({ tasks: [] });
      if (url.endsWith(`/tasks/${taskId}/`)) return json(completed);
      throw new Error("Unexpected mocked path " + url);
    }),
  );
  const cache = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={cache}>
      <main>
        <h1>Comfort synthetic test</h1>
        <CareIntelligence
          {...(packet
            ? { packetId: sourceId }
            : { from: "2026-10-01", to: "2026-10-31" })}
        />
      </main>
    </QueryClientProvider>,
  );
  return { posts };
}
afterEach(() => vi.unstubAllGlobals());

it("selects exact history revisions, requests once, then keeps an edited private cited draft", async () => {
  const user = userEvent.setup(),
    { posts } = setup();
  await user.click(
    await screen.findByRole("button", { name: "Choose evidence" }),
  );
  await user.click(
    await screen.findByRole("checkbox", { name: /Fictional observation/ }),
  );
  expect(posts).toHaveLength(0);
  await user.click(
    screen.getByRole("button", { name: "Explore selected evidence" }),
  );
  const field = await screen.findByRole("textbox", {
    name: "Planning draft 1",
  });
  expect(field).toHaveValue(quote);
  expect(posts).toHaveLength(1);
  expect(posts[0].body.selected).toEqual([
    { kind: "journal", id: sourceId, revision: 2 },
  ]);
  await user.clear(field);
  await user.type(field, "My question for the visit.");
  await user.click(
    screen.getByRole("button", { name: "Save these notes for myself" }),
  );
  await waitFor(() => expect(posts).toHaveLength(2));
  expect(posts[1].body).toEqual({
    outcome: "edited",
    texts: ["My question for the visit."],
  });
  expect(await screen.findByText(/Patient review: edited/)).toBeVisible();
  expect(
    screen.getByRole("link", { name: /Open cited source/ }),
  ).toHaveAttribute(
    "href",
    `/app/workspaces/${workspaceId}/journal/${sourceId}`,
  );
  const result = await axe.run(document.body, {
    rules: { "color-contrast": { enabled: false } },
  });
  expect(result.violations).toEqual([]);
});

it("uses the frozen consultation packet and requires explicit review", async () => {
  const user = userEvent.setup(),
    { posts } = setup(true);
  const run = await screen.findByRole("button", {
    name: "Find follow-up actions",
  });
  expect(posts).toHaveLength(0);
  await user.click(run);
  expect(
    await screen.findByRole("heading", {
      name: "Documented follow-up request",
    }),
  ).toBeVisible();
  expect(posts[0].body).toEqual({
    kind: "followup_actions",
    packet_id: sourceId,
  });
  expect(posts).toHaveLength(1);
  await user.click(screen.getByRole("button", { name: "Reject proposal" }));
  expect(await screen.findByText(/Proposal rejected/)).toBeVisible();
  expect(posts[1].body).toEqual({ outcome: "rejected" });
});

it("does not expose incomplete features when the deployment gate is off", async () => {
  setup(false, false);
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  expect(
    screen.queryByRole("button", { name: "Choose evidence" }),
  ).not.toBeInTheDocument();
});
