import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IntakeAddressBlock } from "./IntakeAddress.client";

function jsonResponse(body: unknown, ok = true, status = ok ? 200 : 500) {
  return {
    ok,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  };
}

const address = {
  local_part: "acme-rollout-abc123def456ghi789jkl0",
  email: "acme-rollout-abc123def456ghi789jkl0@intake.example.com",
  created_at: "2026-08-13T00:00:00Z",
  can_regenerate: false,
};

describe("IntakeAddressBlock", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows the address with the explainer, and copies it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse(address))),
    );
    const user = userEvent.setup();
    // After userEvent.setup() so this stub wins over userEvent's own.
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    render(<IntakeAddressBlock engagementId="e1" />);

    expect(await screen.findByText(address.email)).toBeInTheDocument();
    expect(screen.getByText(/CC or forward deal email here/)).toBeInTheDocument();
    // Non-admin: no Regenerate offered.
    expect(screen.queryByRole("button", { name: "Regenerate" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith(address.email);
  });

  it("falls back to the local part when the CP has no intake domain", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse({ ...address, email: null }))),
    );
    render(<IntakeAddressBlock engagementId="e1" />);
    expect(await screen.findByText(address.local_part)).toBeInTheDocument();
  });

  it("renders nothing when the address endpoint errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(jsonResponse({ error: "nope" }, false, 404))),
    );
    const { container } = render(<IntakeAddressBlock engagementId="e1" />);
    // Give the mount fetch a tick to settle, then assert the block stayed out.
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("regenerates after confirm for admins, and shows the new address", async () => {
    const regenerated = {
      ...address,
      local_part: "acme-rollout-newtoken12345678901234",
      email: "acme-rollout-newtoken12345678901234@intake.example.com",
      can_regenerate: true,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: { method?: string }) => {
        if (init?.method === "POST" && url.includes("/regenerate")) {
          return Promise.resolve(jsonResponse(regenerated, true, 201));
        }
        return Promise.resolve(jsonResponse({ ...address, can_regenerate: true }));
      }),
    );
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    const user = userEvent.setup();
    render(<IntakeAddressBlock engagementId="e1" />);

    await user.click(await screen.findByRole("button", { name: "Regenerate" }));
    expect(confirmSpy).toHaveBeenCalledOnce();
    expect(await screen.findByText(regenerated.email)).toBeInTheDocument();
  });

  it("does not regenerate when the confirm is declined", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(jsonResponse({ ...address, can_regenerate: true })),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(false);

    const user = userEvent.setup();
    render(<IntakeAddressBlock engagementId="e1" />);

    await user.click(await screen.findByRole("button", { name: "Regenerate" }));
    // Only the mount-time GET — no POST fired.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText(address.email)).toBeInTheDocument();
  });
});
