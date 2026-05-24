import type { Metadata } from "next";

import { EmailPasteForm } from "@/components/settings/EmailPasteForm.client";
import { requireCanonicalRead } from "@/lib/internal/strategist-surface";

export const metadata: Metadata = {
  title: "Email paste-import",
  description: "Land IMAP / MBOX pasted emails until OAuth-delivered fetch ships.",
};

export default async function EmailImportPage() {
  await requireCanonicalRead();
  return (
    <div className="max-w-5xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Email paste-import</h1>
        <p className="text-ink-600 mt-1 text-sm">
          Paste raw RFC 5322 messages or an mbox export. Each message lands in the tenant ingest
          queue and is folded into canonical memory in a later step.
        </p>
      </header>
      <EmailPasteForm />
    </div>
  );
}
