"use client";

/**
 * Self-serve workspace creation form. Posts to `/api/auth/signup`; on success
 * the BFF has already set the session cookies, so we hard-navigate straight
 * into the app. Password policy (length 10-72, common-password blocklist) is
 * enforced by the control plane — the only client-side check is the confirm
 * field, which the CP cannot see.
 */

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function SignupForm() {
  const [workspace, setWorkspace] = React.useState("");
  const [displayName, setDisplayName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!workspace.trim() || !displayName.trim() || !email.trim() || !password) {
      setError("All fields are required.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          password,
          workspace_name: workspace.trim(),
          display_name: displayName.trim(),
        }),
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
      setError(body?.error ?? "Sign-up failed. Please try again.");
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="text-left" aria-label="Create a workspace">
      <div className="mb-3">
        <Label htmlFor="signup-workspace">Workspace name</Label>
        <Input
          id="signup-workspace"
          value={workspace}
          onChange={(e) => setWorkspace(e.target.value)}
          className="mt-1"
        />
      </div>
      <div className="mb-3">
        <Label htmlFor="signup-display-name">Your name</Label>
        <Input
          id="signup-display-name"
          autoComplete="name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="mt-1"
        />
      </div>
      <div className="mb-3">
        <Label htmlFor="signup-email">Email</Label>
        <Input
          id="signup-email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1"
        />
      </div>
      <div className="mb-3">
        <Label htmlFor="signup-password">Password</Label>
        <Input
          id="signup-password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1"
        />
        <p className="mt-1 text-xs text-muted-foreground">At least 10 characters.</p>
      </div>
      <div className="mb-4">
        <Label htmlFor="signup-confirm">Confirm password</Label>
        <Input
          id="signup-confirm"
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
        {busy ? "Creating workspace…" : "Create workspace"}
      </Button>
    </form>
  );
}
