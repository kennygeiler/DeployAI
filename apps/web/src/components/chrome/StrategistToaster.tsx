"use client";

import { Toaster } from "sonner";

/** Strategist surfaces (Epic 9.4 carryover, etc.) — avoids `next-themes` coupling in root layout. */
export function StrategistToaster() {
  return <Toaster richColors position="top-right" closeButton />;
}
