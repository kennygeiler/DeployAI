import { redirect } from "next/navigation";

/**
 * Root → the engagements portfolio. The MVP loop lives entirely on
 * `/engagements` (portfolio + cross-engagement insights) and
 * `/engagements/[id]` (per-engagement matrix + insights). The pre-pivot
 * BMAD preview routes (digest, phase-tracking, evening) are being
 * retired — see `docs/product/deployai-source-of-truth-spec.md` §16.
 */
export default function Home() {
  redirect("/engagements");
}
