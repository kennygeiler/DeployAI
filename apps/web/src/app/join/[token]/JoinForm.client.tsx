"use client";

/**
 * Invite-accept flow: preview the invite (workspace + role + email), then set
 * a display name + password. Accepting creates the account server-side and
 * sets the session cookies, so the invitee lands in the app signed in.
 * Invalid, expired, and already-used tokens are one generic error by design.
 */

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Preview = {
  email: string;
  role: string;
  workspace_name: string | null;
  expires_at: string;
};

export function JoinForm({ token }: { token: string }) {
  const [preview, setPreview] = React.useState<Preview | null>(null);
  const [dead, setDead] = React.useState<string | null>(null);
  const [displayName, setDisplayName] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/auth/invites/preview?token=${encodeURIComponent(token)}`);
        const body = (await res.json().catch(() => null)) as (Preview & { error?: string }) | null;
        if (cancelled) {
          return;
        }
        if (res.ok && body?.email) {
          setPreview(body);
        } else {
          setDead(body?.error ?? "This invite link is invalid, expired, or already used.");
        }
      } catch {
        if (!cancelled) {
          setDead("Could not reach the server. Please try again.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!displayName.trim() || !password) {
      setError("Enter your name and a password.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/auth/invites/accept", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password, display_name: displayName.trim() }),
      });
      const body = (await res.json().catch(() => null)) as {
        ok?: boolean;
        next?: string;
        error?: string;
      } | null;
      if (res.ok && body?.ok) {
        window.location.assign(body.next ?? "/engagements");
        return;
      }
      setError(body?.error ?? "Could not accept the invite. Please try again.");
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  if (dead) {
    return (
      <div>
        <p role="alert" className="mb-4 text-sm text-destructive">
          {dead}
        </p>
        <p className="text-sm opacity-75">
          Ask a workspace admin for a fresh invite link, or{" "}
          <a href="/login" className="underline">
            sign in
          </a>{" "}
          if you already have an account.
        </p>
      </div>
    );
  }
  if (!preview) {
    return <p className="text-sm opacity-75">Checking your invite…</p>;
  }

  return (
    <div className="text-left">
      <p className="mb-4 text-sm">
        You&apos;re joining <strong>{preview.workspace_name ?? "a DeployAI workspace"}</strong> as{" "}
        <strong>{preview.role}</strong> ({preview.email}).
      </p>
      <form onSubmit={submit} aria-label="Accept invite">
        <div className="mb-3">
          <Label htmlFor="join-display-name">Your name</Label>
          <Input
            id="join-display-name"
            autoComplete="name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="mt-1"
          />
        </div>
        <div className="mb-3">
          <Label htmlFor="join-password">Password</Label>
          <Input
            id="join-password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1"
          />
          <p className="mt-1 text-xs text-muted-foreground">At least 10 characters.</p>
        </div>
        <div className="mb-4">
          <Label htmlFor="join-confirm">Confirm password</Label>
          <Input
            id="join-confirm"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="mt-1"
          />
        </div>
        {error ? (
          <p role="alert" className="mb-3 text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Joining…" : "Join workspace"}
        </Button>
      </form>
    </div>
  );
}
