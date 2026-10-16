import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { record } from "../../test/fixtures";
import { RecordCard } from "./RecordCard";

describe("record card metadata hierarchy", () => {
  it("promotes reviewed metadata while preserving the original filename and exact navigation", async () => {
    const onSelect = vi.fn();
    render(
      <MemoryRouter>
        <RecordCard
          record={{
            ...record,
            metadata: {
              ...record.metadata,
              revision: 1,
              values: {
                document_type: "lab_report",
                document_date: {
                  precision: "month",
                  year: 2026,
                  month: 9,
                  day: null,
                },
                facility_name: "Fictional clinic",
              },
            },
          }}
          selected={false}
          onSelect={onSelect}
        />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "Lab report · fictional-lab.pdf" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Lab report · fictional-lab.pdf" }),
    ).toHaveAttribute("href", `/records/${record.id}`);
    expect(screen.getByText("September 2026")).toBeInTheDocument();
    expect(screen.getByText("Fictional clinic")).toBeInTheDocument();
    expect(screen.getByText("fictional-lab.pdf")).toBeInTheDocument();
    await userEvent
      .setup()
      .click(screen.getByRole("checkbox", { name: "Select for a visit" }));
    expect(onSelect).toHaveBeenCalledWith(true);
  });

  it("does not promote unreviewed metadata into a clinical title or known date", () => {
    render(
      <MemoryRouter>
        <RecordCard
          record={{
            ...record,
            metadata: {
              ...record.metadata,
              values: {
                document_type: "prescription",
                document_date: {
                  precision: "year",
                  year: 2026,
                  month: null,
                  day: null,
                },
                facility_name: "Unreviewed clinic",
              },
            },
          }}
        />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "Health record · fictional-lab.pdf" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Date not reviewed")).toBeInTheDocument();
    expect(screen.queryByText("Unreviewed clinic")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Prescription" }),
    ).not.toBeInTheDocument();
  });
});
