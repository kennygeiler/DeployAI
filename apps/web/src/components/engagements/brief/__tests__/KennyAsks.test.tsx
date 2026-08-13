import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { KennyAsks } from "@/components/engagements/brief/KennyAsks.client";
import { clearCachedFetchForTests } from "@/lib/hooks/useCachedFetch";

const ASKS = [
  {
    id: "a1b2c3d4e5f60718",
    rule: "risk_unmitigated",
    severity: "high",
    target_node_id: "n1",
    title: "What is being done about “Calibration slip”?",
    why: "Risk “Calibration slip” is open with no mitigation on record.",
    remedy_kind: "answer",
  },
  {
    id: "0918273645abcdef",
    rule: "engagement_silent",
    severity: "medium",
    target_node_id: null,
    title: "Forward the latest status thread",
    why: "Nothing has landed in the record for over 14 days",
    remedy_kind: "forward",
  },
];

function stubFetch(opts: { asks?: unknown[]; failGet?: boolean; failPost?: boolean } = {}) {
  const calls: Array<{ url: string; method: string; body: string }> = [];
  const fetchMock = vi.fn((url: string, init?: { method?: string; body?: unknown }) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: typeof init?.body === "string" ? init.body : "" });
    if (method === "POST") {
      if (opts.failPost) {
        return Promise.resolve({ ok: false, status: 500, text: () => Promise.resolve("boom") });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ dismissal: { ask_id: "x", dismissed_at: "now", snooze_until: null } }),
      });
    }
    if (opts.failGet) {
      return Promise.resolve({ ok: false, status: 404, text: () => Promise.resolve("nope") });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ asks: opts.asks ?? ASKS }) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("KennyAsks", () => {
  beforeEach(() => {
    clearCachedFetchForTests();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders one card per ask with title, why, and remedies", async () => {
    stubFetch();
    render(<KennyAsks engagementId="e1" onOpenCapture={vi.fn()} />);

    await waitFor(() => screen.getByTestId("kenny-asks"));
    const riskCard = screen.getByTestId("kenny-ask-risk_unmitigated");
    expect(riskCard.textContent).toContain("What is being done about");
    expect(riskCard.textContent).toContain("no mitigation on record");
    expect(screen.getByTestId("kenny-ask-engagement_silent")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Open Capture" })).toHaveLength(2);
  });

  it("renders nothing when there are no asks (quiet empty state)", async () => {
    const calls = stubFetch({ asks: [] });
    const { container } = render(<KennyAsks engagementId="e1" onOpenCapture={vi.fn()} />);

    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    await waitFor(() => expect(container.textContent).toBe(""));
    expect(screen.queryByTestId("kenny-asks")).toBeNull();
  });

  it("renders nothing when the endpoint is unavailable", async () => {
    const calls = stubFetch({ failGet: true });
    const { container } = render(<KennyAsks engagementId="e1" onOpenCapture={vi.fn()} />);

    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    await waitFor(() => expect(container.textContent).toBe(""));
  });

  it("switches to Capture via the remedy button", async () => {
    stubFetch();
    const onOpenCapture = vi.fn();
    const user = userEvent.setup();
    render(<KennyAsks engagementId="e1" onOpenCapture={onOpenCapture} />);

    await waitFor(() => screen.getByTestId("kenny-asks"));
    await user.click(screen.getAllByRole("button", { name: "Open Capture" })[0]!);
    expect(onOpenCapture).toHaveBeenCalledTimes(1);
  });

  it("dismisses an ask through the BFF and refreshes the list", async () => {
    const calls = stubFetch();
    const user = userEvent.setup();
    render(<KennyAsks engagementId="e1" onOpenCapture={vi.fn()} />);

    await waitFor(() => screen.getByTestId("kenny-asks"));
    await user.click(screen.getByRole("button", { name: `Dismiss: ${ASKS[0]!.title}` }));

    await waitFor(() =>
      expect(
        calls.some(
          (c) =>
            c.method === "POST" &&
            c.url === `/api/bff/engagements/e1/gap-asks/${ASKS[0]!.id}/dismiss`,
        ),
      ).toBe(true),
    );
    // The cache invalidation refetches the list.
    await waitFor(() =>
      expect(calls.filter((c) => c.method === "GET").length).toBeGreaterThanOrEqual(2),
    );
  });

  it("snoozes an ask for 7 days", async () => {
    const calls = stubFetch();
    const user = userEvent.setup();
    render(<KennyAsks engagementId="e1" onOpenCapture={vi.fn()} />);

    await waitFor(() => screen.getByTestId("kenny-asks"));
    await user.click(screen.getAllByRole("button", { name: "Snooze 7d" })[0]!);

    await waitFor(() => {
      const post = calls.find(
        (c) =>
          c.method === "POST" && c.url === `/api/bff/engagements/e1/gap-asks/${ASKS[0]!.id}/snooze`,
      );
      expect(post).toBeTruthy();
      expect(JSON.parse(post!.body)).toEqual({ days: 7 });
    });
  });
});
