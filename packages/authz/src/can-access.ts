import { isAllowedByMatrix } from "./matrix.js";
import { emitAuthzAudit } from "./audit.js";
import type { Action, AuthActor, Decision, Resource } from "./types.js";

/**
 * True when a non–platform admin acts on a tenant other than their own.
 */
function crossTenantBlocked(actor: AuthActor, resource: Resource): boolean {
  if (actor.role === "platform_admin") {
    return false;
  }
  if (resource.kind === "tenant") {
    if (!actor.tenantId) {
      return true;
    }
    if (actor.tenantId !== resource.id) {
      return true;
    }
  }
  return false;
}

/**
 * Primary authorization entry (Epic 2.1). Synchronous; OpenFGA adapter can wrap later.
 * Emits structured audit on server runtimes.
 */
export function canAccess(
  actor: AuthActor,
  action: Action,
  resource: Resource,
  options?: { traceId?: string; skipAudit?: boolean },
): Decision {
  let d: Decision;
  if (crossTenantBlocked(actor, resource)) {
    d = {
      allow: false,
      code: "forbidden",
      reason: "Cross-tenant access is not allowed for this role",
    };
  } else if (!isAllowedByMatrix(actor.role, action)) {
    d = {
      allow: false,
      code: "forbidden",
      reason: "Role cannot perform this action in the V1 matrix",
    };
  } else {
    d = { allow: true, code: "ok" };
  }
  if (!options?.skipAudit) {
    emitAuthzAudit(actor, action, resource, d, options?.traceId);
  }
  return d;
}
