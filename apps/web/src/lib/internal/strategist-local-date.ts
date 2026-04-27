/**
 * Strategist-local calendar date (YYYY-MM-DD) for mock surfaces and due-window chips.
 *
 * - `STRATEGIST_DEMO_TODAY=YYYY-MM-DD` — fixed “today” for tests and deterministic e2e (no prod use).
 * - `STRATEGIST_LOCAL_TZ` — IANA zone (default `UTC`) for the live clock.
 */
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function getStrategistLocalDateForServer(): string {
  const demo = process.env.STRATEGIST_DEMO_TODAY?.trim();
  if (demo && ISO_DATE.test(demo)) {
    return demo;
  }
  const zone = process.env.STRATEGIST_LOCAL_TZ?.trim() || "UTC";
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}
