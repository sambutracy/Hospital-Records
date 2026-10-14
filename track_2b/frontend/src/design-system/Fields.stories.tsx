import type { Meta, StoryObj } from "@storybook/react-vite";
import { TextField, SelectField } from "./fields";
const meta = {
  title: "Comfort/Fields",
  component: TextField,
  args: { id: "example", label: "Example field" },
} satisfies Meta<typeof TextField>;
export default meta;
type Story = StoryObj<typeof meta>;
export const States: Story = {
  render: () => (
    <div className="stack">
      <TextField
        id="facility"
        label="Issuing facility"
        help="Leave blank if unknown."
      />
      <TextField
        id="year"
        label="Known year"
        error="Enter a year from 1 to 9999."
        inputProps={{ defaultValue: "not a year" }}
      />
      <SelectField
        id="precision"
        label="How much of the date is known?"
        options={[
          { value: "unknown", label: "Unknown" },
          { value: "year", label: "Year only" },
        ]}
      />
    </div>
  ),
};
