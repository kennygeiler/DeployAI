import type { V1Role } from "@deployai/authz";

/**
 * Local-dev role/tenant header injection policy (Wave 1 ticket A2).
 *
 * Injection is strictly opt-IN: it only activates when
 * `DEPLOYAI_LOCAL_DEV_ROLE_INJECT=1` is set explicitly — running `next dev` is
 * no longer sufficient on its own. On a production build
 * (`NODE_ENV === "production"`, e.g. the local compose stack) a second override,
 * `DEPLOYAI_DEV_ROLE_INJECT_ALLOW_PRODUCTION=1`, is additionally required so the
 * flag cannot quietly grant a role to every request on a hosted deploy.
 * `DEPLOYAI_DISABLE_DEV_STRATEGIST=1` remains an unconditional kill switch.
 *
 * NEVER set these flags in a hosted/pilot deploy — SSO/proxy or the CP-issued
 * access JWT supplies the real `x-deployai-role` / `x-deployai-tenant` there.
 */
export function devRoleInjectEnabled(): boolean {
  if (process.env.DEPLOYAI_DISABLE_DEV_STRATEGIST === "1") {
    return false;
  }
  if (process.env.DEPLOYAI_LOCAL_DEV_ROLE_INJECT !== "1") {
    return false;
  }
  if (
    process.env.NODE_ENV === "production" &&
    process.env.DEPLOYAI_DEV_ROLE_INJECT_ALLOW_PRODUCTION !== "1"
  ) {
    return false;
  }
  return true;
}

const DEV_ROLE_ALLOWED: readonly V1Role[] = [
  "platform_admin",
  "customer_admin",
  "deployment_strategist",
  "fde",
  "biz_dev",
  "successor_strategist",
  "customer_records_officer",
  "external_auditor",
];

/** Role injected when dev injection is active (`DEPLOYAI_DEV_STRATEGIST_ROLE` override). */
export function devInjectedRole(): V1Role {
  const raw = process.env.DEPLOYAI_DEV_STRATEGIST_ROLE?.trim();
  if (raw && (DEV_ROLE_ALLOWED as string[]).includes(raw)) {
    return raw as V1Role;
  }
  return "deployment_strategist";
}

/** Tenant injected when dev injection is active. Defaults to the seed_app.py tenant. */
export function devInjectedTenantId(): string {
  return process.env.DEPLOYAI_DEV_TENANT_ID?.trim() || "11111111-1111-1111-1111-111111111111";
}
