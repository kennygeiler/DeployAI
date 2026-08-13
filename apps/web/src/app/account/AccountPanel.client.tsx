"use client";

/**
 * Account page body: session profile, change-password, sign-out, and (for
 * admins) workspace invites.
 *
 * - Display name is read-only: the only profile-mutation surface in the stack
 *   today is SCIM (enterprise IdP-owned); there is no self-serve profile
 *   route, so we honestly render instead of pretending to save.
 * - Invites produce a copyable join link — there is NO email delivery
 *   anywhere in the product; the admin sends the link themselves.
 */

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Me = {
  user_id: string;
  tenant_id: string;
  tenant_name: string | null;
  email: string | null;
  display_name: string | null;
  roles: string[];
  has_password: boolean;
};

type PendingInvite = {
  invite_id: string;
  email: string;
  role: string;
  expires_at: string;
  created_at: string;
};

const INVITABLE_ROLES = [
  "deployment_strategist",
  "customer_admin",
  "fde",
  "biz_dev",
  "successor_strategist",
  "customer_records_officer",
  "external_auditor",
] as const;

function ChangePasswordForm() {
  const [current, setCurrent] = React.useState("");
  const [next, setNext] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [done, setDone] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setDone(false);
    if (!current || !next) {
      setError("Enter your current and new password.");
      return;
    }
    if (next !== confirm) {
      setError("New passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      const body = (await res.json().catch(() => null)) as { ok?: boolean; error?: string } | null;
      if (res.ok && body?.ok) {
        setDone(true);
        setCurrent("");
        setNext("");
        setConfirm("");
      } else {
        setError(body?.error ?? "Password change failed. Please try again.");
      }
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} aria-label="Change password" className="max-w-sm">
      <div className="mb-3">
        <Label htmlFor="pw-current">Current password</Label>
        <Input
          id="pw-current"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          className="mt-1"
        />
      </div>
      <div className="mb-3">
        <Label htmlFor="pw-new">New password</Label>
        <Input
          id="pw-new"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          className="mt-1"
        />
        <p className="mt-1 text-xs text-muted-foreground">At least 10 characters.</p>
      </div>
      <div className="mb-4">
        <Label htmlFor="pw-confirm">Confirm new password</Label>
        <Input
          id="pw-confirm"
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
      {done ? (
        <p role="status" className="mb-3 text-sm">
          Password changed. Other sessions have been signed out.
        </p>
      ) : null}
      <Button type="submit" disabled={busy}>
        {busy ? "Changing…" : "Change password"}
      </Button>
    </form>
  );
}

function InvitesSection() {
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState<string>("deployment_strategist");
  const [joinUrl, setJoinUrl] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [pending, setPending] = React.useState<PendingInvite[]>([]);
  // Bumped after a successful create so the effect refetches the pending list.
  const [pendingRefresh, setPendingRefresh] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/auth/invites");
        const body = (await res.json().catch(() => null)) as PendingInvite[] | null;
        if (!cancelled && res.ok && Array.isArray(body)) {
          setPending(body);
        }
      } catch {
        // pending list is best-effort
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pendingRefresh]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setJoinUrl(null);
    setCopied(false);
    if (!email.trim()) {
      setError("Enter the teammate's email.");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/auth/invites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), role }),
      });
      const body = (await res.json().catch(() => null)) as {
        join_url?: string;
        error?: string;
      } | null;
      if (res.ok && body?.join_url) {
        setJoinUrl(body.join_url);
        setEmail("");
        setPendingRefresh((n) => n + 1);
      } else {
        setError(body?.error ?? "Invite creation failed. Please try again.");
      }
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!joinUrl) {
      return;
    }
    try {
      await navigator.clipboard.writeText(joinUrl);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div>
      <p className="mb-3 text-sm opacity-75">
        Invites create a single-use join link (valid 7 days). No email is sent — copy the link and
        share it with your teammate yourself.
      </p>
      <form onSubmit={submit} aria-label="Invite a teammate" className="max-w-sm">
        <div className="mb-3">
          <Label htmlFor="invite-email">Email</Label>
          <Input
            id="invite-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1"
          />
        </div>
        <div className="mb-4">
          <Label htmlFor="invite-role">Role</Label>
          <select
            id="invite-role"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="mt-1 h-9 w-full rounded-control border border-transparent bg-field px-3 py-1 text-sm shadow-inset-field outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            {INVITABLE_ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        {error ? (
          <p role="alert" className="mb-3 text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <Button type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create invite link"}
        </Button>
      </form>
      {joinUrl ? (
        <div className="mt-4 max-w-xl">
          <Label htmlFor="invite-join-url">Join link (copy it now — it is shown once)</Label>
          <div className="mt-1 flex items-center gap-2">
            <Input id="invite-join-url" readOnly value={joinUrl} className="font-mono text-xs" />
            <Button type="button" variant="outline" onClick={copy}>
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
        </div>
      ) : null}
      {pending.length > 0 ? (
        <div className="mt-6">
          <h3 className="mb-2 text-sm font-medium">Pending invites</h3>
          <ul className="space-y-1 text-sm">
            {pending.map((i) => (
              <li key={i.invite_id} className="flex items-center gap-2">
                <span>{i.email}</span>
                <span className="opacity-60">as {i.role}</span>
                <span className="opacity-60">
                  · expires {new Date(i.expires_at).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function AccountPanel() {
  const [me, setMe] = React.useState<Me | null>(null);
  const [failed, setFailed] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/auth/me");
        const body = (await res.json().catch(() => null)) as (Me & { error?: string }) | null;
        if (cancelled) {
          return;
        }
        if (res.ok && body?.user_id) {
          setMe(body);
        } else {
          setFailed(body?.error ?? "Could not load your account.");
        }
      } catch {
        if (!cancelled) {
          setFailed("Could not reach the server.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (failed) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {failed}
      </p>
    );
  }
  if (!me) {
    return <p className="text-sm opacity-75">Loading account…</p>;
  }

  const isAdmin = me.roles.includes("customer_admin") || me.roles.includes("platform_admin");

  return (
    <div className="space-y-10">
      <section aria-labelledby="account-profile">
        <h2 id="account-profile" className="mb-3 text-lg font-semibold">
          Profile
        </h2>
        <dl className="grid max-w-xl grid-cols-[10rem_1fr] gap-y-2 text-sm">
          <dt className="opacity-60">Name</dt>
          <dd>{me.display_name ?? "—"}</dd>
          <dt className="opacity-60">Email</dt>
          <dd>{me.email ?? "—"}</dd>
          <dt className="opacity-60">Roles</dt>
          <dd>{me.roles.join(", ") || "—"}</dd>
          <dt className="opacity-60">Workspace</dt>
          <dd>{me.tenant_name ?? "—"}</dd>
          <dt className="opacity-60">Tenant ID</dt>
          <dd className="font-mono text-xs">{me.tenant_id}</dd>
        </dl>
        <p className="mt-2 text-xs opacity-60">
          Profile details are read-only here; they come from your sign-up or your identity provider.
        </p>
      </section>

      <section aria-labelledby="account-password">
        <h2 id="account-password" className="mb-3 text-lg font-semibold">
          Password
        </h2>
        {me.has_password ? (
          <ChangePasswordForm />
        ) : (
          <p className="text-sm opacity-75">
            This account signs in with SSO; there is no password to change.
          </p>
        )}
      </section>

      {isAdmin ? (
        <section aria-labelledby="account-invites">
          <h2 id="account-invites" className="mb-3 text-lg font-semibold">
            Invite teammates
          </h2>
          <InvitesSection />
        </section>
      ) : null}

      <section aria-labelledby="account-session">
        <h2 id="account-session" className="mb-3 text-lg font-semibold">
          Session
        </h2>
        <form method="POST" action="/api/auth/logout">
          <Button type="submit" variant="outline">
            Sign out
          </Button>
        </form>
      </section>
    </div>
  );
}
