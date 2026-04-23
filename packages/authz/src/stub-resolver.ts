import { isAllowedByMatrix } from "./matrix.js";
import type { AuthActor, AuthzResolver, Decision, Resource, Action } from "./types.js";

/**
 * In-memory v1: checks role alone (tenant-scoped rules land Story 2.x).
 * Server components pass `actor` derived from the session.
 */
export const stubAuthzResolver: AuthzResolver = (actor, action, resource) => {
  void resource;
  if (!isAllowedByMatrix(actor.role, action)) {
    return { allow: false, code: "forbidden", reason: "Role cannot perform this action in V1" };
  }
  return { allow: true };
};

export function decideSync(actor: AuthActor, action: Action, resource: Resource): Decision {
  return stubAuthzResolver(actor, action, resource) as Decision;
}
