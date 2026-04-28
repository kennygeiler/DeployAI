import { z } from "zod";

/** Story 11.2 — edge agent registers an Ed25519 public key with the control plane. */
export const edgeAgentRegisterRequestSchema = z.object({
  tenant_id: z.string().uuid(),
  device_id: z.string().uuid(),
  /** Standard Base64 (no wrapping) of 32-byte Ed25519 public key. */
  public_key_ed25519_b64: z.string().min(1),
});

export type EdgeAgentRegisterRequest = z.infer<typeof edgeAgentRegisterRequestSchema>;

export const edgeAgentRegisterResponseSchema = z.object({
  edge_agent_id: z.string().uuid(),
  registered_at: z.string().datetime({ offset: true }),
});

export type EdgeAgentRegisterResponse = z.infer<typeof edgeAgentRegisterResponseSchema>;
