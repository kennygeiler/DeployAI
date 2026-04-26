"use client";

import * as React from "react";

import { MOBILE_READ_ONLY_PX } from "./breakpoints";

/**
 * `true` when viewport is below the break-glass “mobile read-only” width (UX-DR38).
 * Use to gate **write** surfaces (Override, In-Meeting actions, etc.) on small viewports.
 *
 * @param breakpointPx — default matches Tailwind `md:` (`MOBILE_READ_ONLY_PX`, 768).
 */
export function useMobileReadOnlyGate(breakpointPx: number = MOBILE_READ_ONLY_PX): boolean {
  const [readOnly, setReadOnly] = React.useState(false);

  React.useEffect(() => {
    const max = Math.max(0, breakpointPx - 1);
    const q = window.matchMedia(`(max-width: ${max}px)`);
    const sync = () => {
      setReadOnly(q.matches);
    };
    sync();
    q.addEventListener("change", sync);
    return () => {
      q.removeEventListener("change", sync);
    };
  }, [breakpointPx]);

  return readOnly;
}
