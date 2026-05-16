import { NextResponse } from "next/server";

import { strategistQueuesShouldRejectMemoryFallback } from "@/lib/internal/strategist-queues-backend";

export function strategistQueueBffCpMisconfiguredResponse(
  tenantId: string | null | undefined,
): NextResponse | null {
  if (!strategistQueuesShouldRejectMemoryFallback(tenantId)) {
    return null;
  }
  return NextResponse.json(
    {
      error: "service_misconfigured",
      code: "cp_env_missing",
      source: "cp_misconfigured",
      userMessage:
        "Strategist queues are not fully configured for this environment. Ask your administrator to verify deployment settings.",
    },
    { status: 503 },
  );
}
