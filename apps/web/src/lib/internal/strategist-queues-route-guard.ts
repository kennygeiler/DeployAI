import { NextResponse } from "next/server";

import { strategistQueuesCpMisconfiguredForTenant } from "@/lib/internal/strategist-queues-backend";

export function strategistQueueBffCpMisconfiguredResponse(
  tenantId: string | null | undefined,
): NextResponse | null {
  if (!strategistQueuesCpMisconfiguredForTenant(tenantId)) {
    return null;
  }
  return NextResponse.json(
    {
      error: "service_misconfigured",
      code: "cp_env_missing",
      source: "cp_misconfigured",
      userMessage:
        "Strategist queues require the control plane. Set DEPLOYAI_CONTROL_PLANE_URL and DEPLOYAI_INTERNAL_API_KEY.",
    },
    { status: 503 },
  );
}
