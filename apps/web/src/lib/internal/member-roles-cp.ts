import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type BuiltinMemberRole = {
  name: string;
  label: string;
};

export type CustomMemberRole = {
  id: string;
  name: string;
  label: string;
  description: string | null;
};

export type MemberRolesRead = {
  builtin: BuiltinMemberRole[];
  custom: CustomMemberRole[];
};

export type MemberRoleCreate = {
  name: string;
  label: string;
  description?: string | null;
};

export type MemberRoleUpdate = {
  label?: string;
  description?: string | null;
};

function cpHeaders(): Record<string, string> {
  const key = getControlPlaneInternalKey();
  if (!key) {
    throw new Error("DEPLOYAI_INTERNAL_API_KEY not set");
  }
  return { "X-DeployAI-Internal-Key": key };
}

function cpBase(): string {
  const base = getControlPlaneBaseUrl()?.replace(/\/$/, "");
  if (!base) {
    throw new Error("DEPLOYAI_CONTROL_PLANE_URL not set");
  }
  return base;
}

export async function cpListMemberRoles(tenantId: string): Promise<MemberRolesRead> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/member-roles`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp member-roles list ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as MemberRolesRead;
}

export async function cpCreateMemberRole(
  tenantId: string,
  body: MemberRoleCreate,
): Promise<CustomMemberRole> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/member-roles`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp member-roles create ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as CustomMemberRole;
}

export async function cpUpdateMemberRole(
  tenantId: string,
  roleId: string,
  body: MemberRoleUpdate,
): Promise<CustomMemberRole> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/member-roles/${encodeURIComponent(roleId)}`;
  const r = await fetch(url, {
    method: "PUT",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp member-roles update ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as CustomMemberRole;
}

export async function cpDeleteMemberRole(tenantId: string, roleId: string): Promise<void> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/member-roles/${encodeURIComponent(roleId)}`;
  const r = await fetch(url, { method: "DELETE", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp member-roles delete ${r.status}: ${await r.text()}`);
  }
}
