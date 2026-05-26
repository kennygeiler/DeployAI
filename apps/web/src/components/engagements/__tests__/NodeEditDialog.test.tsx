import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NodeEditDialog } from "@/components/engagements/NodeEditDialog.client";
import type { MatrixNode } from "@/lib/bff/matrix-types";

const baseNode: MatrixNode = {
  id: "node-1",
  engagement_id: "eng-1",
  node_type: "stakeholder",
  title: "Alice",
  identity_node_id: null,
  attributes: { team: "ops" },
  status: null,
  evidence_event_ids: [],
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("NodeEditDialog", () => {
  it("PATCHes the node and calls onSaved with the server response on success", async () => {
    const onSaved = vi.fn();
    const onClose = vi.fn();
    const captured: Array<{ url: string; init: { method?: string; body?: string } }> = [];
    const fetchMock = vi.fn((url: string, init?: { method?: string; body?: string }) => {
      captured.push({ url, init: init ?? {} });
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            node: { ...baseNode, title: "Alice Renamed" },
            source: "cp",
          }),
        text: () => Promise.resolve(""),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <NodeEditDialog
        engagementId="eng-1"
        node={baseNode}
        open={true}
        onClose={onClose}
        onSaved={onSaved}
      />,
    );

    const titleInput = screen.getByLabelText(/title/i) as HTMLInputElement;
    expect(titleInput.value).toBe("Alice");
    fireEvent.change(titleInput, { target: { value: "Alice Renamed" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    const savedArg = onSaved.mock.calls[0]?.[0] as { title?: string } | undefined;
    expect(savedArg?.title).toBe("Alice Renamed");
    expect(onClose).toHaveBeenCalled();

    expect(captured.length).toBe(1);
    const { url, init } = captured[0]!;
    expect(url).toBe("/api/bff/engagements/eng-1/matrix/nodes/node-1");
    expect(init.method).toBe("PATCH");
    const body = JSON.parse(init.body ?? "{}") as {
      title: string;
      node_type: string;
      attributes: Record<string, unknown>;
    };
    expect(body).toEqual({
      title: "Alice Renamed",
      node_type: "stakeholder",
      attributes: { team: "ops" },
    });
  });

  it("shows the server error and does not call onSaved when the PATCH fails", async () => {
    const onSaved = vi.fn();
    const onClose = vi.fn();
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 422,
        json: () => Promise.resolve({ error: "invalid node_type" }),
        text: () => Promise.resolve("invalid node_type"),
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <NodeEditDialog
        engagementId="eng-1"
        node={baseNode}
        open={true}
        onClose={onClose}
        onSaved={onSaved}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(onSaved).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("blocks save with invalid JSON attributes and shows an error", async () => {
    const onSaved = vi.fn();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(
      <NodeEditDialog
        engagementId="eng-1"
        node={baseNode}
        open={true}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    );

    const attrs = screen.getByLabelText(/attributes/i) as HTMLTextAreaElement;
    fireEvent.change(attrs, { target: { value: "{not json" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });
});
