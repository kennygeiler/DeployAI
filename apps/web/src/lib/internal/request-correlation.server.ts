import { headers } from "next/headers";

import { pickCorrelationIdFromIncoming } from "./correlation-id";

export async function getInboundCorrelationId(): Promise<string | undefined> {
  const h = await headers();
  return pickCorrelationIdFromIncoming(h);
}

export { resolveStrategistOutboundCorrelationId } from "./correlation-id";
