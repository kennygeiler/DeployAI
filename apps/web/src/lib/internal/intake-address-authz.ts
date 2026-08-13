/**
 * Wave 5 IN2 — who may rotate an engagement's intake address.
 *
 * The authz matrix has no action that maps to exactly {customer_admin,
 * platform_admin} (`internal:proxy` includes strategists; `scim:manage`
 * is user-provisioning semantics), so the BFF gates regenerate on the
 * role directly. If a real "engagement admin" action lands in
 * `@deployai/authz`, replace this with `decideSync` against it.
 */

const INTAKE_REGENERATE_ROLES = new Set<string>(["customer_admin", "platform_admin"]);

export function canRegenerateIntakeAddress(role: string): boolean {
  return INTAKE_REGENERATE_ROLES.has(role);
}
