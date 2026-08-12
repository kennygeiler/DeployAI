import type { ReactNode } from "react";

import { TourProvider } from "@/components/tour/TourProvider.client";

import { StrategistShell } from "./StrategistShell.client";

export default function StrategistLayout({ children }: { children: ReactNode }) {
  return (
    <StrategistShell>
      <main id="main" tabIndex={-1} className="outline-none">
        {children}
      </main>
      {/* K6 — guided demo tour; renders nothing unless demo_tour=1. Lives in
          the layout so the tour survives client-side navigation. */}
      <TourProvider />
    </StrategistShell>
  );
}
