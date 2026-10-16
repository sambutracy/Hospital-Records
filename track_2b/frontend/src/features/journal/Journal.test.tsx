import {
  act,
  configure,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import axe from "axe-core";
import App from "../../app/App";
import { SessionProvider } from "../../services/auth/session";
import { context, workspaceId } from "../../test/fixtures";
import {
  initialFields,
  localDay,
  toValues,
  type Draft,
  type Fields,
  type JournalEvent,
} from "./contracts";

configure({ asyncUtilTimeout: 5000 });
const id = "77777777-7777-4777-8777-777777777777";
const concernId = "88888888-8888-4888-8888-888888888888";
const aiId = "99999999-9999-4999-8999-999999999999";
const timestamp = "2026-10-16T09:00:00Z";
function HistoryControls() {
  const navigate = useNavigate();
  return (
    <div>
      <button onClick={() => navigate(-1)}>Browser back</button>
      <button onClick={() => navigate(1)}>Browser forward</button>
    </div>
  );
}
function event(fields = initialFields(localDay())): JournalEvent {
  return {
    contract_version: 1,
    id,
    revision: 1,
    status: "active",
    created_at: timestamp,
    updated_at: timestamp,
    created_by_id: workspaceId,
    updated_by_id: workspaceId,
    provenance: "patient_reported",
    visibility: "private",
    values: toValues({
      ...fields,
      description: fields.description || "Fictional observation",
    }),
    occurred_at: null,
  };
}
function setup(
  options: {
    seed?: JournalEvent;
    draft?: Draft;
    fail?: "conflict" | "network" | "draft-conflict";
    manage?: boolean;
    seconds?: number;
    aiWarnings?: string[];
  } = {},
) {
  const stored = {
    items: options.seed ? [options.seed] : [],
    draft: options.draft ?? (null as Draft | null),
  };
  type Payload = {
    fields: Fields;
    event_id: string | null;
    base_revision: number;
    expected_revision: number;
    values: JournalEvent["values"];
    status: JournalEvent["status"];
    draft_revision?: number;
    outcome?: "accepted" | "edited" | "rejected" | "abandoned";
  };
  const writes: Array<{ path: string; data: Payload }> = [];
  let conflict = options.fail === "conflict";
  let draftConflict = options.fail === "draft-conflict";
  let aiPayload: Record<string, unknown> | null = null;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (path, init) => {
    const url = String(path),
      data: Payload | null = init?.body ? JSON.parse(String(init.body)) : null;
    if (url === "/api/session/")
      return new Response(
        JSON.stringify({
          contract_version: 1,
          actor: { id: workspaceId, display_name: "Fictional patient" },
          contexts: [
            {
              ...context,
              capabilities: [
                ...context.capabilities,
                ...(options.manage === false ? [] : ["manage_profile"]),
              ],
            },
          ],
          default_context_id: workspaceId,
          expires_at: Date.now() / 1000 + (options.seconds ?? 300),
          csrf_token: "csrf-test",
          supported_context_kinds: ["patient"],
        }),
      );
    if (url.endsWith("/care/concerns/"))
      return new Response(
        JSON.stringify({
          items: [
            {
              id: concernId,
              revision: 1,
              status: "active",
              updated_at: timestamp,
              provenance: "patient_reported",
              access_effect: "none",
              values: {
                title: "Fictional headache concern",
                description: "",
                kind: "investigation",
                certainty: "unconfirmed",
                onset: {
                  precision: "unknown",
                  year: null,
                  month: null,
                  day: null,
                },
              },
            },
          ],
        }),
      );
    if (url.endsWith("/journal/ai/requests/")) {
      if (!data) return new Response(JSON.stringify({ requests: aiPayload ? [aiPayload] : [] }));
      const draftRevision = data.draft_revision ?? stored.draft?.revision ?? 0;
      aiPayload = {
        id: aiId,
        draft_revision: draftRevision,
        state: "queued",
        error_code: null,
        created_at: timestamp,
        started_at: null,
        finished_at: null,
        model: null,
        prompt_version: null,
        latency_seconds: null,
        queue_wait_seconds: null,
        inference_seconds: null,
        validation_seconds: null,
        stale: false,
        expired: false,
        review: null,
        proposal: null,
      };
      return new Response(JSON.stringify(aiPayload), { status: 202 });
    }
    if (url.endsWith(`/journal/ai/requests/${aiId}/`)) {
      if (data && aiPayload) {
        if (data.outcome === "accepted" || data.outcome === "edited") {
          stored.draft = {
            id,
            revision: (stored.draft?.revision ?? 0) + 1,
            event_id: null,
            base_revision: 0,
            fields: data.fields!,
            updated_at: timestamp,
          };
        }
        aiPayload = {
          ...(aiPayload as Record<string, unknown>),
          stale: data.outcome === "accepted" || data.outcome === "edited",
          review: data.outcome,
          proposal: null,
        };
        return new Response(JSON.stringify(aiPayload));
      }
      aiPayload = {
        ...(aiPayload as Record<string, unknown>),
        state: "completed",
        started_at: timestamp,
        finished_at: timestamp,
        model: "Apertus v1.5 8B",
        prompt_version: "journal-interpretation-v1",
        latency_seconds: 0.8,
        queue_wait_seconds: 0.1,
        inference_seconds: 0.7,
        validation_seconds: 0.01,
        proposal: {
          fields: {
            ...initialFields(localDay(), "symptom"),
            description: stored.draft?.fields.description ?? "Headache and pain was 6/10.",
            precision: "unknown",
            year: "",
            month: "",
            day: "",
            severity: "6",
          },
          evidence: {
            category: { quote: "Headache", start: 0, end: 8 },
            severity: { quote: "6/10", start: 17, end: 21, origin: "source_extraction" },
          },
          unknown: ["Medication name"],
          ambiguities: options.aiWarnings ?? [],
          schema_version: "journal-proposal-v1",
          model: "Apertus v1.5 8B",
          generated_at: timestamp,
          expires_at: "2026-10-23T09:00:00Z",
          review: null,
        },
      };
      return new Response(JSON.stringify(aiPayload));
    }
    if (data) writes.push({ path: url, data });
    if (url.endsWith("/journal/draft/")) {
      if (data) {
        if (options.fail === "network") throw new Error("Offline");
        if (draftConflict) {
          draftConflict = false;
          stored.draft = {
            id,
            revision: 1,
            event_id: null,
            base_revision: 0,
            fields: {
              ...initialFields(localDay()),
              description: "Another fictional draft",
            },
            updated_at: timestamp,
          };
          return new Response("", { status: 409 });
        }
        stored.draft = {
          id,
          revision: (stored.draft?.revision ?? 0) + 1,
          event_id: data.event_id,
          base_revision: data.base_revision,
          fields: data.fields,
          updated_at: timestamp,
        };
      }
      return new Response(
        JSON.stringify({ contract_version: 1, draft: stored.draft }),
      );
    }
    if (url.endsWith("/draft/discard/")) {
      stored.draft = null;
      return new Response(JSON.stringify({ discarded: true }));
    }
    if (url.includes("/history/"))
      return new Response(
        JSON.stringify({
          contract_version: 1,
          truncated: false,
          history: [
            {
              revision: 1,
              actor_id: workspaceId,
              recorded_at: timestamp,
              snapshot: {
                description: "Earlier fictional note",
                category: "note",
                status: "active",
                occurrence: stored.items[0].values.occurrence,
                severity: null,
                timezone_name: "UTC",
              },
            },
          ],
        }),
      );
    if (url.endsWith("/status/") && data) {
      stored.items[0] = {
        ...stored.items[0],
        status: data.status,
        revision: stored.items[0].revision + 1,
      };
      return new Response(JSON.stringify(stored.items[0]));
    }
    if (url.endsWith(`/journal/${id}/`)) {
      if (data) {
        if (conflict) {
          conflict = false;
          stored.items[0] = {
            ...stored.items[0],
            revision: 2,
            values: {
              ...stored.items[0].values,
              description: "Concurrent correction",
            },
          };
          return new Response("", { status: 409 });
        }
        stored.items[0] = {
          ...stored.items[0],
          revision: data.expected_revision + 1,
          values: data.values,
        };
        stored.draft = null;
      }
      return new Response(JSON.stringify(stored.items[0]));
    }
    if (url.includes("/journal/?")) {
      const params = new URL(url, "http://localhost").searchParams;
      return new Response(
        JSON.stringify({
          contract_version: 1,
          items: stored.items.filter(
            (item) => item.status === params.get("status"),
          ),
          next_page: null,
          from: params.get("from"),
          to: params.get("to"),
        }),
      );
    }
    if (url.endsWith("/journal/") && data) {
      stored.items = [{ ...event(), values: data.values }];
      stored.draft = null;
      return new Response(JSON.stringify(stored.items[0]), { status: 201 });
    }
    return new Response("", { status: 404 });
  });
  const app = render(
    <MemoryRouter
      initialEntries={[
        `/workspaces/${workspaceId}/records`,
        `/workspaces/${workspaceId}/journal`,
      ]}
      initialIndex={1}
    >
      <HistoryControls />
      <SessionProvider>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  );
  return { stored, writes, ...app };
}
afterEach(() => vi.restoreAllMocks());

it("keeps unacknowledged writing when the patient cancels sign-out", async () => {
  const user = userEvent.setup();
  setup({ fail: "network" });
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  await user.click(
    await screen.findByRole("button", { name: "Add observation" }),
  );
  await user.type(
    screen.getByLabelText("Your note"),
    "Unsaved fictional sign-out check",
  );
  await user.click(screen.getByRole("button", { name: "Sign out" }));
  expect(confirm).toHaveBeenCalledWith(
    expect.stringContaining("Recent Journal changes have not been saved"),
  );
  expect(screen.getByLabelText("Your note")).toHaveValue(
    "Unsaved fictional sign-out check",
  );
}, 15000);

it("shows a competing draft without overwriting it and requires explicit replacement", async () => {
  const user = userEvent.setup();
  const { stored } = setup({ fail: "draft-conflict" });
  await user.click(
    await screen.findByRole("button", { name: "Add observation" }),
  );
  await user.type(screen.getByLabelText("Your note"), "My fictional writing");
  await user.click(
    screen.getByRole("button", { name: "Keep draft and close" }),
  );
  await screen.findByText("A different draft is already saved");
  expect(stored.draft!.fields.description).toBe("Another fictional draft");
  expect(screen.getByLabelText("Your note")).toHaveValue(
    "My fictional writing",
  );
  await user.click(
    screen.getByRole("button", { name: "Replace with my writing" }),
  );
  await user.click(
    within(screen.getByRole("dialog")).getByRole("button", {
      name: "Replace draft",
    }),
  );
  await user.click(
    screen.getByRole("button", { name: "Keep draft and close" }),
  );
  await screen.findByRole("button", { name: "Resume private draft" });
  expect(stored.draft!.fields.description).toBe("My fictional writing");
  expect(stored.items).toEqual([]);
}, 15000);

it("recovers unacknowledged writing after route back and forward within the patient context", async () => {
  const user = userEvent.setup();
  setup({ fail: "network" });
  await user.click(
    await screen.findByRole("button", { name: "Add observation" }),
  );
  await user.type(
    screen.getByLabelText("Your note"),
    "Unsaved fictional navigation note",
  );
  await user.click(screen.getByRole("button", { name: "Browser back" }));
  await waitFor(() =>
    expect(screen.queryByLabelText("Your note")).not.toBeInTheDocument(),
  );
  await user.click(screen.getByRole("button", { name: "Browser forward" }));
  expect(await screen.findByLabelText("Your note")).toHaveValue(
    "Unsaved fictional navigation note",
  );
}, 15000);

it("creates a linked symptom with optional severity against typed APIs and checks accessibility", async () => {
  const user = userEvent.setup();
  const { stored, container } = setup();
  await user.click(
    await screen.findByRole("button", { name: "Add observation" }),
  );
  await user.selectOptions(
    screen.getByLabelText("What would you like to record?"),
    "symptom",
  );
  await user.type(
    screen.getByLabelText("What did you experience?"),
    "Fictional headache this afternoon",
  );
  await user.click(screen.getByText("Optional details"));
  await user.type(screen.getByLabelText("Severity (optional)"), "4");
  await user.selectOptions(
    screen.getByLabelText("Related health concern (optional)"),
    concernId,
  );
  await user.click(screen.getByRole("button", { name: "Save observation" }));
  await screen.findByText("Observation saved privately.");
  expect(stored.items[0].values.severity).toBe(4);
  expect(stored.items[0].values.concern_id).toBe(concernId);
  expect(stored.draft).toBeNull();
  expect(screen.getByText("Fictional headache this afternoon")).toBeVisible();
  expect(
    (
      await axe.run(container, {
        rules: { "color-contrast": { enabled: false } },
      })
    ).violations,
  ).toEqual([]);
}, 20000);

it("keeps a private recovery draft without publishing and resumes it after a fresh mount", async () => {
  const user = userEvent.setup();
  const { stored, unmount } = setup();
  await user.click(
    await screen.findByRole("button", { name: "Add observation" }),
  );
  await user.type(
    screen.getByLabelText("Your note"),
    "Private fictional thought",
  );
  await user.click(
    screen.getByRole("button", { name: "Keep draft and close" }),
  );
  await screen.findByRole("button", { name: "Resume private draft" });
  expect(stored.items).toEqual([]);
  const draft = stored.draft!;
  unmount();
  vi.restoreAllMocks();
  setup({ draft });
  await user.click(
    await screen.findByRole("button", { name: "Resume private draft" }),
  );
  expect(screen.getByLabelText("Your note")).toHaveValue(
    "Private fictional thought",
  );
  expect(localStorage.length).toBe(0);
  expect(sessionStorage.length).toBe(0);
}, 15000);

it("reviews Apertus suggestions into the private draft and publishes only after Save", async () => {
  const user = userEvent.setup();
  const { stored } = setup();
  await user.click(await screen.findByRole("button", { name: "Add observation" }));
  await user.type(screen.getByLabelText("Your note"), "Headache and pain was 6/10.");
  await user.click(screen.getByRole("button", { name: "Organize with Apertus" }));
  await screen.findByRole("heading", { name: "Suggestions to review" }, { timeout: 8000 });
  expect(stored.items).toHaveLength(0);
  await user.click(screen.getByRole("button", { name: "Copy selected suggestions to draft" }));
  await waitFor(() => expect(stored.draft?.revision).toBe(2));
  await screen.findByText(/Suggestions copied to your private draft/);
  expect(screen.getByLabelText("What would you like to record?")).toHaveValue("symptom");
  expect(stored.items).toHaveLength(0);
  await user.click(screen.getByRole("button", { name: "Save observation" }));
  await screen.findByText("Observation saved privately.");
  expect(stored.items).toHaveLength(1);
  expect(stored.items[0].values.category).toBe("symptom");
  expect(stored.items[0].values.severity).toBe(6);
  expect(stored.items[0].values.description).toBe("Headache and pain was 6/10.");
}, 20000);

it("shows partial-proposal warnings and keeps manual date and time when no supported suggestion exists", async () => {
  const user = userEvent.setup();
  const fields = { ...initialFields("2026-09-12", "symptom"),
    description: "Headache and pain was 6/10.", time: "08:45", severity: "3" };
  const { stored } = setup({ draft: { id, revision: 1, event_id: null,
    base_revision: 0, fields, updated_at: timestamp },
    aiWarnings: ["Occurrence date: the model suggestion disagrees with the source; neither was substituted."] });
  await user.click(await screen.findByRole("button", { name: "Resume private draft" }));
  await user.click(screen.getByRole("button", { name: "Organize with Apertus" }));
  await screen.findByRole("heading", { name: "Suggestions to review" }, { timeout: 8000 });
  expect(screen.getByText(/Needs your judgment: Occurrence date/)).toBeInTheDocument();
  expect(screen.getByText(/Copied from your source text/)).toBeInTheDocument();
  expect(screen.queryByLabelText(/Use suggested date or time period/)).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Copy selected suggestions to draft" }));
  await waitFor(() => expect(stored.draft?.revision).toBe(2));
  expect(stored.draft?.fields).toMatchObject({ year: "2026", month: "09", day: "12",
    time: "08:45", severity: "6", description: fields.description });
  expect(stored.items).toHaveLength(0);
}, 20000);

it("preserves writing on a revision conflict and requires review before a new correction", async () => {
  const user = userEvent.setup();
  const { stored } = setup({ seed: event(), fail: "conflict" });
  await user.click(
    await screen.findByRole("button", { name: "Correct entry" }),
  );
  await user.clear(screen.getByLabelText("Your note"));
  await user.type(screen.getByLabelText("Your note"), "My correction");
  await user.click(screen.getByRole("button", { name: "Save correction" }));
  await screen.findByText("Concurrent correction");
  expect(screen.getByLabelText("Your note")).toHaveValue("My correction");
  await user.click(
    screen.getByRole("button", {
      name: "Use revision 2 as the starting point",
    }),
  );
  await user.click(screen.getByRole("button", { name: "Browser back" }));
  await waitFor(() =>
    expect(screen.queryByLabelText("Your note")).not.toBeInTheDocument(),
  );
  await user.click(screen.getByRole("button", { name: "Browser forward" }));
  expect(await screen.findByLabelText("Your note")).toHaveValue(
    "My correction",
  );
  await user.click(screen.getByRole("button", { name: "Save correction" }));
  await screen.findByText(
    "Correction saved. Earlier revisions remain in history.",
  );
  expect(stored.items[0].revision).toBe(3);
  await user.click(screen.getByText("Correction history"));
  await screen.findByText("Earlier fictional note");
}, 15000);

it("retains writing and prevents context exit when draft saving fails", async () => {
  const user = userEvent.setup();
  const { stored } = setup({ fail: "network" });
  await user.click(
    await screen.findByRole("button", { name: "Add observation" }),
  );
  await user.type(
    screen.getByLabelText("Your note"),
    "Keep my unsaved writing",
  );
  await user.click(
    screen.getByRole("button", { name: "Keep draft and close" }),
  );
  await screen.findByText(/Recent changes are not saved/);
  expect(screen.getByLabelText("Your note")).toHaveValue(
    "Keep my unsaved writing",
  );
  const leave = new Event("comfort:leave-context", { cancelable: true });
  act(() => {
    window.dispatchEvent(leave);
  });
  expect(leave.defaultPrevented).toBe(true);
  expect(stored.items).toEqual([]);
}, 15000);

it("archives with confirmation and retains history in the archived view", async () => {
  const user = userEvent.setup();
  const { stored } = setup({ seed: event() });
  await user.click(
    await screen.findByRole("button", { name: "Archive entry" }),
  );
  await user.click(
    within(screen.getByRole("dialog")).getByRole("button", { name: "Archive" }),
  );
  await screen.findByText(
    "Observation archived. Its history remains available.",
  );
  expect(stored.items[0].status).toBe("archived");
  await user.click(screen.getByLabelText("Show archived entries"));
  await screen.findByText("Fictional observation");
  await user.click(screen.getByText("Correction history"));
  await screen.findByText("Earlier fictional note");
}, 15000);

it("does not load Journal data without the required capability", async () => {
  const { writes } = setup({ manage: false });
  await screen.findByText(
    "Your current context does not permit private Journal access.",
  );
  expect(writes).toEqual([]);
});

it("hides a saved draft on session interruption without publishing it", async () => {
  const fields = {
    ...initialFields(localDay()),
    description: "Private fictional draft",
  };
  const { stored } = setup({
    draft: {
      id,
      revision: 1,
      event_id: null,
      base_revision: 0,
      fields,
      updated_at: timestamp,
    },
  });
  await userEvent
    .setup()
    .click(await screen.findByRole("button", { name: "Resume private draft" }));
  act(() => window.dispatchEvent(new Event("comfort:session-ended")));
  await screen.findByText("Your information is hidden until you sign in.");
  expect(screen.queryByLabelText("Your note")).not.toBeInTheDocument();
  expect(stored.draft?.fields.description).toBe(fields.description);
  expect(stored.items).toEqual([]);
});

it("rejects impossible dates without inventing components and leaves severity optional", () => {
  const fields = {
    ...initialFields("2026-02-30"),
    description: "Fictional note",
  };
  expect(() => toValues(fields)).toThrow("valid calendar date");
  const values = toValues({
    ...fields,
    precision: "year",
    year: "2025",
    time: "",
  });
  expect(values.occurrence).toEqual({
    precision: "year",
    year: 2025,
    month: null,
    day: null,
  });
  expect(values.severity).toBeNull();
});
