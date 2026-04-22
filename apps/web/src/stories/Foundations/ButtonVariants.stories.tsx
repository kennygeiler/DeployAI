import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Mail } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * Foundations / ButtonVariants — renders the shadcn `<Button>` across every
 * variant × size × state combination required by `UX-DR39`. Under
 * `@storybook/addon-a11y` (runOnly = wcag2a + wcag2aa + wcag21aa + wcag22aa
 * per preview.ts) each story must produce zero axe-core violations, which
 * is why the icon-only cases ship an explicit `aria-label` and the inner
 * `<Mail />` is `aria-hidden`.
 *
 * The surface exercised here is the one downstream stories (Epic 7
 * composites, Epic 8 surfaces) compose against — keep parity with the
 * shadcn primitive API.
 */
const meta = {
  title: "Foundations/ButtonVariants",
  component: Button,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Canonical render of every shadcn <Button> variant, size, and disabled state. Mirrors UX-DR39 (primary/secondary/ghost/destructive hierarchy, 36 px min height, 44×44 hit area, icon-only aria-label).",
      },
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const AllVariants: Story = {
  render: () => (
    <section aria-labelledby="button-variants-heading" className="space-y-4">
      <h2 id="button-variants-heading" className="sr-only">
        All Button variants
      </h2>
      <div className="flex flex-wrap items-center gap-2">
        <Button>Default</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="destructive">Destructive</Button>
        <Button variant="link">Link</Button>
        <Button variant="outline">Outline</Button>
      </div>
    </section>
  ),
};

export const AllSizes: Story = {
  render: () => (
    <section aria-labelledby="button-sizes-heading" className="space-y-4">
      <h2 id="button-sizes-heading" className="sr-only">
        All Button sizes
      </h2>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm">Small</Button>
        <Button size="default">Default</Button>
        <Button size="lg">Large</Button>
        <Button size="icon" aria-label="Send mail">
          <Mail aria-hidden />
        </Button>
      </div>
    </section>
  ),
};

export const DisabledStates: Story = {
  render: () => (
    <section aria-labelledby="button-disabled-heading" className="space-y-4">
      <h2 id="button-disabled-heading" className="sr-only">
        Disabled Button states
      </h2>
      <div className="flex flex-wrap items-center gap-2">
        <Button disabled>Default</Button>
        <Button variant="secondary" disabled>
          Secondary
        </Button>
        <Button variant="ghost" disabled>
          Ghost
        </Button>
        <Button variant="destructive" disabled>
          Destructive
        </Button>
        <Button variant="link" disabled>
          Link
        </Button>
        <Button variant="outline" disabled>
          Outline
        </Button>
      </div>
    </section>
  ),
};

export const IconOnlyHasAriaLabel: Story = {
  name: "Icon-only has aria-label",
  render: () => (
    <Button size="icon" aria-label="Open menu">
      <Mail aria-hidden />
    </Button>
  ),
};
