import type { Action, AuthzAuditEvent, AuthActor, Decision, Resource } from "./types.js";

function resourceKind(r: Resource): string {
  if (r.kind === "tenant") {
    return `tenant:${r.id}`;
  }
  return r.kind;
}

function resourceTenantId(r: Resource): string | null {
  if (r.kind === "tenant") {
    return r.id;
  }
  return null;
}

function isBrowserRuntime(): boolean {
  return typeof (globalThis as { window?: unknown }).window !== "undefined";
}

/**
 * Emits a single JSON line for NFR59 when running on the server (Node / Edge).
 * No-ops in the browser to keep client bundles free of log noise.
 */
export function emitAuthzAudit(
  actor: AuthActor,
  action: Action,
  resource: Resource,
  d: Decision,
  traceId?: string,
): void {
  if (isBrowserRuntime()) {
    return;
  }
  const base: AuthzAuditEvent = {
    event: "authz_decision",
    allow: d.allow,
    actor_role: actor.role,
    action,
    resource_kind: resourceKind(resource),
    tenant_id: actor.tenantId ?? null,
    resource_tenant_id: resourceTenantId(resource),
    code: d.allow ? "ok" : d.code,
  };
  if (!d.allow) {
    base.reason = d.reason;
  }
  if (traceId !== undefined) {
    base.trace_id = traceId;
  }
  console.info(JSON.stringify(base));
}
