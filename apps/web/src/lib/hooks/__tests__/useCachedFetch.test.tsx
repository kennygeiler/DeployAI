import { act, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearCachedFetchForTests,
  invalidateCachedFetch,
  useCachedFetch,
} from "@/lib/hooks/useCachedFetch";

function Probe({ url, id }: { url: string | null; id: string }) {
  const { data, error, pending } = useCachedFetch<{ value?: string }>(url);
  return (
    <output data-testid={id}>
      {pending ? "pending" : error ? `error:${error}` : `data:${data?.value ?? ""}`}
    </output>
  );
}

describe("useCachedFetch", () => {
  beforeEach(() => {
    clearCachedFetchForTests();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches, caches, and serves the cached value to later mounts without refetching", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ value: "one" }) }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const first = render(<Probe url="/api/x" id="a" />);
    await waitFor(() => expect(screen.getByTestId("a").textContent).toBe("data:one"));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    first.unmount();

    // Second mount inside the stale window: cached value, no new request.
    render(<Probe url="/api/x" id="b" />);
    expect(screen.getByTestId("b").textContent).toBe("data:one");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("dedupes concurrent mounts into one request", async () => {
    let resolveJson: (v: unknown) => void = () => {};
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => new Promise((res) => (resolveJson = res)),
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <>
        <Probe url="/api/y" id="a" />
        <Probe url="/api/y" id="b" />
      </>,
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => {
      // Flush the microtask queue so the fetcher reaches json() and swaps
      // in the real resolver before we resolve it.
      await Promise.resolve();
      resolveJson({ value: "shared" });
    });
    await waitFor(() => expect(screen.getByTestId("a").textContent).toBe("data:shared"));
    expect(screen.getByTestId("b").textContent).toBe("data:shared");
  });

  it("surfaces BFF error descriptions", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({
        ok: false,
        text: () => Promise.resolve(JSON.stringify({ userMessage: "Not found." })),
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<Probe url="/api/z" id="a" />);
    await waitFor(() => expect(screen.getByTestId("a").textContent).toContain("error:"));
    expect(screen.getByTestId("a").textContent).toContain("Not found.");
  });

  it("invalidateCachedFetch refetches only matching keys with live subscribers", async () => {
    const bodies = new Map<string, string>([
      ["/api/section-a", "a1"],
      ["/api/section-b", "b1"],
    ]);
    const fetchMock = vi.fn((url: string) =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ value: bodies.get(url) }) }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <>
        <Probe url="/api/section-a" id="a" />
        <Probe url="/api/section-b" id="b" />
      </>,
    );
    await waitFor(() => expect(screen.getByTestId("a").textContent).toBe("data:a1"));
    await waitFor(() => expect(screen.getByTestId("b").textContent).toBe("data:b1"));
    expect(fetchMock).toHaveBeenCalledTimes(2);

    bodies.set("/api/section-a", "a2");
    bodies.set("/api/section-b", "b2");
    await act(async () => {
      invalidateCachedFetch("/api/section-a");
    });

    await waitFor(() => expect(screen.getByTestId("a").textContent).toBe("data:a2"));
    // Section B kept its cache — no refetch, stale value intact.
    expect(screen.getByTestId("b").textContent).toBe("data:b1");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("does nothing for a null key (disabled fetch)", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<Probe url={null} id="a" />);
    expect(screen.getByTestId("a").textContent).toBe("data:");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
