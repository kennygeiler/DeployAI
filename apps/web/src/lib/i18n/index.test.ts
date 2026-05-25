import { describe, expect, it, vi } from "vitest";

import { DEFAULT_LOCALE, t } from "./index";

describe("i18n t()", () => {
  it("returns the en-US string for a known key", () => {
    expect(t("settings.heading")).toBe("Settings");
  });

  it("returns the key itself when the key is missing", () => {
    const missing = "nonexistent.key.value";
    expect(t(missing)).toBe(missing);
  });

  it("warns once per missing key in dev", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubEnv("NODE_ENV", "development");
    t("once.warn.test");
    t("once.warn.test");
    vi.unstubAllEnvs();
    expect(warn).toHaveBeenCalledTimes(1);
    warn.mockRestore();
  });

  it("DEFAULT_LOCALE is en-US", () => {
    expect(DEFAULT_LOCALE).toBe("en-US");
  });
});
