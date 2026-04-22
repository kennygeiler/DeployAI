"use client";

import { useEffect } from "react";

import { initAxeInDev } from "@/lib/axe";

/**
 * Story 1.6 AC3: client-side bootstrap for @axe-core/react. Renders
 * nothing; side-effect only runs in dev mode. See src/lib/axe.ts for
 * the guard contract and the React-19 compatibility risk (Risks §1).
 */
export function AxeDev(): null {
  useEffect(() => {
    void initAxeInDev();
  }, []);
  return null;
}
