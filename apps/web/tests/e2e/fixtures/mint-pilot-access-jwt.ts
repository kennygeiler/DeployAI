import * as fs from "node:fs";
import * as path from "node:path";

import * as jose from "jose";

const fixtureDir = path.join(process.cwd(), "tests/e2e/fixtures");

let cachedKey: CryptoKey | null = null;

async function fixturePrivateKey(): Promise<CryptoKey> {
  if (cachedKey) {
    return cachedKey;
  }
  const pem = fs.readFileSync(path.join(fixtureDir, "pilot-access-e2e-private.pem"), "utf8");
  cachedKey = await jose.importPKCS8(pem, "RS256");
  return cachedKey;
}

/** CP-shaped access token for Story 15.1 E2E (issuer/audience match defaults). */
export async function mintPilotAccessJwt(params: {
  sub: string;
  tid: string;
  roles: string[];
}): Promise<string> {
  const key = await fixturePrivateKey();
  const now = Math.floor(Date.now() / 1000);
  return new jose.SignJWT({
    sub: params.sub,
    tid: params.tid,
    roles: params.roles,
    token_use: "access",
  })
    .setProtectedHeader({ alg: "RS256" })
    .setIssuer("deployai-control-plane")
    .setAudience("deployai")
    .setIssuedAt(now)
    .setExpirationTime(now + 15 * 60)
    .sign(key);
}
