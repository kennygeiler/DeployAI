import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";

import { OverrideComposer } from "@deployai/shared-ui";

const evidence = [
  { id: "n1", label: "Learning L-42 — Q2 scope" },
  { id: "n2", label: "Transcript T-9 — standup" },
  { id: "n3", label: "Email thread E-11 — vendor" },
];

const meta: Meta<typeof OverrideComposer> = {
  title: "Components/OverrideComposer",
  component: OverrideComposer,
  tags: ["autodocs"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Trust-repair override form (UX-DR8). Cmd+Enter submits. Propagation column is stub copy until graph APIs exist.",
      },
    },
  },
} satisfies Meta<typeof OverrideComposer>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = {
  args: {
    evidenceOptions: evidence,
    onSubmit: async () => {
      await new Promise((r) => {
        setTimeout(r, 400);
      });
    },
  },
};

export const WithHandler: Story = {
  render: function R() {
    const [log, setLog] = useState<string>("");
    return (
      <div className="max-w-4xl space-y-4">
        <OverrideComposer
          evidenceOptions={evidence}
          onSubmit={async (p) => {
            await new Promise((x) => {
              setTimeout(x, 300);
            });
            setLog(JSON.stringify(p, null, 2));
          }}
        />
        {log ? (
          <pre className="text-body bg-paper-200 max-h-48 overflow-auto rounded p-3 font-mono text-xs">
            {log}
          </pre>
        ) : null}
      </div>
    );
  },
};
