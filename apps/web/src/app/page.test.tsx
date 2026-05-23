import { describe, expect, it, vi } from "vitest";

const redirectMock = vi.fn();

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

describe("Home page", () => {
  it("redirects to /engagements", async () => {
    const { default: Home } = await import("./page");
    Home();
    expect(redirectMock).toHaveBeenCalledWith("/engagements");
  });
});
