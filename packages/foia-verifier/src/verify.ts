/**
 * V1 stub: confirms DeployAI TSR shape + digest echo (no full ASN.1).
 * Go CLI in Epic 12 embeds the real certificate chain; the bytes live under `certs/`.
 */
export function verifyTsrStub(tsr: Uint8Array, expectedDigest: Uint8Array): { ok: boolean; error?: string } {
  const prefix = new TextEncoder().encode("DEPLOYAI-TSA-STUB\0");
  if (tsr.length < prefix.length + expectedDigest.length) {
    return { ok: false, error: "truncated" };
  }
  for (let i = 0; i < prefix.length; i += 1) {
    if (tsr[i] !== prefix[i]) {
      return { ok: false, error: "prefix" };
    }
  }
  for (let j = 0; j < expectedDigest.length; j += 1) {
    if (tsr[prefix.length + j] !== expectedDigest[j]) {
      return { ok: false, error: "digest" };
    }
  }
  return { ok: true };
}
