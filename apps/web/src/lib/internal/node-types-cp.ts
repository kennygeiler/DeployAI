import { z } from "zod";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type BuiltinNodeType = {
  name: string;
  label: string;
};

export type CustomNodeType = {
  id: string;
  name: string;
  label: string;
  color: string | null;
  description: string | null;
};

export type NodeTypesResponse = {
  builtin: BuiltinNodeType[];
  custom: CustomNodeType[];
};

const NODE_TYPE_NAME_RE = /^[a-z][a-z0-9_]{0,49}$/;
const NODE_TYPE_COLOR_RE = /^#[0-9a-f]{6}$/;

export const zNodeTypeCreate = z.object({
  name: z.string().regex(NODE_TYPE_NAME_RE),
  label: z.string().min(1).max(200),
  color: z.string().regex(NODE_TYPE_COLOR_RE).nullish(),
  description: z.string().max(500).nullish(),
});

export const zNodeTypeUpdate = z.object({
  label: z.string().min(1).max(200).optional(),
  color: z.string().regex(NODE_TYPE_COLOR_RE).nullish(),
  description: z.string().max(500).nullish(),
});

export type NodeTypeCreate = z.infer<typeof zNodeTypeCreate>;
export type NodeTypeUpdate = z.infer<typeof zNodeTypeUpdate>;

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

export async function cpListNodeTypes(tenantId: string): Promise<NodeTypesResponse> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/node-types`;
  const r = await fetch(url, { method: "GET", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp node-types list ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as NodeTypesResponse;
}

export async function cpCreateNodeType(
  tenantId: string,
  body: NodeTypeCreate,
): Promise<CustomNodeType> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/node-types`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp node-types create ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as CustomNodeType;
}

export async function cpUpdateNodeType(
  tenantId: string,
  nodeTypeId: string,
  body: NodeTypeUpdate,
): Promise<CustomNodeType> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/node-types/${encodeURIComponent(nodeTypeId)}`;
  const r = await fetch(url, {
    method: "PUT",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp node-types update ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as CustomNodeType;
}

export async function cpDeleteNodeType(tenantId: string, nodeTypeId: string): Promise<void> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/node-types/${encodeURIComponent(nodeTypeId)}`;
  const r = await fetch(url, { method: "DELETE", headers: cpHeaders(), cache: "no-store" });
  if (!r.ok) {
    throw new Error(`cp node-types delete ${r.status}: ${await r.text()}`);
  }
}
