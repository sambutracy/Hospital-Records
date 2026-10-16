import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it } from "vitest";
import CareNavigation from "./CareNavigation";

it("keeps all three care destinations directly available and identifies the current section", () => {
  render(
    <MemoryRouter initialEntries={["/workspaces/fictional/care/team"]}>
      <Routes>
        <Route path="workspaces/:workspaceId">
          <Route path="care/team" element={<CareNavigation />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
  expect(
    screen.getByRole("navigation", { name: "My Care sections" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Health concerns" })).toHaveAttribute(
    "href",
    "/workspaces/fictional/care/concerns",
  );
  expect(screen.getByRole("link", { name: "Care Team" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(
    screen.getByRole("link", { name: "Prepare for a visit" }),
  ).toHaveAttribute("href", "/workspaces/fictional/care/visits");
});
