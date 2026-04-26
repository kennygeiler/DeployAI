"use client";

import * as React from "react";

/**
 * `true` when viewport is below the break-glass “mobile read-only” width (UX-DR38).
 * Use to gate **write** surfaces (Override, In-Meeting actions, etc.) on small viewports.
 *
 * @param breakpointPx — default `768` (matches Tailwind `md:`).
 */
export function useMobileReadOnlyGate(breakpointPx: number = 768): boolean {
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
