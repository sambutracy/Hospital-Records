import type { Meta, StoryObj } from "@storybook/react-vite";
import { MemoryRouter } from "react-router-dom";
import CareHome from "./CareHome";
const meta = {
  title: "Comfort/My Care",
  component: CareHome,
  decorators: [
    (Story) => (
      <MemoryRouter>
        <main className="main-content">
          <Story />
        </main>
      </MemoryRouter>
    ),
  ],
} satisfies Meta<typeof CareHome>;
export default meta;
export const Overview: StoryObj<typeof meta> = {};
