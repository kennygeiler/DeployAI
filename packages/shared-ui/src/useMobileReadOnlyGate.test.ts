import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useMobileReadOnlyGate } from "./useMobileReadOnlyGate";

describe("useMobileReadOnlyGate", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: true,
        media: "",
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reflects narrow viewports as read-only", async () => {
    const { result } = renderHook(() => useMobileReadOnlyGate(768));
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current).toBe(true);
  });
});
