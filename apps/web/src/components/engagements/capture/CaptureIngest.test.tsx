import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CaptureIngest } from "./CaptureIngest.client";

/**
 * Wave 3 K2/K4 — the staged capture flow. Extraction takes real seconds
 * (10–25s live), so the async window between "saved" and "proposals ready"
 * is the demo's most fragile moment: these tests pin the progress states
 * across that window using deferred fetch promises.
 */

type Deferred<T> = { promise: Promise<T>; resolve: (v: T) => void };

function deferred<T>(): Deferred<T> {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function jsonResponse(body: unknown, ok = true, status = ok ? 200 : 500) {
  return {
    ok,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  };
}

function proposal(id: string, status = "pending") {
  return {
    id,
    engagement_id: "e1",
    source_event_id: "ev1",
    proposal_kind: "node",
    payload: { node_type: "decision", title: "Edge inference" },
    rationale: null,
    status,
    created_at: "2026-08-11T00:00:00Z",
    decided_at: null,
    decided_by: null,
    result_node_id: null,
    result_edge_id: null,
  };
}

describe("CaptureIngest", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("walks the honest progress states across the async extraction window", async () => {
    const ingestGate = deferred<unknown>();
    const extractGate = deferred<unknown>();
    const calls: Array<{ url: string; body: string }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: { body?: unknown }) => {
        calls.push({ url, body: typeof init?.body === "string" ? init.body : "" });
        if (url.includes("/ingest")) {
          return ingestGate.promise;
        }
        return extractGate.promise;
      }),
    );
    // The scroll target the success state jumps to (Needs-you lives outside
    // this component on the Brief).
    const needsYou = document.createElement("section");
    needsYou.setAttribute("data-tour", "brief-needs-you");
    const scrollSpy = vi.fn();
    needsYou.scrollIntoView = scrollSpy;
    document.body.appendChild(needsYou);

    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<CaptureIngest engagementId="e1" onChanged={onChanged} />);

    await user.type(screen.getByLabelText("Interaction"), "From: dana@acme.com\n\nKickoff notes");
    await user.click(screen.getByRole("button", { name: "Capture" }));

    // Stage 1 — saving, until the ingest request lands.
    expect(await screen.findByText("Saving")).toBeInTheDocument();
    expect(screen.queryByText(/Extracting/)).not.toBeInTheDocument();

    ingestGate.resolve(jsonResponse({ event: { id: "ev1" }, extract_error: null }, true, 201));

    // Stage 2 — extracting, with the honest expectation set. This is the
    // 10–25s async window; the UI must hold this state until /extract returns.
    expect(await screen.findByText(/Extracting \(usually 10–25s\)/)).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();

    extractGate.resolve(jsonResponse({ proposals: [proposal("p1"), proposal("p2")] }));

    // Stage 3 — done: count surfaces, proposals refresh, Needs-you scrolls in.
    expect(await screen.findByText(/2 proposals ready — review below/)).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(scrollSpy).toHaveBeenCalled());

    // The staged contract with the BFF: ingest opts out of chained
    // extraction, then /extract is driven with the new event id.
    expect(calls[0]!.url).toContain("/api/bff/engagements/e1/ingest");
    expect(JSON.parse(calls[0]!.body)).toMatchObject({ source: "email", extract: false });
    expect(calls[1]!.url).toContain("/api/bff/engagements/e1/extract");
    expect(JSON.parse(calls[1]!.body)).toEqual({ event_id: "ev1" });

    // The box clears for the next artifact.
    expect(screen.getByLabelText("Interaction")).toHaveValue("");
    needsYou.remove();
  });

  it("says so plainly when extraction finds nothing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/ingest")) {
          return Promise.resolve(jsonResponse({ event: { id: "ev1" } }, true, 201));
        }
        return Promise.resolve(jsonResponse({ proposals: [] }));
      }),
    );
    const user = userEvent.setup();
    render(<CaptureIngest engagementId="e1" />);

    await user.type(screen.getByLabelText("Interaction"), "hi");
    await user.click(screen.getByRole("button", { name: "Capture" }));

    expect(await screen.findByText(/extraction found no proposals/)).toBeInTheDocument();
  });

  it("surfaces an ingest failure without pretending to extract", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(jsonResponse({ error: "tenant misconfigured" }, false, 502)),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<CaptureIngest engagementId="e1" />);

    await user.type(screen.getByLabelText("Interaction"), "hi");
    await user.click(screen.getByRole("button", { name: "Capture" }));

    expect(await screen.findByText(/Could not save the interaction/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps the saved event when extraction fails, and says both", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/ingest")) {
          return Promise.resolve(jsonResponse({ event: { id: "ev1" } }, true, 201));
        }
        return Promise.resolve(jsonResponse({ error: "llm timeout" }, false, 502));
      }),
    );
    const user = userEvent.setup();
    render(<CaptureIngest engagementId="e1" />);

    await user.type(screen.getByLabelText("Interaction"), "hi");
    await user.click(screen.getByRole("button", { name: "Capture" }));

    expect(await screen.findByText(/Saved — but extraction failed/)).toBeInTheDocument();
    expect(screen.getByText(/can be retried/)).toBeInTheDocument();
  });

  it("reads a picked .txt file into the paste box", async () => {
    const user = userEvent.setup();
    render(<CaptureIngest engagementId="e1" />);

    const file = new File(["[9:14 AM] Priya Shah: orin build v0.3 flashed"], "slack-export.txt", {
      type: "text/plain",
    });
    await user.upload(screen.getByLabelText("Pick a .txt file"), file);

    await waitFor(() =>
      expect(screen.getByLabelText("Interaction")).toHaveValue(
        "[9:14 AM] Priya Shah: orin build v0.3 flashed",
      ),
    );
  });

  it("marks the paste box as the tour's capture-input target", () => {
    render(<CaptureIngest engagementId="e1" />);
    const wrapper = document.querySelector('[data-tour="capture-input"]');
    expect(wrapper).not.toBeNull();
    expect(wrapper!.querySelector("#capture-content")).not.toBeNull();
  });

  it("disables Capture until there is text", async () => {
    const user = userEvent.setup();
    render(<CaptureIngest engagementId="e1" />);

    expect(screen.getByRole("button", { name: "Capture" })).toBeDisabled();
    await user.type(screen.getByLabelText("Interaction"), "x");
    expect(screen.getByRole("button", { name: "Capture" })).toBeEnabled();
  });
});
