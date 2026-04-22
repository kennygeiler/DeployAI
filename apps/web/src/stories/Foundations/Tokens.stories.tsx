import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { colors, radii, shadows, spacing, typeScale } from "@deployai/design-tokens";

/**
 * Foundations / Tokens — renders every token domain so UX can review the
 * palette, type ramp, spacing ladder, radii, and shadow library in one
 * place. Satisfies UX-DR1 and UX-DR2.
 */
const meta = {
  title: "Foundations/Tokens",
  parameters: {
    layout: "fullscreen",
    docs: {
      description: {
        component:
          "Canonical render of every token in @deployai/design-tokens. Use this surface for design review and to spot drift from ux-design-specification.md §Foundations.",
      },
    },
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

type Scale = Record<string, string>;

function Swatch({ name, value }: { name: string; value: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--spacing-3)",
        padding: "var(--spacing-2)",
        borderRadius: "var(--radius-md)",
        border: "1px solid var(--color-paper-400)",
        background: "var(--color-paper-100)",
      }}
    >
      <div
        aria-hidden
        style={{
          width: 48,
          height: 48,
          borderRadius: "var(--radius-sm)",
          background: value,
          border: "1px solid var(--color-paper-400)",
          flexShrink: 0,
        }}
      />
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-small)",
            color: "var(--color-ink-800)",
          }}
        >
          {name}
        </span>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-ink-600)",
          }}
        >
          {value}
        </span>
      </div>
    </div>
  );
}

/**
 * Slugify a heading to a CSS-selector-safe anchor id (lowercase, alnum + `-`).
 * Protects against headings like `Spacing (4 px base)` that would otherwise
 * emit `#section-spacing-(4-px-base)` and need manual escaping at the call
 * site.
 */
function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function Section({
  heading,
  description,
  children,
}: {
  heading: string;
  description?: string;
  children: React.ReactNode;
}) {
  const anchorId = `section-${slugify(heading)}`;
  return (
    <section
      aria-labelledby={anchorId}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--spacing-4)",
        padding: "var(--spacing-6)",
        borderBottom: "1px solid var(--color-paper-300)",
      }}
    >
      <header style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-1)" }}>
        <h2
          id={anchorId}
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-heading)",
            fontWeight: 600,
            color: "var(--color-ink-950)",
            margin: 0,
          }}
        >
          {heading}
        </h2>
        {description ? (
          <p
            style={{
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-body)",
              color: "var(--color-ink-600)",
              margin: 0,
              maxWidth: "var(--reading-measure-max)",
            }}
          >
            {description}
          </p>
        ) : null}
      </header>
      {children}
    </section>
  );
}

function PaletteScale({ name, scale }: { name: string; scale: Scale }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-2)" }}>
      <h3
        style={{
          fontFamily: "var(--font-sans)",
          fontSize: "var(--text-small)",
          fontWeight: 600,
          color: "var(--color-ink-800)",
          margin: 0,
          textTransform: "capitalize",
        }}
      >
        {name}
      </h3>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
          gap: "var(--spacing-2)",
        }}
      >
        {Object.entries(scale).map(([step, value]) => (
          <Swatch key={step} name={`${name}-${step}`} value={value} />
        ))}
      </div>
    </div>
  );
}

export const Palette: Story = {
  render: () => (
    <Section
      heading="Color"
      description="Neutral-dominant calm-authority palette. No primary green. Every body-text pair meets WCAG AA (≥ 4.5:1); citation chips and primary text reach AAA (≥ 7:1)."
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-6)" }}>
        {Object.entries(colors).map(([name, scale]) => (
          <PaletteScale key={name} name={name} scale={scale as Scale} />
        ))}
      </div>
    </Section>
  ),
};

export const TypeRamp: Story = {
  render: () => (
    <Section
      heading="Typography"
      description="Inter for UI and body text, IBM Plex Mono for citations, IDs, and code. Prose surfaces enforce a 60–72 ch reading measure."
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-4)" }}>
        {Object.entries(typeScale).map(([step, scale]) => (
          <div
            key={step}
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--spacing-1)",
              padding: "var(--spacing-3)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--color-paper-300)",
              background: "var(--color-paper-100)",
            }}
          >
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-micro)",
                color: "var(--color-ink-600)",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
              }}
            >
              {step} · {scale.size} / {scale.lineHeight} · {scale.weight}
            </span>
            <p
              style={{
                fontFamily: "var(--font-sans)",
                fontSize: scale.size,
                lineHeight: scale.lineHeight,
                fontWeight: scale.weight,
                letterSpacing: scale.letterSpacing,
                color: "var(--color-ink-950)",
                margin: 0,
              }}
            >
              The DeployAI deployment of record is your calm, evidenced companion.
            </p>
          </div>
        ))}
      </div>
    </Section>
  ),
};

export const Spacing: Story = {
  render: () => (
    <Section
      heading="Spacing (4 px base)"
      description="All surfaces compose on a 4 px base. No free-form margins or paddings outside this ladder."
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-2)" }}>
        {Object.entries(spacing).map(([key, value]) => (
          <div
            key={key}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--spacing-3)",
              padding: "var(--spacing-2)",
              borderRadius: "var(--radius-sm)",
              background: "var(--color-paper-200)",
            }}
          >
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-small)",
                color: "var(--color-ink-800)",
                minWidth: 72,
              }}
            >
              space-{key.replace(/_/g, "-")}
            </span>
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-micro)",
                color: "var(--color-ink-600)",
                minWidth: 48,
              }}
            >
              {value}
            </span>
            <div
              aria-hidden
              style={{
                height: 12,
                width: value,
                background: "var(--color-evidence-700)",
                borderRadius: "var(--radius-sm)",
              }}
            />
          </div>
        ))}
      </div>
    </Section>
  ),
};

export const RadiiAndShadows: Story = {
  render: () => (
    <Section
      heading="Radii & Shadows"
      description="Subtle rounding and very soft elevation cues. Sharp-edged primitives only where legibility demands it."
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-6)" }}>
        <div>
          <h3
            style={{
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-small)",
              fontWeight: 600,
              color: "var(--color-ink-800)",
              margin: "0 0 var(--spacing-2)",
            }}
          >
            Radii
          </h3>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "var(--spacing-3)",
            }}
          >
            {Object.entries(radii).map(([key, value]) => (
              <div
                key={key}
                style={{
                  width: 96,
                  height: 96,
                  background: "var(--color-paper-300)",
                  border: "1px solid var(--color-paper-400)",
                  borderRadius: value,
                  display: "flex",
                  alignItems: "flex-end",
                  justifyContent: "center",
                  padding: "var(--spacing-1)",
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-micro)",
                  color: "var(--color-ink-800)",
                }}
              >
                {key}
              </div>
            ))}
          </div>
        </div>
        <div>
          <h3
            style={{
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-small)",
              fontWeight: 600,
              color: "var(--color-ink-800)",
              margin: "0 0 var(--spacing-2)",
            }}
          >
            Shadows
          </h3>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "var(--spacing-6)",
              padding: "var(--spacing-4)",
            }}
          >
            {Object.entries(shadows).map(([key, value]) => (
              <div
                key={key}
                style={{
                  width: 128,
                  height: 96,
                  background: "var(--color-paper-100)",
                  borderRadius: "var(--radius-md)",
                  boxShadow: value,
                  display: "flex",
                  alignItems: "flex-end",
                  justifyContent: "center",
                  padding: "var(--spacing-1)",
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-micro)",
                  color: "var(--color-ink-800)",
                }}
              >
                {key}
              </div>
            ))}
          </div>
        </div>
      </div>
    </Section>
  ),
};
