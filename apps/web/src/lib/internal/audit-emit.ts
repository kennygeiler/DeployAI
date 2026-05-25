import { cpEmitAuditEvent } from "@/lib/internal/audit-cp";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function emitTenantAuditEventBackground(
  tenantId: string,
  actorId: string | null,
  category: string,
  summary: string,
  detail: Record<string, unknown>,
  refId?: string,
): void {
  if (!actorId || !UUID_RE.test(actorId)) return;
  setTimeout(() => {
    void cpEmitAuditEvent(tenantId, {
      actor_id: actorId,
      category,
      summary,
      detail,
      ref_id: refId ?? null,
    }).catch((e) => {
      console.error("[audit-emit] failed", e);
    });
  }, 0);
}
