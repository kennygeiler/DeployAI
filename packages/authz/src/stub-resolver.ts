import { canAccess } from "./can-access.js";
import type { AuthActor, AuthzResolver, Decision, Resource, Action } from "./types.js";

/**
 * Async-shaped resolver delegating to {@link canAccess} (keeps type for future OpenFGA).
 */
export const authzResolver: { canAccess: AuthzResolver } = {
  canAccess: (actor, action, resource) => canAccess(actor, action, resource),
};

export const stubAuthzResolver: AuthzResolver = (actor, action, resource) => {
  return canAccess(actor, action, resource);
};

/** Sync helper used by RSC, middleware, and legacy call sites. */
export function decideSync(
  actor: AuthActor,
  action: Action,
  resource: Resource,
  options?: { traceId?: string; skipAudit?: boolean },
): Decision {
  return canAccess(actor, action, resource, options);
}
