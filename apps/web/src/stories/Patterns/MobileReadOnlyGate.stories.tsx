import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useMobileReadOnlyGate } from "@deployai/shared-ui";

/**
 * UX-DR38 — documents the mobile read-only gate shipped in Story 7-13 (`packages/shared-ui`).
 * Resize the Storybook viewport (or the browser window) across **768px** (`md:`) to see the
 * value flip; Epic 9 / 10 write flows should branch on `true` to render view-only chrome.
 */
const meta: Meta = {
  title: "Patterns/Mobile read-only gate (UX-DR38)",
  tags: ["autodocs"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "`useMobileReadOnlyGate()` returns `true` when `matchMedia('(max-width: 767px)')` matches. Default breakpoint aligns with Tailwind `md:` (768px).",
      },
    },
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

function GateReadout() {
  const readOnly = useMobileReadOnlyGate();
  return (
    <div className="border-border max-w-lg rounded-lg border p-4" role="status" aria-live="polite">
      <p className="text-foreground text-sm font-semibold">useMobileReadOnlyGate()</p>
      <p className="text-body text-ink-700 mt-2">
        Current value:{" "}
        <strong>
          {readOnly ? "read-only — defer writes or show view-only UI" : "full interaction"}
        </strong>
      </p>
      <p className="text-muted-foreground mt-3 text-xs">
        In Storybook: change the viewport preset (e.g. Mobile vs Desktop) and watch this status
        update.
      </p>
    </div>
  );
}

export const Default: Story = {
  render: () => <GateReadout />,
};
