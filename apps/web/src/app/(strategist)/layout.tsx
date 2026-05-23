import type { ReactNode } from "react";

import { StrategistShell } from "./StrategistShell.client";

export default function StrategistLayout({ children }: { children: ReactNode }) {
  return (
    <StrategistShell>
      <main id="main" tabIndex={-1} className="outline-none">
        {children}
      </main>
    </StrategistShell>
  );
}
