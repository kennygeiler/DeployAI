/**
 * V1 stub: confirms DeployAI TSR shape + digest echo (no full ASN.1).
 * Go CLI in Epic 12 embeds the real certificate chain; the bytes live under `certs/`.
 */
const STUB_PREFIX = new Uint8Array([
  0x44, 0x45, 0x50, 0x4c, 0x4f, 0x59, 0x41, 0x49, 0x2d, 0x54, 0x53, 0x41, 0x2d, 0x53, 0x54, 0x55,
  0x42, 0x00,
]);

export function verifyTsrStub(
  tsr: Uint8Array,
  expectedDigest: Uint8Array,
): { ok: boolean; error?: string } {
  const prefix = STUB_PREFIX;
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
