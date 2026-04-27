import type { DigestTopItem } from "@/lib/epic8/mock-digest";
import { MORNING_DIGEST_TOP } from "@/lib/epic8/mock-digest";

/**
 * Optional remote source for the Morning Digest list (JSON array of `DigestTopItem` rows).
 * When unset, uses mock data from `mock-digest`.
 */
export async function loadMorningDigestTopItems(): Promise<readonly DigestTopItem[]> {
  const u = process.env.STRATEGIST_DIGEST_SOURCE_URL?.trim();
  if (!u) {
    return MORNING_DIGEST_TOP;
  }
  try {
    const r = await fetch(u, { cache: "no-store" });
    if (!r.ok) {
      return MORNING_DIGEST_TOP;
    }
    const j = (await r.json()) as unknown;
    if (Array.isArray(j) && j.length > 0) {
      return j as DigestTopItem[];
    }
  } catch {
    /* fall through */
  }
  return MORNING_DIGEST_TOP;
}
