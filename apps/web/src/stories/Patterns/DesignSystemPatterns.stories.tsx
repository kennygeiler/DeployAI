import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Settings } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * UX-DR39–41 — pattern reference in the host app (shadcn Button + forms live in `apps/web`).
 * Component primitives ship from `@deployai/shared-ui`; this story is the visual contract for hierarchy.
 */
const meta: Meta = {
  title: "Patterns/Design system consistency (UX-DR39–41)",
  tags: ["autodocs"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Primary (one per surface), secondary outline, ghost tertiary, destructive only for irreversible actions. Forms: label above, required text, aria-invalid. Modals: destructive → Dialog; heavy settings → Sheet; metadata → Popover.",
      },
    },
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const ButtonHierarchy: Story = {
  render: () => (
    <div className="flex min-h-32 flex-wrap items-center gap-3">
      <Button>Primary action</Button>
      <Button variant="secondary">Secondary</Button>
      <Button variant="ghost">Tertiary / ghost</Button>
      <Button variant="destructive">Destructive</Button>
      <Button size="icon" variant="outline" aria-label="Settings">
        <Settings className="size-4" />
      </Button>
    </div>
  ),
};
