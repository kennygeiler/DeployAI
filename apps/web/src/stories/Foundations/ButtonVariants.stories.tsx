import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Mail } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * Foundations / ButtonVariants — renders the shadcn `<Button>` across every
 * variant × size × state combination required by `UX-DR39` and AC4 (lines
 * 97–103 of the Story 1.5 spec: "every variant × size combination" plus
 * "enabled and disabled for each variant"). Under `@storybook/addon-a11y`
 * (runOnly = wcag2a + wcag2aa + wcag21aa + wcag22aa per preview.ts) each
 * story must produce zero axe-core violations, which is why the icon-only
 * cases ship an explicit `aria-label` and the inner `<Mail />` is
 * `aria-hidden`.
 *
 * The surface exercised here is the one downstream stories (Epic 7
 * composites, Epic 8 surfaces) compose against — keep parity with the
 * shadcn primitive API.
 */

type Variant = "default" | "secondary" | "ghost" | "destructive" | "link" | "outline";
type Size = "sm" | "default" | "lg" | "icon";

const VARIANTS: readonly Variant[] = [
  "default",
  "secondary",
  "ghost",
  "destructive",
  "link",
  "outline",
] as const;

const SIZES: readonly Size[] = ["sm", "default", "lg", "icon"] as const;

function renderCell(variant: Variant, size: Size, disabled: boolean) {
  const key = `${variant}-${size}-${disabled ? "disabled" : "enabled"}`;
  const commonProps = {
    variant,
    size,
    disabled,
  } as const;
  if (size === "icon") {
    return (
      <Button
        key={key}
        {...commonProps}
        aria-label={`${variant} ${disabled ? "disabled" : "enabled"} icon button`}
      >
        <Mail aria-hidden />
      </Button>
    );
  }
  return (
    <Button key={key} {...commonProps}>
      {variant}
    </Button>
  );
}

function MatrixSection({
  headingId,
  heading,
  disabled,
}: {
  headingId: string;
  heading: string;
  disabled: boolean;
}) {
  return (
    <section aria-labelledby={headingId} className="space-y-2">
      <h2 id={headingId} className="sr-only">
        {heading}
      </h2>
      <table className="w-full border-separate border-spacing-2 text-left">
        <thead>
          <tr>
            <th scope="col" className="sr-only">
              Variant
            </th>
            {SIZES.map((size) => (
              <th key={size} scope="col" className="text-muted-foreground text-sm">
                {size}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {VARIANTS.map((variant) => (
            <tr key={variant}>
              <th scope="row" className="text-muted-foreground pr-2 text-sm">
                {variant}
              </th>
              {SIZES.map((size) => (
                <td key={size}>{renderCell(variant, size, disabled)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

const meta = {
  title: "Foundations/ButtonVariants",
  component: Button,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Canonical render of every shadcn <Button> variant × size × state combination (6 variants × 4 sizes × enabled/disabled = 48 cells). Mirrors UX-DR39 (primary/secondary/ghost/destructive hierarchy, 36 px min height, 44×44 hit area, icon-only aria-label).",
      },
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const EnabledMatrix: Story = {
  name: "Enabled — variant × size",
  render: () => (
    <MatrixSection
      headingId="button-enabled-matrix-heading"
      heading="Enabled Button variants by size"
      disabled={false}
    />
  ),
};

export const DisabledMatrix: Story = {
  name: "Disabled — variant × size",
  render: () => (
    <MatrixSection
      headingId="button-disabled-matrix-heading"
      heading="Disabled Button variants by size"
      disabled={true}
    />
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
