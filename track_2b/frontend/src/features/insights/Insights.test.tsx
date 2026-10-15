import {
  render,
  screen,
  within,
  waitFor,
  configure,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import axe from "axe-core";
import App from "../../app/App";
import { SessionProvider } from "../../services/auth/session";
import { context, workspaceId, versionId, recordId } from "../../test/fixtures";
import type { Observations, TimelineItem } from "./contracts";
configure({ asyncUtilTimeout: 5000 });
const eventId = "77777777-7777-4777-8777-777777777777";
const unknown = {
  precision: "unknown" as const,
  year: null,
  month: null,
  day: null,
};
const occurrence = {
  precision: "day" as const,
  year: 2026,
  month: 10,
  day: 16,
};
const journal: TimelineItem = {
  id: `journal:${eventId}`,
  kind: "journal",
  source_id: eventId,
  workspace_id: workspaceId,
  title: "Symptom observation",
  description: "Fictional intermittent headache",
  occurrence,
  date_meaning: "Patient-reported occurrence",
  recorded_at: "2026-10-16T09:00:00Z",
  provenance: "patient_reported",
  review_status: "Patient-authored observation",
  visibility: "private",
  href: `/app/workspaces/${workspaceId}/journal/${eventId}`,
  original_url: null,
  source_version_id: null,
  concern_id: null,
  episode_id: null,
  details: [{ label: "Severity", value: "0 / 10" }],
};
const documentItem: TimelineItem = {
  ...journal,
  id: `document:${versionId}`,
  kind: "document",
  source_id: versionId,
  title: "fictional-lab.pdf",
  description: "Lab report · Fictional Clinic",
  occurrence: { precision: "month", year: 2026, month: 10, day: null },
  date_meaning: "Patient-reviewed document date",
  provenance: "uploaded_record",
  review_status: "Patient-reviewed details; not clinical verification",
  href: `/app/workspaces/${workspaceId}/records/${recordId}`,
  source_version_id: versionId,
  original_url: `/api/workspaces/${workspaceId}/versions/${versionId}/original/`,
  details: [],
};
const summary: Observations = {
  contract_version: 1,
  from: "2026-10-01",
  to: "2026-10-04",
  concern_id: null,
  exact_dated_observations: 4,
  days_with_observations: 3,
  days_in_range: 4,
  days_without_entries: 1,
  scored_observations: 3,
  unscored_observations: 1,
  partial_date_observations_excluded: 1,
  undated_observations_excluded: 2,
  chart_ready: true,
  method: "active_patient_reported_symptom_entries_by_exact_local_date_v1",
  interpretation: "No inference",
  bins: [
    {
      date: "2026-10-01",
      observations: 2,
      scored_observations: 1,
      severity_min: 0,
      severity_max: 0,
    },
    {
      date: "2026-10-02",
      observations: 0,
      scored_observations: 0,
      severity_min: null,
      severity_max: null,
    },
    {
      date: "2026-10-03",
      observations: 1,
      scored_observations: 1,
      severity_min: 4,
      severity_max: 4,
    },
    {
      date: "2026-10-04",
      observations: 1,
      scored_observations: 1,
      severity_min: 3,
      severity_max: 3,
    },
  ],
};
function setup({
  permitted = true,
  fail = false,
  empty = false,
}: { permitted?: boolean; fail?: boolean; empty?: boolean } = {}) {
  const requests: Array<{ url: string; data: unknown }> = [];
  let failTimeline = fail;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (path, init) => {
    const url = String(path);
    const data = init?.body ? JSON.parse(String(init.body)) : null;
    requests.push({ url, data });
    const json = (value: unknown, status = 200) =>
      new Response(JSON.stringify(value), { status });
    if (url === "/api/session/")
      return json({
        contract_version: 1,
        actor: { id: workspaceId, display_name: "Fictional patient" },
        contexts: [
          {
            ...context,
            capabilities: [
              ...context.capabilities,
              ...(permitted ? ["manage_profile"] : []),
            ],
          },
        ],
        default_context_id: workspaceId,
        expires_at: Date.now() / 1000 + 300,
        csrf_token: "csrf-test",
        supported_context_kinds: ["patient"],
      });
    if (url.endsWith("/care/concerns/")) return json({ items: [] });
    if (url.endsWith("/episodes/")) return json({ episodes: [] });
    if (url.includes("/insights/observations/?"))
      return json(
        empty
          ? {
              ...summary,
              exact_dated_observations: 0,
              days_with_observations: 0,
              days_without_entries: 4,
              scored_observations: 0,
              unscored_observations: 0,
              chart_ready: false,
              bins: summary.bins.map((row) => ({
                ...row,
                observations: 0,
                scored_observations: 0,
                severity_min: null,
                severity_max: null,
              })),
            }
          : summary,
      );
    if (url.includes("/insights/timeline/?")) {
      if (failTimeline) {
        failTimeline = false;
        return new Response("", { status: 503 });
      }
      const params = new URL(url, "http://localhost").searchParams;
      const page = Number(params.get("page"));
      const undated = params.get("date_scope") === "undated";
      return json({
        contract_version: 1,
        items: empty
          ? []
          : undated
            ? [{ ...documentItem, occurrence: unknown }]
            : page === 1
              ? [journal, documentItem]
              : [{ ...journal, title: "Another fictional observation" }],
        page,
        next_page: page === 1 && !undated ? 2 : null,
        dated_count: empty ? 0 : 3,
        undated_count: empty ? 0 : 1,
        date_scope: undated ? "undated" : "dated",
        generated_at: "2026-10-16T09:00:00Z",
        medications_included: true,
        coverage: {
          current_document_versions_only: true,
          drafts_excluded: true,
          archived_entries_excluded: true,
          concern_links_are_explicit: true,
          episode_dates_not_inferred: true,
        },
      });
    }
    if (url.endsWith(`/journal/${eventId}/`))
      return json({
        contract_version: 1,
        id: eventId,
        revision: 1,
        status: "active",
        created_at: journal.recorded_at,
        updated_at: journal.recorded_at,
        created_by_id: workspaceId,
        updated_by_id: workspaceId,
        provenance: "patient_reported",
        visibility: "private",
        values: {
          category: "symptom",
          description: journal.description,
          occurrence,
          time: null,
          timezone: "",
          fold: null,
          severity: 0,
          concern_id: null,
        },
        occurred_at: null,
      });
    if (url.endsWith("/journal/draft/"))
      return json({ contract_version: 1, draft: null });
    if (url.endsWith("/history/"))
      return json({ contract_version: 1, truncated: false, history: [] });
    if (url.endsWith("/packets/"))
      return json(
        {
          id: recordId,
          purpose: "Fictional visit",
          revision_id: versionId,
          approved_at: journal.recorded_at,
          items: [],
          access: "private",
        },
        201,
      );
    if (url.endsWith(`/packets/${recordId}/`))
      return json({
        id: recordId,
        purpose: "Fictional visit",
        revision_id: versionId,
        approved_at: journal.recorded_at,
        items: [],
        access: "private",
      });
    return new Response("", { status: 404 });
  });
  const app = render(
    <MemoryRouter initialEntries={[`/workspaces/${workspaceId}/insights`]}>
      <SessionProvider>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  );
  return { ...app, requests };
}
afterEach(() => vi.restoreAllMocks());

it("opens the exact private Journal observation from the mixed timeline", async () => {
  const user = userEvent.setup();
  setup();
  await screen.findByRole("heading", { name: "Care timeline" });
  expect(
    await screen.findByText(
      "Patient-reviewed details; not clinical verification",
      { exact: false },
    ),
  ).toBeVisible();
  expect(
    screen.getByRole("link", { name: "Open exact original" }),
  ).toHaveAttribute("href", documentItem.original_url);
  await user.click(screen.getByRole("link", { name: "Open observation" }));
  expect(
    await screen.findByRole("heading", { name: "Journal observation" }),
  ).toBeVisible();
  expect(await screen.findByText(journal.description)).toBeVisible();
  expect(screen.getByRole("button", { name: "Correct entry" })).toBeEnabled();
  await user.click(screen.getByText("Correction history"));
  expect(
    await screen.findByRole("link", { name: "Back to Insights" }),
  ).toBeVisible();
});

it("preserves a zero score, missing scores and unrecorded dates in the accessible data table", async () => {
  const user = userEvent.setup();
  const { container } = setup();
  await screen.findByText("Recorded observations by date");
  await user.click(
    screen.getByText("View observation data, including unrecorded days"),
  );
  const zero = screen.getByRole("row", { name: "2026-10-01 2 1 0" });
  expect(zero).toBeVisible();
  expect(
    screen.getByRole("row", {
      name: "2026-10-02 No entries recorded 0 Not recorded",
    }),
  ).toBeVisible();
  expect(
    screen.getByText(/Blank days do not mean symptom-free days/),
  ).toBeVisible();
  const audit = await axe.run(container, {
    rules: { "color-contrast": { enabled: false } },
  });
  expect(audit.violations).toEqual([]);
}, 15000);

it("separates undated entries and applies timeline filters only when requested", async () => {
  const user = userEvent.setup();
  const { requests } = setup();
  await screen.findByRole("link", { name: "Open observation" });
  await user.click(screen.getByText("Refine the care timeline"));
  await user.selectOptions(screen.getByLabelText("Event type"), "document");
  expect(requests.filter((r) => r.url.includes("/timeline/?")).length).toBe(1);
  await user.click(screen.getByRole("button", { name: "Apply filters" }));
  await waitFor(() =>
    expect(requests.some((r) => r.url.includes("kind=document"))).toBe(true),
  );
  await user.click(screen.getByRole("button", { name: /^Undated/ }));
  expect(
    await screen.findByText(/cannot be placed inside the chosen date range/),
  ).toBeVisible();
  await waitFor(() =>
    expect(requests.some((r) => r.url.includes("date_scope=undated"))).toBe(
      true,
    ),
  );
  expect(
    await screen.findByText("Date unknown", { exact: false }),
  ).toBeVisible();
});

it("saves only selected exact documents after confirmation, without AI or sharing", async () => {
  const user = userEvent.setup();
  const { requests } = setup();
  await user.click(
    await screen.findByRole("checkbox", { name: /Include fictional-lab.pdf/ }),
  );
  await user.type(
    screen.getByLabelText("Purpose of your visit"),
    "Fictional visit",
  );
  await user.click(
    screen.getByRole("button", { name: "Prepare private visit selection" }),
  );
  expect(requests.filter((r) => r.data)).toHaveLength(0);
  const dialog = screen.getByRole("dialog");
  expect(
    within(dialog).getByText(/does not share information or send a request/),
  ).toBeVisible();
  await user.click(
    within(dialog).getByRole("button", { name: "Save private selection" }),
  );
  await waitFor(() =>
    expect(requests.filter((r) => r.data)).toEqual([
      {
        url: `/api/workspaces/${workspaceId}/packets/`,
        data: { purpose: "Fictional visit", source_version_ids: [versionId] },
      },
    ]),
  );
  expect(requests.some((r) => /assistant|grants/.test(r.url) && r.data)).toBe(
    false,
  );
});

it("paginates history and recovers from a timeline error", async () => {
  const user = userEvent.setup();
  setup({ fail: true });
  await user.click(
    await screen.findByRole("button", { name: "Retry timeline" }),
  );
  await screen.findByRole("link", { name: "Open observation" });
  await user.click(screen.getByRole("button", { name: "Next timeline page" }));
  expect(
    await screen.findByRole("heading", {
      name: "Another fictional observation",
    }),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Next timeline page" }),
  ).toBeDisabled();
});

it("keeps empty history and insufficient data truthful", async () => {
  setup({ empty: true });
  expect(
    await screen.findByText(/not yet observations on three different dates/),
  ).toBeVisible();
  expect(
    await screen.findByRole("heading", {
      name: "Nothing recorded in this view",
    }),
  ).toBeVisible();
  expect(
    screen.queryByText("Recorded observations by date"),
  ).not.toBeInTheDocument();
});

it("does not fetch private Insights without the required acting capability", async () => {
  const { requests } = setup({ permitted: false });
  expect(
    await screen.findByText(
      "Your current context does not permit access to this private history.",
    ),
  ).toBeVisible();
  expect(requests.some((r) => r.url.includes("/insights/"))).toBe(false);
});
