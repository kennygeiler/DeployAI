import { isAllowedByMatrix } from "./matrix.js";
import { emitAuthzAudit, resourceTenantId } from "./audit.js";
import type { Action, AuthActor, Decision, Resource } from "./types.js";

/**
 * Resource kinds that are always tenant-owned. Calls for these kinds must carry
 * `tenantId` or the tenant comparison silently never runs (the Wave 1 audit
 * finding behind ticket A5).
 */
const TENANT_SCOPED_KINDS: ReadonlySet<Resource["kind"]> = new Set([
  "canonical_memory",
  "override",
  "foia_export",
]);

function isProductionRuntime(): boolean {
  return typeof process !== "undefined" && process.env?.NODE_ENV === "production";
}

/**
 * True when a non–platform admin acts on a tenant other than their own.
 * Applies to EVERY resource kind: whenever both the actor tenant and the
 * resource tenant are present and differ, access is blocked. `kind: "tenant"`
 * additionally keeps its stricter legacy rule: an actor without a tenant may
 * not touch a tenant resource at all.
 */
function crossTenantBlocked(actor: AuthActor, resource: Resource): boolean {
  if (actor.role === "platform_admin") {
    return false;
  }
  const rtid = resourceTenantId(resource);
  if (resource.kind === "tenant" && rtid !== null && !actor.tenantId) {
    return true;
  }
  if (rtid !== null && actor.tenantId && actor.tenantId !== rtid) {
    return true;
  }
  return false;
}

/**
 * Missing `tenantId` on a tenant-scoped kind is a caller bug, not a legitimate
 * request shape. Policy (ticket A5): fail loud in dev/test (throw, so the broken
 * call site is found immediately) and fail closed in production (deny — never
 * allow a tenant-scoped resource to skip the tenant comparison).
 */
function tenantScopePolicyViolation(resource: Resource): boolean {
  return TENANT_SCOPED_KINDS.has(resource.kind) && resourceTenantId(resource) === null;
}

/**
 * Primary authorization entry (Epic 2.1). Synchronous; OpenFGA adapter can wrap later.
 * Emits structured audit on server runtimes.
 *
 * @throws Error outside production when a tenant-scoped resource
 *   (canonical_memory / override / foia_export) is passed without `tenantId`.
 */
export function canAccess(
  actor: AuthActor,
  action: Action,
  resource: Resource,
  options?: { traceId?: string; skipAudit?: boolean },
): Decision {
  let d: Decision;
  if (tenantScopePolicyViolation(resource)) {
    if (!isProductionRuntime()) {
      throw new Error(
        `authz policy error: resource kind "${resource.kind}" is tenant-scoped but no tenantId was provided. ` +
          "Pass the tenant the request is about (e.g. { kind, tenantId }). In production this call is denied.",
      );
    }
    d = {
      allow: false,
      code: "forbidden",
      reason: "Tenant-scoped resource is missing tenantId (denied fail-closed)",
    };
  } else if (crossTenantBlocked(actor, resource)) {
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
