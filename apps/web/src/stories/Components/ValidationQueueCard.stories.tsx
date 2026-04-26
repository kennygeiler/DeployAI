import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";

import { CitationChip, ValidationQueueCard, type ValidationQueueState } from "@deployai/shared-ui";

const meta: Meta<typeof ValidationQueueCard> = {
  title: "Components/ValidationQueueCard",
  component: ValidationQueueCard,
  tags: ["autodocs"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Single User Validation / Solidification queue item (UX-DR10). Modify and Reject require a response reason. Confirm and Defer do not.",
      },
    },
  },
} satisfies Meta<typeof ValidationQueueCard>;

export default meta;
type Story = StoryObj<typeof meta>;

const preview = {
  citationId: "n-9",
  retrievalPhase: "P5",
  confidence: "0.88",
  signedTimestamp: "2026-01-20T10:00:00Z",
};

function DemoChip({ label }: { label: string }) {
  const [ex, setEx] = useState(false);
  return (
    <CitationChip
      label={label}
      expanded={ex}
      onToggleExpand={() => {
        setEx((v) => !v);
      }}
      preview={preview}
      onViewEvidence={() => {}}
      onOverride={() => {}}
      onCopyLink={() => {}}
      onCiteInOverride={() => {}}
    />
  );
}

const chips = (
  <>
    <DemoChip label="L-201 — cable scope" />
  </>
);

function Interactive({
  state,
  log = true,
}: {
  state: ValidationQueueState;
  log?: boolean;
}) {
  const [lines, setLines] = useState<string[]>([]);
  const push = (s: string) => {
    setLines((L) => [...L, s]);
  };
  return (
    <div className="max-w-3xl space-y-4">
      <ValidationQueueCard
        proposedFact="NYC DOT will complete the Section 15 handhole run before March 1."
        supportingEvidence={chips}
        confidence="0.88 (high)"
        state={state}
        onConfirm={async () => {
          await new Promise((r) => {
            setTimeout(r, 200);
          });
          if (log) {
            push("confirm");
          }
        }}
        onModify={async (reason) => {
          await new Promise((r) => {
            setTimeout(r, 200);
          });
          if (log) {
            push(`modify: ${reason}`);
          }
        }}
        onReject={async (reason) => {
          await new Promise((r) => {
            setTimeout(r, 200);
          });
          if (log) {
            push(`reject: ${reason}`);
          }
        }}
        onDefer={async () => {
          await new Promise((r) => {
            setTimeout(r, 200);
          });
          if (log) {
            push("defer");
          }
        }}
      />
      {log && lines.length > 0 ? (
        <pre className="text-body bg-paper-200 max-h-40 overflow-auto rounded p-2 font-mono text-xs">
          {lines.join("\n")}
        </pre>
      ) : null}
    </div>
  );
}

export const Unresolved: Story = {
  render: () => <Interactive state="unresolved" />,
};

export const InReview: Story = {
  render: () => <Interactive state="in-review" />,
};

export const Resolved: Story = {
  render: () => <Interactive state="resolved" log={false} />,
};

export const Escalated: Story = {
  render: () => <Interactive state="escalated" log={false} />,
};
