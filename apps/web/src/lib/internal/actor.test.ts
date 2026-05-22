import { afterEach, describe, expect, it, vi } from "vitest";

const { headersMock } = vi.hoisted(() => ({ headersMock: vi.fn() }));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: vi.fn(async () => ({ get: () => undefined })),
}));

import { getActorFromHeaders } from "./actor";

describe("getActorFromHeaders — x-deployai-role", () => {
  afterEach(() => {
    headersMock.mockReset();
  });

  it("resolves the fde team role from the header", async () => {
    headersMock.mockResolvedValue(
      new Headers({ "x-deployai-role": "fde", "x-deployai-tenant": "t1" }),
    );
    expect(await getActorFromHeaders()).toEqual({ role: "fde", tenantId: "t1" });
  });

  it("resolves the biz_dev team role from the header", async () => {
    headersMock.mockResolvedValue(
      new Headers({ "x-deployai-role": "biz_dev", "x-deployai-tenant": "t1" }),
    );
    expect(await getActorFromHeaders()).toEqual({ role: "biz_dev", tenantId: "t1" });
  });
});
