import type { Metadata } from "next";

import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

import { OverviewDeck } from "./OverviewDeck.client";

export const metadata: Metadata = {
  title: "Product overview",
  description:
    "A slide-deck walkthrough of DeployAI's surfaces — portfolio, the Brief, the capture-review loop, Agent Kenny, citations, and the graph lens — with a mini-tutorial per surface.",
};

/**
 * /overview — slide-deck product walkthrough. Real screenshots of the
 * seeded BlueState engagements, one surface per slide, each with a short
 * "how to use it" tutorial. Doubles as the first-run orientation page.
 */
export default async function OverviewPage() {
  await requireCanonicalRead();
  return <OverviewDeck />;
}
