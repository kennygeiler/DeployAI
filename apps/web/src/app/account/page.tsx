/**
 * Account management (authed — the middleware gates `/account` like the
 * other strategist surfaces and bounces anonymous browsers to /login).
 * All data comes from `/api/auth/me` client-side; the page itself renders
 * no session material.
 */

import Link from "next/link";

import { AccountPanel } from "./AccountPanel.client";

export const metadata = { title: "Account — DeployAI" };

export default function AccountPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8 md:px-6">
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Account</h1>
        <Link href="/engagements" className="text-sm underline">
          Back to app
        </Link>
      </div>
      <AccountPanel />
    </main>
  );
}
