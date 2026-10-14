import type { Meta, StoryObj } from "@storybook/react-vite";
import { Button, Notice, EmptyState, ConfirmDialog } from "./primitives";
const meta = { title: "Comfort/Foundation", component: Button } satisfies Meta<
  typeof Button
>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Actions: Story = {
  render: () => (
    <div className="stack">
      <Button>Add a record</Button>
      <Button variant="secondary">Review details</Button>
      <Button isDisabled>Saving…</Button>
      <Notice tone="warning">
        Your original is saved. Text reading needs another step.
      </Notice>
      <EmptyState
        title="Your records start here"
        action={<Button>Add a record</Button>}
      >
        Keep your originals ready for your next visit.
      </EmptyState>
      <ConfirmDialog
        title="Save a new version?"
        trigger="Replace original"
        onConfirm={() => {}}
      >
        The existing version stays in your history.
      </ConfirmDialog>
    </div>
  ),
};
export const VisualDirections: Story = {
  render: () => (
    <div className="study-variants">
      {[
        ["Quiet Editorial Care", ""],
        ["Warm Humanist", "study-warm"],
        ["Clinical Precision", "study-clinical"],
      ].map(([title, style]) => (
        <section className={`panel stack ${style}`} key={title}>
          <h2>{title}</h2>
          <h3>Your health story, together.</h3>
          <p>One original. Clear details. You choose what to share.</p>
          <Button>Add a record</Button>
          <Notice>Details reviewed by you · not clinician-verified.</Notice>
        </section>
      ))}
    </div>
  ),
};
