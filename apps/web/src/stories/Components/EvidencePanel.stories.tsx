import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { lazy, Suspense, useState } from "react";

import { CitationChip, EvidencePanel, type CitationPreview } from "@deployai/shared-ui";

const preview: CitationPreview = {
  citationId: "2d4437ee-9336-441e-ab57-121b81ee57a4",
  retrievalPhase: "oracle",
  confidence: "0.94",
  signedTimestamp: "2026-04-23T10:03:00Z",
};

const baseMeta = {
  sourceType: "Email thread",
  timestamp: "2026-04-20T16:12:00Z",
  phase: "P4 — Production",
  confidence: "0.89",
  supersession: "current" as const,
};

const meta: Meta<typeof EvidencePanel> = {
  title: "Components/EvidencePanel",
  component: EvidencePanel,
  tags: ["autodocs"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Inline evidence (Story 7-2, UX-DR5). " +
          "Use with `Suspense` + `React.lazy` when the payload is async (In-Meeting ≤ 8 s). " +
          "Keyboard/SR: panel is an `article` with a labelled title; " +
          "state changes are announced via `aria-live=polite` (visually in the docs canvas the live region is `sr-only`).",
      },
    },
  },
} satisfies Meta<typeof EvidencePanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Loaded: Story = {
  name: "Loaded + highlight",
  args: {
    retrievalPhase: "oracle",
    metadata: baseMeta,
    state: "loaded",
    bodyText: "The contractor committed to a beta cut by May 1 for the program office review.",
    evidenceSpan: { start: 4, end: 23, source_ref: "n1" },
  },
};

export const Loading: Story = {
  args: {
    retrievalPhase: "oracle",
    metadata: baseMeta,
    state: "loading",
  },
};

export const Degraded: Story = {
  name: "Degraded (Cartographer / sync lag)",
  args: {
    retrievalPhase: "cartographer",
    metadata: { ...baseMeta, supersession: "unknown" },
    state: "degraded",
    bodyText: "The contractor committed to a beta cut by May 1 f…",
    evidenceSpan: { start: 4, end: 23, source_ref: "n1" },
  },
};

export const Tombstoned: Story = {
  args: {
    retrievalPhase: "oracle",
    metadata: { ...baseMeta, supersession: "tombstoned" },
    state: "tombstoned",
    tombstoneMessage: "Removed under retention policy ABC-12 (ticket RT-9001).",
  },
};

const LazyBody = lazy(async () => {
  await new Promise((r) => {
    setTimeout(r, 400);
  });
  return {
    default: function Lazy() {
      return <p>Async body resolved (simulated network).</p>;
    },
  };
});

export const AsyncSuspense: Story = {
  name: "Async body (lazy + Suspense)",
  render: function Render() {
    return (
      <Suspense
        fallback={<EvidencePanel retrievalPhase="oracle" metadata={baseMeta} state="loading" />}
      >
        <EvidencePanel retrievalPhase="oracle" metadata={baseMeta} state="loaded">
          <LazyBody />
        </EvidencePanel>
      </Suspense>
    );
  },
};

function ChipWithPanel() {
  const [open, setOpen] = useState(true);
  return (
    <div className="max-w-2xl space-y-3 font-sans text-sm text-foreground">
      <p>Citation chip + expanded panel (default composition for Digest / In-Meeting).</p>
      <div className="flex flex-wrap items-start gap-2">
        <CitationChip
          label="10:03 standup"
          expanded={open}
          onToggleExpand={() => {
            setOpen((o) => !o);
          }}
          visualState="default"
          variant="inline"
          preview={preview}
          onViewEvidence={() => {}}
          onOverride={() => {}}
          onCopyLink={() => {}}
          onCiteInOverride={() => {}}
        />
      </div>
      {open ? (
        <EvidencePanel
          retrievalPhase="oracle"
          metadata={baseMeta}
          state="loaded"
          bodyText="The contractor committed to a beta cut by May 1 for the program office review."
          evidenceSpan={{ start: 4, end: 23, source_ref: "n1" }}
        />
      ) : null}
    </div>
  );
}

export const WithCitationChip: Story = {
  name: "Keyboard/SR — chip + inline panel",
  render: () => <ChipWithPanel />,
  parameters: {
    docs: {
      description: {
        story: "Tab to the chip, Enter/Space toggles; expand to read the `article` below.",
      },
    },
  },
};
