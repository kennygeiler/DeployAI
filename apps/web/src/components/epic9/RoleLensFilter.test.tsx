import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import type { MatrixNode } from "@/lib/bff/matrix-types";
import { applyRoleLens, type RoleLens } from "@/lib/matrix/role-lens";

import { RoleLensFilter } from "./RoleLensFilter.client";

function mkNode(id: string, node_type: string, title: string): MatrixNode {
  return {
    id,
    engagement_id: "e1",
    node_type,
    title,
    identity_node_id: null,
    attributes: {},
    status: null,
    evidence_event_ids: [],
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
  };
}

const ALL_NODES: MatrixNode[] = [
  mkNode("n1", "stakeholder", "Mayor Chen"),
  mkNode("n2", "system", "LiDAR ingest"),
  mkNode("n3", "risk", "Calibration slip"),
];

/**
 * Harness mirroring how `EngagementDetail` wires the lens: the
 * `RoleLensFilter` drives state and `applyRoleLens` filters the nodes
 * that get rendered. Exercises the integration without coupling to the
 * full engagement-detail page.
 */
function Harness() {
  const [role, setRole] = React.useState<RoleLens>("all");
  const { nodes } = applyRoleLens(ALL_NODES, [], role);
  return (
    <>
      <RoleLensFilter value={role} onChange={setRole} />
      <ul>
        {nodes.map((n) => (
          <li key={n.id}>{n.title}</li>
        ))}
      </ul>
    </>
  );
}

describe("RoleLensFilter", () => {
  it("renders all four role options with the current value", () => {
    render(<RoleLensFilter value="all" onChange={() => {}} />);
    const select = screen.getByLabelText("Role lens") as HTMLSelectElement;
    expect(select.value).toBe("all");
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toEqual(["all", "fde", "deployment_strategist", "biz_dev"]);
  });

  it("calls onChange with the new role when the user picks one", async () => {
    const onChange = vi.fn();
    render(<RoleLensFilter value="all" onChange={onChange} />);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Role lens"), "fde");
    expect(onChange).toHaveBeenCalledWith("fde");
  });

  it("default 'all' shows every node; switching to 'fde' hides stakeholders; switching back restores them", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    // Default — all three nodes visible.
    expect(screen.getByText("Mayor Chen")).toBeTruthy();
    expect(screen.getByText("LiDAR ingest")).toBeTruthy();
    expect(screen.getByText("Calibration slip")).toBeTruthy();

    // FDE — stakeholder ("Mayor Chen") is hidden, system + risk remain.
    await user.selectOptions(screen.getByLabelText("Role lens"), "fde");
    expect(screen.queryByText("Mayor Chen")).toBeNull();
    expect(screen.getByText("LiDAR ingest")).toBeTruthy();
    expect(screen.getByText("Calibration slip")).toBeTruthy();

    // Back to All — stakeholder is restored.
    await user.selectOptions(screen.getByLabelText("Role lens"), "all");
    expect(screen.getByText("Mayor Chen")).toBeTruthy();
  });
});
