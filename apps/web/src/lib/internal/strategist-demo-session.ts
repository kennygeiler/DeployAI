/**
 * Optional break-glass / external-auditor strip for Epic 8 Story 8.5 (SessionBanner slot).
 * Set `STRATEGIST_DEMO_SESSION_BANNER=1` in the web app environment to verify chrome in dev/CI.
 */
export type StrategistSessionBannerPayload = {
  sessionId: string;
  variant: "break-glass" | "external-auditor";
  /** Epoch ms — 15 min from load when demo is on. */
  expiresAt: number;
};

export function getStrategistSessionBannerForEnv(): StrategistSessionBannerPayload | null {
  if (process.env.STRATEGIST_DEMO_SESSION_BANNER !== "1") {
    return null;
  }
  return {
    sessionId: "demo-bg-ephemeral",
    variant: "break-glass",
    expiresAt: Date.now() + 15 * 60 * 1000,
  };
}
