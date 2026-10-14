import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import App from "../../app/App";
import { SessionProvider } from "./session";
import { context, workspaceId, record } from "../../test/fixtures";
import { api, setCsrf } from "../api/client";
import { recordsSchema } from "../api/contracts";
const session = {
  contract_version: 1,
  actor: { id: workspaceId, display_name: "Fictional patient" },
  contexts: [context],
  default_context_id: workspaceId,
  expires_at: Date.now() / 1000 + 300,
  csrf_token: "test-csrf",
  supported_context_kinds: ["patient"],
};
afterEach(() => vi.restoreAllMocks());
it("rejects a different context route without requesting its records", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(session)));
  render(
    <MemoryRouter
      initialEntries={[
        "/workspaces/99999999-9999-4999-8999-999999999999/records",
      ]}
    >
      <SessionProvider>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: "This workspace is unavailable" });
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(String(fetch.mock.calls[0][0])).toBe("/api/session/");
});
it("hides patient content and clears the shell immediately when the session ends", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async (path) =>
      new Response(
        JSON.stringify(
          String(path) === "/api/session/"
            ? session
            : {
                records: [record],
                offset: 0,
                limit: 50,
                total: 1,
                has_more: false,
                order: "upload",
              },
        ),
      ),
  );
  render(
    <MemoryRouter initialEntries={[`/workspaces/${workspaceId}/home`]}>
      <SessionProvider>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: "Hello, Fictional patient." });
  window.dispatchEvent(new Event("comfort:session-ended"));
  await screen.findByRole("button", { name: "Sign in securely" });
  expect(
    screen.queryByText("Hello, Fictional patient."),
  ).not.toBeInTheDocument();
});
it("rejects malformed contracts and makes CSRF failures actionable", async () => {
  setCsrf("test-csrf");
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ records: "invented" })),
  );
  await expect(
    api("/api/workspaces/x/records/", recordsSchema),
  ).rejects.toThrow("response safely");
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("", { status: 403 }),
  );
  await expect(api("/api/session/", recordsSchema)).rejects.toThrow("Refresh");
});
it("does not allow a late bootstrap response to resurrect a closed session", async () => {
  let finish: (value: Response) => void = () => {};
  vi.spyOn(globalThis, "fetch").mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  render(
    <MemoryRouter>
      <SessionProvider>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  );
  window.dispatchEvent(new Event("comfort:session-ended"));
  await screen.findByRole("button", { name: "Sign in securely" });
  finish(new Response(JSON.stringify(session)));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Sign in securely" }),
    ).toBeInTheDocument(),
  );
  expect(
    screen.queryByRole("heading", { name: "Hello, Fictional patient." }),
  ).not.toBeInTheDocument();
});
