/**
 * Control-plane paste-preview API (internal key). Posts a candidate
 * interaction to `POST /internal/v1/engagements/{id}/extract-preview`,
 * which runs the matrix-extraction agent against an in-memory pseudo
 * event and returns drafts without persisting anything. The web client
 * uses it to render the extractor's output before the user commits.
 */
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type ExtractPreviewPayload = {
  source: string;
  occurred_at: string;
  content: Record<string, unknown>;
  source_ref?: string | null;
};

export type ExtractPreviewDraft = {
  kind: string;
  payload: Record<string, unknown>;
  rationale: string | null;
};

export type ExtractPreviewResponse = {
  drafts: ExtractPreviewDraft[];
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

export async function cpExtractPreview(
  tenantId: string,
  engagementId: string,
  body: ExtractPreviewPayload,
): Promise<ExtractPreviewResponse> {
  const url =
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/extract-preview` +
    `?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp extract-preview ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as ExtractPreviewResponse;
}
