import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  filterByRange,
  parseIsoDay,
  paramKey,
  readRange,
  toIsoDay,
  useTemporalFilter,
  writeRange,
} from "@/lib/bff/temporal-filter";

const { routerReplaceMock, pathnameMock, searchParamsRef } = vi.hoisted(() => ({
  routerReplaceMock: vi.fn(),
  pathnameMock: vi.fn(),
  searchParamsRef: { current: new URLSearchParams() as URLSearchParams },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: routerReplaceMock,
    push: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
  usePathname: () => pathnameMock(),
  useSearchParams: () => searchParamsRef.current,
}));

describe("parseIsoDay", () => {
  it("accepts YYYY-MM-DD", () => {
    expect(parseIsoDay("2026-05-25")?.toISOString()).toBe("2026-05-25T00:00:00.000Z");
  });

  it("rejects non-day strings", () => {
    expect(parseIsoDay("2026-05-25T12:00:00Z")).toBeNull();
    expect(parseIsoDay("garbage")).toBeNull();
    expect(parseIsoDay("")).toBeNull();
    expect(parseIsoDay(null)).toBeNull();
    expect(parseIsoDay(undefined)).toBeNull();
  });

  it("rejects calendar-invalid values that JS would otherwise coerce", () => {
    expect(parseIsoDay("2026-13-40")).toBeNull();
  });
});

describe("toIsoDay", () => {
  it("formats a Date as UTC YYYY-MM-DD", () => {
    expect(toIsoDay(new Date("2026-05-25T23:59:00.000Z"))).toBe("2026-05-25");
  });
});

describe("paramKey", () => {
  it("namespaces by section", () => {
    expect(paramKey("insights", "from")).toBe("insights.from");
    expect(paramKey("decisions", "to")).toBe("decisions.to");
  });
});

describe("readRange", () => {
  it("returns nulls when no params", () => {
    const r = readRange(new URLSearchParams(), "insights");
    expect(r).toEqual({ from: null, to: null });
  });

  it("reads section-namespaced params", () => {
    const r = readRange(
      new URLSearchParams("insights.from=2026-05-20&insights.to=2026-05-25"),
      "insights",
    );
    expect(r.from?.toISOString()).toBe("2026-05-20T00:00:00.000Z");
    expect(r.to?.toISOString()).toBe("2026-05-25T00:00:00.000Z");
  });

  it("ignores garbage params silently", () => {
    const r = readRange(
      new URLSearchParams("insights.from=garbage&insights.to=also-garbage"),
      "insights",
    );
    expect(r).toEqual({ from: null, to: null });
  });

  it("auto-swaps when from > to", () => {
    const r = readRange(
      new URLSearchParams("insights.from=2026-05-25&insights.to=2026-05-20"),
      "insights",
    );
    expect(r.from && toIsoDay(r.from)).toBe("2026-05-20");
    expect(r.to && toIsoDay(r.to)).toBe("2026-05-25");
  });

  it("does not cross sections", () => {
    const params = new URLSearchParams("insights.from=2026-05-20&decisions.from=2026-04-01");
    const ins = readRange(params, "insights");
    const dec = readRange(params, "decisions");
    expect(ins.from && toIsoDay(ins.from)).toBe("2026-05-20");
    expect(dec.from && toIsoDay(dec.from)).toBe("2026-04-01");
  });
});

describe("writeRange", () => {
  it("sets both bounds", () => {
    const out = writeRange(new URLSearchParams(), "decisions", {
      from: new Date("2026-05-20T00:00:00Z"),
      to: new Date("2026-05-25T00:00:00Z"),
    });
    expect(out.get("decisions.from")).toBe("2026-05-20");
    expect(out.get("decisions.to")).toBe("2026-05-25");
  });

  it("clears bounds when null", () => {
    const out = writeRange(
      new URLSearchParams("decisions.from=2026-05-20&decisions.to=2026-05-25"),
      "decisions",
      { from: null, to: null },
    );
    expect(out.get("decisions.from")).toBeNull();
    expect(out.get("decisions.to")).toBeNull();
  });

  it("preserves unrelated params and sibling sections", () => {
    const out = writeRange(
      new URLSearchParams("tab=matrix&insights.from=2026-05-20"),
      "decisions",
      { from: new Date("2026-04-01T00:00:00Z"), to: null },
    );
    expect(out.get("tab")).toBe("matrix");
    expect(out.get("insights.from")).toBe("2026-05-20");
    expect(out.get("decisions.from")).toBe("2026-04-01");
  });

  it("auto-swaps from > to on write", () => {
    const out = writeRange(new URLSearchParams(), "risks", {
      from: new Date("2026-05-25T00:00:00Z"),
      to: new Date("2026-05-20T00:00:00Z"),
    });
    expect(out.get("risks.from")).toBe("2026-05-20");
    expect(out.get("risks.to")).toBe("2026-05-25");
  });
});

describe("filterByRange", () => {
  type Item = { ts: string; id: string };
  const items: Item[] = [
    { id: "a", ts: "2026-05-19T12:00:00Z" },
    { id: "b", ts: "2026-05-20T00:00:00Z" },
    { id: "c", ts: "2026-05-22T23:59:59Z" },
    { id: "d", ts: "2026-05-25T00:00:00Z" },
    { id: "e", ts: "2026-05-26T00:00:00Z" },
  ];

  it("returns input unchanged when both bounds null", () => {
    expect(filterByRange(items, (i) => i.ts, { from: null, to: null })).toEqual(items);
  });

  it("includes the entire 'to' day (inclusive)", () => {
    const out = filterByRange(items, (i) => i.ts, {
      from: new Date("2026-05-20T00:00:00Z"),
      to: new Date("2026-05-25T00:00:00Z"),
    });
    expect(out.map((i) => i.id)).toEqual(["b", "c", "d"]);
  });

  it("drops items with unparseable timestamps", () => {
    const out = filterByRange([{ id: "x", ts: "garbage" }], (i) => i.ts, {
      from: new Date("2026-05-20T00:00:00Z"),
      to: null,
    });
    expect(out).toEqual([]);
  });
});

describe("useTemporalFilter", () => {
  beforeEach(() => {
    pathnameMock.mockReturnValue("/engagements/e1");
    searchParamsRef.current = new URLSearchParams();
  });

  afterEach(() => {
    routerReplaceMock.mockReset();
  });

  it("reads the current range from the URL", () => {
    searchParamsRef.current = new URLSearchParams(
      "insights.from=2026-05-20&insights.to=2026-05-25",
    );
    const { result } = renderHook(() => useTemporalFilter("insights"));
    expect(result.current.range.from && toIsoDay(result.current.range.from)).toBe("2026-05-20");
    expect(result.current.range.to && toIsoDay(result.current.range.to)).toBe("2026-05-25");
  });

  it("setRange pushes section-namespaced params to the URL", () => {
    const { result } = renderHook(() => useTemporalFilter("decisions"));
    act(() => {
      result.current.setRange({
        from: new Date("2026-05-20T00:00:00Z"),
        to: new Date("2026-05-25T00:00:00Z"),
      });
    });
    expect(routerReplaceMock).toHaveBeenCalledTimes(1);
    const [target] = routerReplaceMock.mock.calls[0]!;
    expect(target).toContain("decisions.from=2026-05-20");
    expect(target).toContain("decisions.to=2026-05-25");
  });

  it("insights and decisions sections are independent", () => {
    searchParamsRef.current = new URLSearchParams(
      "insights.from=2026-05-20&decisions.from=2026-04-01",
    );
    const insights = renderHook(() => useTemporalFilter("insights"));
    const decisions = renderHook(() => useTemporalFilter("decisions"));

    expect(insights.result.current.range.from && toIsoDay(insights.result.current.range.from)).toBe(
      "2026-05-20",
    );
    expect(
      decisions.result.current.range.from && toIsoDay(decisions.result.current.range.from),
    ).toBe("2026-04-01");

    act(() => {
      insights.result.current.setRange({
        from: new Date("2026-05-22T00:00:00Z"),
        to: null,
      });
    });
    const [target] = routerReplaceMock.mock.calls[0]!;
    expect(target).toContain("insights.from=2026-05-22");
    // The decisions param is preserved on the write.
    expect(target).toContain("decisions.from=2026-04-01");
  });

  it("clears params when both bounds null", () => {
    searchParamsRef.current = new URLSearchParams(
      "insights.from=2026-05-20&insights.to=2026-05-25",
    );
    const { result } = renderHook(() => useTemporalFilter("insights"));
    act(() => {
      result.current.setRange({ from: null, to: null });
    });
    const [target] = routerReplaceMock.mock.calls[0]!;
    expect(target).toBe("/engagements/e1");
  });

  it("treats garbage URL params as 'no filter'", () => {
    searchParamsRef.current = new URLSearchParams("insights.from=garbage&insights.to=2026-13-99");
    const { result } = renderHook(() => useTemporalFilter("insights"));
    expect(result.current.range).toEqual({ from: null, to: null });
  });
});
