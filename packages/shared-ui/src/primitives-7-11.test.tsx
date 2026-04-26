import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LoadingFromMemory } from "./LoadingFromMemory";
import { MemorySyncingGlyph } from "./MemorySyncingGlyph";

describe("7.11 primitives", () => {
  it("LoadingFromMemory exposes status", () => {
    render(<LoadingFromMemory label="Recalling from graph…" />);
    expect(screen.getByRole("status")).toHaveTextContent(/Recalling from graph/);
  });

  it("MemorySyncingGlyph renders state", () => {
    render(<MemorySyncingGlyph state="stale" label="Memory stale — refresh" />);
    expect(screen.getByText(/Memory stale/)).toBeInTheDocument();
  });
});
