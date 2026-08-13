/**
 * Self-serve workspace creation. Renders only when
 * NEXT_PUBLIC_SELF_SERVE_SIGNUP=1 (same gate style as demo mode); otherwise
 * the route 404s so a customer deploy shows no trace of public signup. The
 * control plane enforces its own DEPLOYAI_SELF_SERVE_SIGNUP server-side —
 * this page gate is presentation, not the security boundary.
 */

import { notFound } from "next/navigation";

import { selfServeSignupEnabled } from "@/lib/internal/account-auth";

import { SignupForm } from "./SignupForm.client";

export const metadata = { title: "Create a workspace — DeployAI" };

export default function SignupPage() {
  if (!selfServeSignupEnabled()) {
    notFound();
  }
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem",
      }}
    >
      <div style={{ maxWidth: "24rem", width: "100%", textAlign: "center" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "0.5rem" }}>
          Create your DeployAI workspace
        </h1>
        <p style={{ marginBottom: "1.5rem", opacity: 0.75 }}>
          A workspace is your team&apos;s tenant. You&apos;ll be its first admin.
        </p>
        <SignupForm />
        <p style={{ marginTop: "1.5rem", fontSize: "0.875rem" }}>
          Already have an account?{" "}
          <a href="/login" style={{ textDecoration: "underline", fontWeight: 500 }}>
            Sign in
          </a>
        </p>
      </div>
    </main>
  );
}
