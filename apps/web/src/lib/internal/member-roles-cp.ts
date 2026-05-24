import { z } from "zod";

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

export type MemberRolesResponse = {
  builtin: BuiltinMemberRole[];
  custom: CustomMemberRole[];
};

export const zMemberRoleCreate = z.object({
  name: z.string().min(1).max(50),
  label: z.string().min(1).max(200),
  description: z.string().max(500).nullish(),
});

export const zMemberRoleUpdate = z.object({
  label: z.string().min(1).max(200).optional(),
  description: z.string().max(500).nullish(),
});

export type MemberRoleCreate = z.infer<typeof zMemberRoleCreate>;
export type MemberRoleUpdate = z.infer<typeof zMemberRoleUpdate>;

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

export async function cpListMemberRoles(tenantId: string): Promise<MemberRolesResponse> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/member-roles`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp member-roles list ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as MemberRolesResponse;
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
