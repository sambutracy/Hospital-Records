import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import axe from "axe-core";
import { Button, ConfirmDialog, EmptyState, Notice } from "./primitives";
describe("accessible foundations", () => {
  it("uses named semantic controls and announces a recoverable error", async () => {
    const { container } = render(
      <main>
        <h1>Comfort</h1>
        <Button>Add a record</Button>
        <Notice tone="error" live>
          Your original is unchanged. Try again.
        </Notice>
        <EmptyState title="Your records start here">
          Add an original.
        </EmptyState>
      </main>,
    );
    expect(screen.getByRole("button", { name: "Add a record" })).toBeEnabled();
    expect(screen.getByRole("alert")).toHaveTextContent("unchanged");
    const result = await axe.run(container, {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(result.violations).toEqual([]);
  });
  it("lets keyboard users cancel confirmation and restores focus to the trigger", async () => {
    const confirm = vi.fn();
    render(
      <ConfirmDialog
        title="Save private selection?"
        trigger="Prepare for a visit"
        onConfirm={confirm}
      >
        <p>No information is shared.</p>
      </ConfirmDialog>,
    );
    const user = userEvent.setup();
    const trigger = screen.getByRole("button", { name: "Prepare for a visit" });
    await user.tab();
    await user.keyboard("{Enter}");
    expect(
      screen.getByRole("dialog", { name: "Save private selection?" }),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).not.toHaveBeenCalled();
    expect(trigger).toHaveFocus();
  });
});
