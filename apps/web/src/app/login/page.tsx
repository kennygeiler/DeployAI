/**
 * Sign-in page (ticket A1; self-serve accounts). Native email/password is the
 * primary form; OIDC SSO stays the enterprise option (shown only when the
 * OIDC envs are configured), and the Wave 4S design-system "View live demo"
 * button (guest demo access) renders when NEXT_PUBLIC_DEMO_MODE=1. A link to
 * /signup appears only when NEXT_PUBLIC_SELF_SERVE_SIGNUP=1.
 */

import { Button } from "@/components/ui/button";

import { selfServeSignupEnabled } from "@/lib/internal/account-auth";
import { oidcWebLoginConfigured } from "@/lib/internal/oidc-web-flow";

import { PasswordLoginForm } from "./PasswordLoginForm.client";
import { TokenForm } from "./TokenForm.client";

export const metadata = { title: "Sign in — DeployAI" };

// Bootstrap-token login is an operator escape hatch for hosted deploys that
// don't have an OIDC issuer yet; hidden unless explicitly enabled.
const bootstrapLoginEnabled = () => process.env.NEXT_PUBLIC_BOOTSTRAP_TOKEN_LOGIN === "1";

// Public guest demo (Wave 4S): shows the "View live demo" button, which hits
// /api/auth/demo (server-side mint of a read-only demo_guest session on the
// disposable demo tenant). Also requires the CP-side demo envs — see
// docs/ops/cloud-deploy.md §7.1.
const demoModeEnabled = () => process.env.NEXT_PUBLIC_DEMO_MODE === "1";

const ERROR_MESSAGES: Record<string, string> = {
  issuer_unreachable: "Could not reach the identity provider. Please try again in a moment.",
  control_plane_unreachable: "Could not reach the DeployAI backend. Please try again in a moment.",
  idp_error: "The identity provider reported an error. Please try signing in again.",
  sso_failed: "Sign-in failed. Please try again.",
  demo_unavailable: "The live demo is unavailable right now. Please try again in a moment.",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; next?: string }>;
}) {
  const { error, next } = await searchParams;
  const message = error ? (ERROR_MESSAGES[error] ?? ERROR_MESSAGES.sso_failed) : null;
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
        <h1 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "0.5rem" }}>DeployAI</h1>
        <p style={{ marginBottom: "1.5rem", opacity: 0.75 }}>Sign in to continue.</p>
        {message ? (
          <p
            role="alert"
            style={{
              marginBottom: "1.5rem",
              padding: "0.75rem 1rem",
              borderRadius: "0.5rem",
              border: "1px solid #dc2626",
              color: "#dc2626",
            }}
          >
            {message}
          </p>
        ) : null}
        <PasswordLoginForm next={next ?? "/engagements"} />
        {selfServeSignupEnabled() ? (
          <p style={{ marginBottom: "1.5rem", fontSize: "0.875rem" }}>
            New here?{" "}
            <a href="/signup" style={{ textDecoration: "underline", fontWeight: 500 }}>
              Create a workspace
            </a>
          </p>
        ) : null}
        {demoModeEnabled() ? (
          <div style={{ marginBottom: "1.5rem" }}>
            <Button asChild size="lg">
              <a href="/api/auth/demo">View live demo</a>
            </Button>
            <p style={{ marginTop: "0.5rem", fontSize: "0.875rem", opacity: 0.65 }}>
              Read-only guest on a demo workspace — no sign-up needed. A guided tour starts
              automatically (sessions last about an hour).
            </p>
          </div>
        ) : null}
        {oidcWebLoginConfigured() ? (
          <a
            href="/api/auth/login"
            style={{
              display: "inline-block",
              padding: "0.625rem 1.5rem",
              borderRadius: "0.5rem",
              border: "1px solid currentColor",
              textDecoration: "none",
              fontWeight: 500,
            }}
          >
            Sign in with SSO
          </a>
        ) : null}
        {bootstrapLoginEnabled() ? <TokenForm next={next ?? "/engagements"} /> : null}
      </div>
    </main>
  );
}
