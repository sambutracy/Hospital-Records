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
import { useEffect } from "react";
import { afterEach, expect, it, vi } from "vitest";
import axe from "axe-core";
import App from "../../app/App";
import { SessionProvider } from "../../services/auth/session";
import { context, workspaceId } from "../../test/fixtures";
import type { Concern, Practitioner, Assignment } from "./contracts";
// These journeys lazy-load a route and perform several user actions on a host
// that also runs the local model. Timing is not a product performance assertion.
configure({ asyncUtilTimeout: 5000 });
const concernId = "44444444-4444-4444-8444-444444444444";
const doctorId = "55555555-5555-4555-8555-555555555555";
const assignmentId = "66666666-6666-4666-8666-666666666666";
const common = {
  revision: 1,
  status: "active" as const,
  updated_at: "2026-10-14T12:00:00Z",
  provenance: "patient_reported" as const,
  access_effect: "none" as const,
};
const concern: Concern = {
  ...common,
  id: concernId,
  values: {
    title: "Fictional investigation",
    description: "",
    kind: "investigation",
    certainty: "unconfirmed",
    onset: { precision: "year", year: 2025, month: null, day: null },
  },
};
const doctor: Practitioner = {
  ...common,
  id: doctorId,
  values: {
    name: "Dr Fictional Cedar",
    specialty: "General practice",
    facility: "Fictional clinic",
    notes: "",
  },
};
type Stored = {
  concerns: Concern[];
  practitioners: Practitioner[];
  assignments: Assignment[];
};
function setup(
  route: string,
  seed?: Partial<Stored>,
  mode: "normal" | "conflict" | "network" = "normal",
  canManage = true,
) {
  const stored: Stored = {
    concerns: [],
    practitioners: [],
    assignments: [],
    ...seed,
  };
  const writes: Array<{ path: string; payload: Record<string, unknown> }> = [];
  const mock = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (path, options) => {
      const url = String(path);
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
                  ...(canManage ? ["manage_profile"] : []),
                ],
              },
            ],
            default_context_id: workspaceId,
            expires_at: Date.now() / 1000 + 300,
            csrf_token: "test-csrf",
            supported_context_kinds: ["patient"],
          }),
        );
      if (url.endsWith("/care-circle/"))
        return new Response(JSON.stringify({ contacts: [] }));
      const kind = url.match(
        /\/care\/(concerns|practitioners|assignments)\//,
      )?.[1] as keyof Stored;
      if (!kind) return new Response("", { status: 404 });
      if (url.endsWith("/history/"))
        return new Response(
          JSON.stringify({
            history: [
              {
                revision: 1,
                created_at: common.updated_at,
                snapshot: { ...doctor.values, status: "active" },
              },
            ],
          }),
        );
      if (!options?.method)
        return new Response(JSON.stringify({ items: stored[kind] }));
      const payload = JSON.parse(String(options.body)) as Record<
        string,
        unknown
      >;
      writes.push({ path: url, payload });
      if (mode === "network") throw new TypeError("Network unavailable");
      if (mode === "conflict") {
        stored.practitioners = [
          {
            ...doctor,
            revision: 2,
            values: { ...doctor.values, name: "Updated saved doctor" },
          },
        ];
        return new Response("", { status: 409 });
      }
      const id =
        kind === "concerns"
          ? concernId
          : kind === "practitioners"
            ? doctorId
            : assignmentId;
      const item = { ...common, id, values: payload.values };
      (stored[kind] as unknown[]).push(item);
      return new Response(JSON.stringify(item), { status: 201 });
    });
  let navigate: ReturnType<typeof useNavigate>;
  function NavigationProbe() {
    const current = useNavigate();
    useEffect(() => {
      navigate = current;
    }, [current]);
    return null;
  }
  const view = render(
    <MemoryRouter
      initialEntries={[
        `/workspaces/${workspaceId}/care`,
        `/workspaces/${workspaceId}/care/${route}`,
      ]}
      initialIndex={1}
    >
      <NavigationProbe />
      <SessionProvider>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  );
  return {
    stored,
    writes,
    mock,
    router: { navigate: (delta: number) => navigate(delta) },
    ...view,
  };
}
afterEach(() => vi.restoreAllMocks());
it("recovers an unsaved care draft after back/forward navigation using only the patient context memory", async () => {
  const user = userEvent.setup();
  const storage = vi.spyOn(Storage.prototype, "setItem");
  const { router, writes } = setup("team", { practitioners: [doctor] });
  await screen.findByRole("heading", { name: "Dr Fictional Cedar" });
  await user.click(
    screen.getByRole("button", { name: "Edit Dr Fictional Cedar" }),
  );
  const field = screen.getByLabelText("Doctor’s name");
  await user.clear(field);
  await user.type(field, "Recover this draft");
  await act(async () => {
    await router.navigate(-1);
  });
  await screen.findByRole("heading", {
    name: "Keep the people and pieces together.",
  });
  await act(async () => {
    await router.navigate(1);
  });
  await screen.findByText(
    "Your unsaved care draft is restored in this patient context. Review it before saving.",
  );
  expect(screen.getByLabelText("Doctor’s name")).toHaveValue(
    "Recover this draft",
  );
  expect(writes).toHaveLength(0);
  expect(storage).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Cancel editing" }));
  await user.click(
    within(screen.getByRole("dialog")).getByRole("button", {
      name: "Discard draft",
    }),
  );
  await user.click(screen.getByRole("button", { name: "Add doctor" }));
  expect(screen.getByLabelText("Doctor’s name")).toHaveValue("");
}, 15000);
it("creates a concern, records a historical doctor and links them without requesting access grants", async () => {
  const user = userEvent.setup();
  const { stored, writes } = setup("concerns");
  await screen.findByRole("heading", { name: "Health concerns", level: 1 });
  await user.click(screen.getByRole("button", { name: "Add health concern" }));
  await user.type(
    screen.getByLabelText("Concern name"),
    "Fictional investigation",
  );
  await user.selectOptions(
    screen.getByLabelText("Type of concern"),
    "investigation",
  );
  await user.selectOptions(screen.getByLabelText("Date detail"), "year");
  await user.type(screen.getByLabelText("Year"), "2025");
  await user.click(screen.getByRole("button", { name: "Save care details" }));
  await screen.findByText(
    "Saved to your care information. No access permission was created.",
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Add health concern" }),
    ).toHaveFocus(),
  );
  expect(stored.concerns[0].values.onset).toEqual({
    precision: "year",
    year: 2025,
    month: null,
    day: null,
  });
  expect(stored.concerns[0].values.certainty).toBe("unconfirmed");
  await user.click(screen.getByRole("link", { name: "Care Team" }));
  await screen.findByRole("heading", { name: "Your Care Team" });
  await user.click(screen.getByRole("button", { name: "Add doctor" }));
  await user.type(screen.getByLabelText("Doctor’s name"), "Dr Fictional Cedar");
  await user.click(screen.getByRole("button", { name: "Save care details" }));
  await screen.findByRole("heading", { name: "Dr Fictional Cedar" });
  await user.click(
    screen.getByRole("button", {
      name: "Link a concern for Dr Fictional Cedar",
    }),
  );
  expect(screen.getByLabelText("Participation")).toHaveValue("historical");
  await user.selectOptions(screen.getByLabelText("Health concern"), concernId);
  const start = within(
    screen.getByRole("group", { name: "Care started (optional)" }),
  );
  await user.selectOptions(start.getByLabelText("Date detail"), "month");
  await user.type(start.getByLabelText("Year"), "2025");
  await user.type(start.getByLabelText("Month (1–12)"), "9");
  await user.click(screen.getByRole("button", { name: "Save care details" }));
  await screen.findByText("Doctor · Historical");
  expect(stored.assignments[0].values).toMatchObject({
    practitioner_id: doctorId,
    concern_id: concernId,
    participation: "historical",
    start_date: { precision: "month", year: 2025, month: 9, day: null },
  });
  expect(writes).toHaveLength(3);
  expect(writes.every((w) => w.path.includes("/care/"))).toBe(true);
  expect(
    writes.every((w) => !JSON.stringify(w.payload).includes("recipient_id")),
  ).toBe(true);
  expect(
    screen.getByText("Access: this relationship grants no record access."),
  ).toBeVisible();
});
it("keeps an unsaved correction and its original revision when another update causes a conflict", async () => {
  const user = userEvent.setup();
  const { writes } = setup(
    "team",
    { practitioners: [doctor], concerns: [concern] },
    "conflict",
  );
  await screen.findByRole("heading", { name: "Dr Fictional Cedar" });
  await user.click(
    screen.getByRole("button", { name: "Edit Dr Fictional Cedar" }),
  );
  const input = screen.getByLabelText("Doctor’s name");
  await user.clear(input);
  await user.type(input, "Unsaved correction");
  await user.click(screen.getByRole("button", { name: "Save care details" }));
  await screen.findByRole("alert");
  expect(input).toHaveValue("Unsaved correction");
  expect(writes[0].payload.expected_revision).toBe(1);
  expect(
    screen.getByRole("button", { name: "Save care details" }),
  ).toBeDisabled();
  await user.click(
    screen.getByRole("button", { name: "Reload latest details" }),
  );
  await user.click(
    within(screen.getByRole("dialog")).getByRole("button", { name: "Reload" }),
  );
  await waitFor(() =>
    expect(screen.getByLabelText("Doctor’s name")).toHaveValue(
      "Updated saved doctor",
    ),
  );
  expect(
    screen.getByRole("button", { name: "Save care details" }),
  ).toBeEnabled();
});
it("retains entered care details after a network failure", async () => {
  const user = userEvent.setup();
  setup("concerns", {}, "network");
  await screen.findByRole("heading", { name: "Health concerns", level: 1 });
  await user.click(screen.getByRole("button", { name: "Add health concern" }));
  await user.type(screen.getByLabelText("Concern name"), "Unsaved concern");
  await user.click(screen.getByRole("button", { name: "Save care details" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("Concern name")).toHaveValue("Unsaved concern");
});
it("does not request private care data when the server context lacks profile authority", async () => {
  const { mock } = setup("team", {}, "normal", false);
  await screen.findByText(
    "Care relationship tools are unavailable in your current authorized context.",
  );
  expect(mock).toHaveBeenCalledTimes(1);
  expect(
    screen.queryByRole("button", { name: "Add doctor" }),
  ).not.toBeInTheDocument();
});
it("has named care fields and an accessible saved history view", async () => {
  const user = userEvent.setup();
  const { container } = setup("team", { practitioners: [doctor] });
  await screen.findByRole("heading", { name: "Dr Fictional Cedar" });
  await user.click(
    screen.getByRole("button", { name: "History for Dr Fictional Cedar" }),
  );
  await screen.findByText(/Revision 1/);
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  const results = await axe.run(container, {
    rules: { "color-contrast": { enabled: false } },
  });
  expect(results.violations).toEqual([]);
  await user.click(screen.getByRole("button", { name: "Add doctor" }));
  expect(screen.getByRole("textbox", { name: "Doctor’s name" })).toBeVisible();
});
