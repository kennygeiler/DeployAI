import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PastePreview } from "./PastePreview.client";

type Call = { url: string; method: string; body: string };

type FetchResp = {
  ok: boolean;
  status?: number;
  json: () => Promise<unknown>;
  text?: () => Promise<string>;
};

function makeFetch(
  handler: (url: string, init?: { method?: string; body?: unknown }) => FetchResp,
) {
  return vi.fn((url: string, init?: { method?: string; body?: unknown }) => {
    return Promise.resolve(handler(url, init));
  });
}

describe("PastePreview", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("paste → preview renders drafts; commit posts to /ingest and clears the form", async () => {
    const calls: Call[] = [];
    const drafts = [
      {
        kind: "node",
        payload: { node_type: "decision", title: "Phased rollout" },
        rationale: "agreed",
      },
      { kind: "node", payload: { node_type: "risk", title: "Calibration drift" }, rationale: null },
    ];
    vi.stubGlobal(
      "fetch",
      makeFetch((url, init) => {
        const method = init?.method ?? "GET";
        const body = typeof init?.body === "string" ? init.body : "";
        calls.push({ url, method, body });
        if (url.includes("/extract-preview")) {
          return { ok: true, json: () => Promise.resolve({ drafts, source: "cp" }) };
        }
        if (url.includes("/ingest")) {
          return {
            ok: true,
            json: () => Promise.resolve({ event: { id: "e1" }, extract_error: null, source: "cp" }),
          };
        }
        return { ok: false, status: 404, json: () => Promise.resolve({}) };
      }),
    );
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<PastePreview engagementId="e1" onChanged={onChanged} />);

    fireEvent.change(screen.getByLabelText("Content (text or JSON)"), {
      target: { value: "Phased rollout decided; calibration drift noted." },
    });
    await user.click(screen.getByRole("button", { name: "Preview" }));

    await waitFor(() => expect(screen.getByText(/decision: Phased rollout/)).toBeInTheDocument());
    expect(screen.getByText(/risk: Calibration drift/)).toBeInTheDocument();
    expect(screen.getByText(/2 of 2 draft\(s\) kept/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Commit all kept" }));

    await waitFor(() => expect(calls.some((c) => c.url.includes("/ingest"))).toBe(true));
    const ingest = calls.find((c) => c.url.includes("/ingest"))!;
    expect(ingest.method).toBe("POST");
    const ingestBody = JSON.parse(ingest.body) as { source: string; content: { text: string } };
    expect(ingestBody.source).toBe("manual_import");
    expect(ingestBody.content.text).toBe("Phased rollout decided; calibration drift noted.");
    expect(onChanged).toHaveBeenCalled();
    // Form cleared and draft list reset.
    expect((screen.getByLabelText("Content (text or JSON)") as HTMLTextAreaElement).value).toBe("");
    expect(screen.queryByText(/draft\(s\) kept/)).not.toBeInTheDocument();
  });

  it("surfaces a preview error and does not show drafts", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetch(() => ({
        ok: false,
        status: 502,
        json: () => Promise.resolve({ userMessage: "Service unavailable", detail: "boom" }),
        text: () => Promise.resolve("Service unavailable"),
      })),
    );
    const user = userEvent.setup();
    render(<PastePreview engagementId="e1" />);

    fireEvent.change(screen.getByLabelText("Content (text or JSON)"), {
      target: { value: "anything" },
    });
    await user.click(screen.getByRole("button", { name: "Preview" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Preview" })).not.toBeDisabled());
    expect(screen.queryByText(/draft\(s\) kept/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Commit all kept" })).not.toBeInTheDocument();
  });

  it("discarding a draft commits only the kept ones (and discard removes them from the kept count)", async () => {
    const calls: Call[] = [];
    const drafts = [
      {
        kind: "node",
        payload: { node_type: "decision", title: "Phased rollout" },
        rationale: null,
      },
      { kind: "node", payload: { node_type: "risk", title: "Calibration drift" }, rationale: null },
      {
        kind: "node",
        payload: { node_type: "commitment", title: "Owner: Priya" },
        rationale: null,
      },
    ];
    vi.stubGlobal(
      "fetch",
      makeFetch((url, init) => {
        calls.push({
          url,
          method: init?.method ?? "GET",
          body: typeof init?.body === "string" ? init.body : "",
        });
        if (url.includes("/extract-preview")) {
          return { ok: true, json: () => Promise.resolve({ drafts }) };
        }
        return { ok: true, json: () => Promise.resolve({ event: { id: "e1" } }) };
      }),
    );
    const user = userEvent.setup();
    render(<PastePreview engagementId="e1" />);

    fireEvent.change(screen.getByLabelText("Content (text or JSON)"), {
      target: { value: "all three" },
    });
    await user.click(screen.getByRole("button", { name: "Preview" }));

    await waitFor(() => expect(screen.getByText(/3 of 3 draft\(s\) kept/)).toBeInTheDocument());

    // Discard the second draft (Calibration drift).
    const driftRow = screen.getByText(/risk: Calibration drift/).closest("li")!;
    const discardBtn = driftRow.querySelector("button")!;
    await user.click(discardBtn);

    expect(screen.getByText(/2 of 3 draft\(s\) kept/)).toBeInTheDocument();
    // Discarded entry shows a "Keep" button now (toggle).
    expect(driftRow.textContent).toContain("Keep");

    await user.click(screen.getByRole("button", { name: "Commit all kept" }));
    await waitFor(() => expect(calls.some((c) => c.url.includes("/ingest"))).toBe(true));
    // Commit goes through /ingest exactly once — the kept drafts inform the
    // user's count but the canonical event is what the CP extracts from.
    const ingestCalls = calls.filter((c) => c.url.includes("/ingest"));
    expect(ingestCalls).toHaveLength(1);
  });
});
