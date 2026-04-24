export type { V1Role } from "./roles.js";
export { isAllowedByMatrix } from "./matrix.js";
export { authzResolver, decideSync, stubAuthzResolver } from "./stub-resolver.js";
export { canAccess } from "./can-access.js";
export { emitAuthzAudit } from "./audit.js";
export type {
  Action,
  AuthActor,
  AuthzAuditEvent,
  AuthzResolver,
  Decision,
  Resource,
} from "./types.js";
