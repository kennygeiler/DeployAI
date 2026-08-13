/**
 * Invite landing page (`/join/<token>`). Always routable — whether a given
 * token is live is decided server-side by the control plane; the page just
 * hosts the preview + accept form. The raw token exists only in this URL and
 * the accept POST body; it is never persisted anywhere client-side.
 */

import { JoinForm } from "./JoinForm.client";

export const metadata = { title: "Join workspace — DeployAI" };

export default async function JoinPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
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
          Join a DeployAI workspace
        </h1>
        <p style={{ marginBottom: "1.5rem", opacity: 0.75 }}>
          Set a password to activate your account.
        </p>
        <JoinForm token={token} />
      </div>
    </main>
  );
}
