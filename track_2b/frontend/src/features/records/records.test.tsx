import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ContextScope } from "../../services/auth/session";
import { setCsrf } from "../../services/api/client";
import { context, record, recordId, workspaceId } from "../../test/fixtures";
import Detail from "./Detail";
import Upload, { validateFile } from "./Upload";
import { partialDate } from "./RecordCard";
afterEach(() => vi.restoreAllMocks());
describe("source fidelity and input handling", () => {
  it("keeps unknown and partial dates distinct without guessing a day", () => {
    expect(partialDate(null)).toBe("Date not reviewed");
    expect(
      partialDate({ precision: "unknown", year: null, month: null, day: null }),
    ).toBe("Date unknown");
    expect(
      partialDate({ precision: "month", year: 2026, month: 9, day: null }),
    ).toBe("September 2026");
  });
  it("rejects oversized and unsupported files before sending them", () => {
    expect(validateFile(new File(["x"], "notes.txt"))).toContain("PDF");
    const large = new File(["x"], "large.pdf");
    Object.defineProperty(large, "size", { value: 11 * 1024 * 1024 });
    expect(validateFile(large)).toContain("10 MB");
    expect(validateFile(new File(["x"], "original.dcm"))).toBeUndefined();
  });
  it("reviews a real-shaped partial date using the original version and revision", async () => {
    const sent: unknown[] = [];
    setCsrf("test-csrf");
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, options) => {
      const path = String(input);
      if (path.endsWith("assistant/status/"))
        return new Response(
          JSON.stringify({
            configured: false,
            model: null,
            facility_search_enabled: false,
          }),
        );
      if (path.endsWith("/review/")) {
        sent.push(JSON.parse(String(options?.body)));
        expect(
          (options?.headers as Record<string, string>)["X-CSRFToken"],
        ).toBe("test-csrf");
        return new Response(
          JSON.stringify({ ...record.metadata, revision: 1 }),
        );
      }
      return new Response(JSON.stringify(record));
    });
    render(
      <MemoryRouter
        initialEntries={[`/workspaces/${workspaceId}/records/${recordId}`]}
      >
        <ContextScope context={context}>
          <Routes>
            <Route
              path="workspaces/:workspaceId/records/:recordId"
              element={<Detail />}
            />
          </Routes>
        </ContextScope>
      </MemoryRouter>,
    );
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Review document details" });
    await user.selectOptions(
      screen.getByLabelText("Document type"),
      "lab_report",
    );
    await user.selectOptions(
      screen.getByLabelText("How much of the date is known?"),
      "month",
    );
    await user.type(screen.getByLabelText("Year"), "2026");
    await user.type(screen.getByLabelText("Month (1–12)"), "9");
    await user.type(
      screen.getByLabelText("Issuing facility"),
      "Fictional clinic",
    );
    await user.click(
      screen.getByRole("button", { name: "Confirm document details" }),
    );
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0]).toMatchObject({
      source_version_id: record.current_version.id,
      expected_revision: 0,
      values: {
        document_date: { precision: "month", year: 2026, month: 9, day: null },
      },
    });
    await screen.findByText(
      "Details reviewed by you. They are not clinician-verified.",
    );
  });
  it("retains review entries on conflict and requires explicit reload", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      async (input) =>
        new Response(
          JSON.stringify(
            String(input).endsWith("assistant/status/")
              ? {
                  configured: false,
                  model: null,
                  facility_search_enabled: false,
                }
              : record,
          ),
          { status: String(input).endsWith("/review/") ? 409 : 200 },
        ),
    );
    render(
      <MemoryRouter initialEntries={[`/records/${recordId}`]}>
        <ContextScope context={context}>
          <Routes>
            <Route path="records/:recordId" element={<Detail />} />
          </Routes>
        </ContextScope>
      </MemoryRouter>,
    );
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Review document details" });
    await user.type(
      screen.getByLabelText("Issuing facility"),
      "Keep this valid entry",
    );
    await user.click(
      screen.getByRole("button", { name: "Confirm document details" }),
    );
    await screen.findByRole("button", { name: "Load current details" });
    expect(screen.getByLabelText("Issuing facility")).toHaveValue(
      "Keep this valid entry",
    );
    expect(
      screen.getByRole("button", { name: "Confirm document details" }),
    ).toBeDisabled();
  });
  it("keeps successful uploads and retries only the failed original", async () => {
    const calls: string[] = [];
    let failure = true;
    class TestXHR {
      status = 201;
      responseText = JSON.stringify({
        created: true,
        version: record.current_version,
      });
      withCredentials = false;
      upload = { onprogress: null };
      onload: null | (() => void) = null;
      onerror = null;
      onabort: null | (() => void) = null;
      onloadend: null | (() => void) = null;
      open() {}
      setRequestHeader() {}
      abort() {
        this.onabort?.();
      }
      send(form: FormData) {
        const file = form.get("file") as File;
        calls.push(file.name);
        this.status = file.name === "retry.pdf" && failure ? 503 : 201;
        if (this.status === 503) failure = false;
        queueMicrotask(() => {
          this.onload?.();
          this.onloadend?.();
        });
      }
    }
    vi.stubGlobal("XMLHttpRequest", TestXHR);
    const saved = vi.fn();
    render(
      <MemoryRouter>
        <ContextScope context={context}>
          <Upload onSaved={saved} />
        </ContextScope>
      </MemoryRouter>,
    );
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Choose files"), [
      new File(["x"], "saved.pdf", { type: "application/pdf" }),
      new File(["y"], "retry.pdf", { type: "application/pdf" }),
    ]);
    await user.click(
      screen.getByRole("button", { name: "Save selected files" }),
    );
    await screen.findByRole("button", { name: "Retry failed files" });
    await user.click(
      screen.getByRole("button", { name: "Retry failed files" }),
    );
    await waitFor(() =>
      expect(calls).toEqual(["saved.pdf", "retry.pdf", "retry.pdf"]),
    );
    expect(saved).toHaveBeenCalledTimes(2);
    vi.unstubAllGlobals();
  });
});
