import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard.client";
import { cpListEngagements } from "@/lib/internal/engagements-cp";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Set up DeployAI",
  description: "First-run wizard: LLM provider, first engagement, first team member.",
};

/**
 * Sprint 1 inc 2 — first-run onboarding wizard.
 *
 * Lives at `/onboarding`. The /engagements page redirects empty
 * tenants here; this page mirrors the inverse — once at least one
 * engagement exists, bounce the user back to /engagements so the
 * wizard can't be re-opened by typing the URL.
 */
export default async function OnboardingPage() {
  const actor = await requireCanonicalRead();
  const tid = actor.tenantId?.trim();
  if (tid) {
    let isPopulated = false;
    try {
      const engagements = await cpListEngagements(tid);
      isPopulated = engagements.length > 0;
    } catch {
      // CP unreachable — show the wizard anyway. The wizard's own submit
      // will surface the same error to the user.
    }
    if (isPopulated) {
      // `redirect()` throws a Next-internal NEXT_REDIRECT signal — keep it
      // outside the try so the catch above doesn't swallow it.
      redirect("/engagements");
    }
  }
  return <OnboardingWizard />;
}
