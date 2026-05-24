import { z } from "zod";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export const EMAIL_PASTE_SOURCES = ["imap_paste", "mbox_paste", "manual_paste"] as const;
export type EmailPasteSource = (typeof EMAIL_PASTE_SOURCES)[number];

export const zEmailIngestEvent = z.object({
  id: z.string(),
  tenant_id: z.string(),
  engagement_id: z.string().nullable(),
  source: z.string(),
  external_message_id: z.string().nullable(),
  raw_payload: z.string(),
  parsed_subject: z.string().nullable(),
  parsed_from: z.string().nullable(),
  parsed_to: z.array(z.string()),
  parsed_date: z.string().nullable(),
  received_at: z.string(),
  processed_at: z.string().nullable(),
  error: z.string().nullable(),
});

export type EmailIngestEvent = z.infer<typeof zEmailIngestEvent>;

const zEmailIngestEventList = z.array(zEmailIngestEvent);

export const zEmailPasteBody = z.object({
  source: z.enum(EMAIL_PASTE_SOURCES),
  raw: z.string().min(1),
  engagement_id: z.string().optional(),
});

export type EmailPasteBody = z.infer<typeof zEmailPasteBody>;

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

export async function cpIngestEmailPaste(
  tenantId: string,
  body: EmailPasteBody,
): Promise<EmailIngestEvent[]> {
  const qs = new URLSearchParams({ tenant_id: tenantId });
  const url = `${cpBase()}/internal/v1/emails/ingest?${qs.toString()}`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp emails ingest ${r.status}: ${await r.text()}`);
  }
  const raw: unknown = await r.json();
  return zEmailIngestEventList.parse(raw);
}
