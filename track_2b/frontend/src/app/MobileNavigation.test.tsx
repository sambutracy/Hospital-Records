import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import MobileNavigation from "./MobileNavigation";

it("keeps navigation in a closed native menu and closes after choosing a page", () => {
  render(
    <MobileNavigation currentSection="Home">
      <nav aria-label="Mobile main navigation">
        <a href="#records">Records</a>
      </nav>
    </MobileNavigation>,
  );
  const summary = screen.getByLabelText("Main menu, current page Home");
  const menu = summary.closest("details")!;
  expect(menu.open).toBe(false);
  fireEvent.click(summary);
  expect(menu.open).toBe(true);
  fireEvent.click(screen.getByRole("link", { name: "Records" }));
  expect(menu.open).toBe(false);
});

it("returns keyboard focus to the menu when Escape closes it", () => {
  render(
    <MobileNavigation currentSection="Journal">
      <a href="#journal">Journal</a>
    </MobileNavigation>,
  );
  const summary = screen.getByLabelText("Main menu, current page Journal");
  const menu = summary.closest("details")!;
  menu.open = true;
  const link = screen.getByRole("link", { name: "Journal" });
  link.focus();
  fireEvent.keyDown(link, { key: "Escape" });
  expect(menu.open).toBe(false);
  expect(summary).toHaveFocus();
});
