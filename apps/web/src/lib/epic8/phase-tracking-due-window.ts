/**
 * Due-window filtering for phase-tracking rows (no mock row generation).
 */
import { getStrategistLocalDateForServer } from "@/lib/internal/strategist-local-date";
import type { DueDateWindow } from "@/lib/strategist-data/strategist-surface-types";

const ISO_LOCAL_DAY = /^\d{4}-\d{2}-\d{2}$/;

export function resolveStrategistLocalDayForWindow(today: string | undefined): string {
  if (today !== undefined && today !== "" && ISO_LOCAL_DAY.test(today)) {
    return today;
  }
  return getStrategistLocalDateForServer();
}

function addDaysToIsoDate(isoDate: string, days: number): string {
  const t = new Date(`${isoDate}T12:00:00.000Z`);
  t.setUTCDate(t.getUTCDate() + days);
  return t.toISOString().slice(0, 10);
}

/** YYYY-MM-DD due cell vs window chips (string comparison is valid for ISO dates). */
export function actionQueueRowMatchesDueWindow(
  due: string,
  window: DueDateWindow,
  today?: string,
): boolean {
  const day = resolveStrategistLocalDayForWindow(today);
  if (window === "all") {
    return true;
  }
  if (window === "today") {
    return due === day;
  }
  if (window === "overdue") {
    return due < day;
  }
  const end = addDaysToIsoDate(day, 6);
  return due >= day && due <= end;
}
