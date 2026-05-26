"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Engagement } from "@/lib/bff/engagement-types";
import type { AppUser } from "@/lib/internal/tenant-users-cp";

/**
 * Onboarding wizard.
 *
 * Step 0 is a picker: load a pre-canned scenario (BlueState 26-week demo,
 * BlueState-XL 5-year stress test, or DeployAI Portfolio multi-engagement
 * isolation fixture) or start fresh (LLM → engagement → member 3-step flow).
 */

type ProviderChoice = "anthropic" | "openai" | "stub";
const PROVIDERS: readonly ProviderChoice[] = ["anthropic", "openai", "stub"];

type MemberRole = "deployment_strategist" | "fde" | "biz_dev";
const MEMBER_ROLES: readonly MemberRole[] = ["deployment_strategist", "fde", "biz_dev"];
const ROLE_LABEL: Record<MemberRole, string> = {
  deployment_strategist: "Deployment strategist",
  fde: "Forward-deployed engineer",
  biz_dev: "Business development",
};

type Step = 0 | 1 | 2 | 3;

export function OnboardingWizard() {
  const router = useRouter();
  const [step, setStep] = React.useState<Step>(0);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  // Step 1 state — LLM
  const [provider, setProvider] = React.useState<ProviderChoice>("anthropic");
  const [modelName, setModelName] = React.useState("");
  const [apiKey, setApiKey] = React.useState("");

  // Step 2 state — engagement
  const [engagementName, setEngagementName] = React.useState("");
  const [customerAccount, setCustomerAccount] = React.useState("");
  const [createdEngagement, setCreatedEngagement] = React.useState<Engagement | null>(null);

  // Step 3 state — first member
  const [userName, setUserName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState<MemberRole>("deployment_strategist");

  const loadBluestate = React.useCallback(async () => {
    setBusy(true);
    setErr(null);
    let target: string | null = null;
    try {
      const r = await fetch("/api/bff/onboarding/seed-bluestate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: false }),
      });
      if (r.status === 409) {
        const conflict = (await r.json()) as { error: string; engagement_id: string };
        toast("Demo scenario already seeded.", {
          description: "Open the BlueState engagement?",
          action: {
            label: "Open",
            onClick: () =>
              router.push(`/engagements/${encodeURIComponent(conflict.engagement_id)}`),
          },
        });
        return;
      }
      if (!r.ok) {
        setErr((await r.text()).slice(0, 240));
        return;
      }
      const body = (await r.json()) as { engagement_id: string };
      target = body.engagement_id;
      toast.success("BlueState demo loaded");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load demo scenario.");
    } finally {
      setBusy(false);
    }
    if (target) {
      router.push(`/engagements/${encodeURIComponent(target)}`);
    }
  }, [router]);

  const loadBluestateXl = React.useCallback(async () => {
    setBusy(true);
    setErr(null);
    let target: string | null = null;
    try {
      const r = await fetch("/api/bff/onboarding/seed-bluestate-xl", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: false }),
      });
      if (r.status === 409) {
        const conflict = (await r.json()) as { error: string; engagement_id: string };
        toast("BlueState-XL already seeded.", {
          description: "Open the 5-year engagement?",
          action: {
            label: "Open",
            onClick: () =>
              router.push(`/engagements/${encodeURIComponent(conflict.engagement_id)}`),
          },
        });
        return;
      }
      if (!r.ok) {
        setErr((await r.text()).slice(0, 240));
        return;
      }
      const body = (await r.json()) as { engagement_id: string };
      target = body.engagement_id;
      toast.success("BlueState-XL loaded");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load BlueState-XL.");
    } finally {
      setBusy(false);
    }
    if (target) {
      router.push(`/engagements/${encodeURIComponent(target)}`);
    }
  }, [router]);

  const loadPortfolio = React.useCallback(async () => {
    setBusy(true);
    setErr(null);
    let target: string | null = null;
    try {
      const r = await fetch("/api/bff/onboarding/seed-portfolio", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: false }),
      });
      if (r.status === 409) {
        const conflict = (await r.json()) as { error: string; engagement_ids: string[] };
        const firstId = conflict.engagement_ids[0];
        toast("Portfolio fixture already seeded.", {
          description: firstId ? "Open the first portfolio engagement?" : undefined,
          action: firstId
            ? {
                label: "Open",
                onClick: () => router.push(`/engagements/${encodeURIComponent(firstId)}`),
              }
            : undefined,
        });
        return;
      }
      if (!r.ok) {
        setErr((await r.text()).slice(0, 240));
        return;
      }
      const body = (await r.json()) as {
        summary: { engagements: { engagement_id: string }[] };
      };
      target = body.summary.engagements[0]?.engagement_id ?? null;
      toast.success("DeployAI Portfolio loaded");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load portfolio fixture.");
    } finally {
      setBusy(false);
    }
    if (target) {
      router.push(`/engagements/${encodeURIComponent(target)}`);
    }
  }, [router]);

  const startFresh = React.useCallback(() => {
    setErr(null);
    setStep(1);
  }, []);

  const submitLlm = React.useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/bff/tenant/llm-config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider,
          model_name: modelName.trim() || null,
          ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
        }),
      });
      if (!r.ok) {
        setErr((await r.text()).slice(0, 240));
        return;
      }
      setApiKey("");
      setStep(2);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save LLM config.");
    } finally {
      setBusy(false);
    }
  }, [provider, modelName, apiKey]);

  const submitEngagement = React.useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/bff/engagements", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: engagementName.trim(),
          customer_account: customerAccount.trim() || null,
        }),
      });
      if (!r.ok) {
        setErr((await r.text()).slice(0, 240));
        return;
      }
      const body = (await r.json()) as { engagement: Engagement };
      setCreatedEngagement(body.engagement);
      setStep(3);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not create engagement.");
    } finally {
      setBusy(false);
    }
  }, [engagementName, customerAccount]);

  const submitMember = React.useCallback(async () => {
    if (!createdEngagement) {
      setErr("Engagement is missing; please go back to step 2.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const userRes = await fetch("/api/bff/tenant/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_name: userName.trim(),
          email: email.trim() || null,
        }),
      });
      if (!userRes.ok) {
        setErr((await userRes.text()).slice(0, 240));
        return;
      }
      const userBody = (await userRes.json()) as { user: AppUser };
      const memberRes = await fetch(
        `/api/bff/engagements/${encodeURIComponent(createdEngagement.id)}/members`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userBody.user.id, role }),
        },
      );
      if (!memberRes.ok) {
        setErr((await memberRes.text()).slice(0, 240));
        return;
      }
      toast.success("Onboarding complete");
      router.push(`/engagements/${encodeURIComponent(createdEngagement.id)}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not add team member.");
    } finally {
      setBusy(false);
    }
  }, [createdEngagement, userName, email, role, router]);

  const stepLabel =
    step === 0 ? "Choose" : step === 1 ? "LLM" : step === 2 ? "Engagement" : "Team member";
  const stepDisplay = step === 0 ? "Start" : `Step ${step} of 3`;

  return (
    <section
      aria-labelledby="onboarding-heading"
      aria-busy={busy ? "true" : "false"}
      className="max-w-4xl space-y-6"
    >
      <header>
        <h1 id="onboarding-heading" className="text-xl font-semibold">
          Set up DeployAI for your team
        </h1>
        <p className="text-ink-600 mt-1 text-sm">
          Load a pre-canned scenario in one click, or walk the three-step setup to configure the
          LLM, create your first engagement, and add a team member.
        </p>
        <p className="text-ink-700 mt-3 text-xs font-mono uppercase">
          {stepDisplay} — {stepLabel}
        </p>
      </header>

      {err ? <p className="text-error-700 text-sm">{err}</p> : null}
      {busy && step === 0 ? (
        <p role="status" aria-label="Loading scenario" className="text-ink-700 text-sm">
          Loading scenario (this can take 20–60 seconds)…
        </p>
      ) : null}

      {step === 0 ? (
        <PickerStep
          onLoadBluestate={loadBluestate}
          onLoadBluestateXl={loadBluestateXl}
          onLoadPortfolio={loadPortfolio}
          onStartFresh={startFresh}
          busy={busy}
        />
      ) : null}

      {step === 1 ? (
        <LlmStep
          provider={provider}
          setProvider={setProvider}
          modelName={modelName}
          setModelName={setModelName}
          apiKey={apiKey}
          setApiKey={setApiKey}
          onSubmit={submitLlm}
          busy={busy}
        />
      ) : null}

      {step === 2 ? (
        <EngagementStep
          name={engagementName}
          setName={setEngagementName}
          customerAccount={customerAccount}
          setCustomerAccount={setCustomerAccount}
          onSubmit={submitEngagement}
          busy={busy}
        />
      ) : null}

      {step === 3 ? (
        <MemberStep
          userName={userName}
          setUserName={setUserName}
          email={email}
          setEmail={setEmail}
          role={role}
          setRole={setRole}
          onSubmit={submitMember}
          busy={busy}
        />
      ) : null}
    </section>
  );
}

function PickerStep(props: {
  onLoadBluestate: () => void;
  onLoadBluestateXl: () => void;
  onLoadPortfolio: () => void;
  onStartFresh: () => void;
  busy: boolean;
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-2 xl:grid-cols-4">
      <Button
        type="button"
        variant="default"
        onClick={props.onLoadBluestate}
        disabled={props.busy}
        className="h-auto flex-col items-start gap-2 whitespace-normal break-words p-4 text-left"
      >
        <span className="text-sm font-semibold">Load BlueState demo (26-week scenario)</span>
        <span className="text-ink-100 text-xs font-normal">
          One-click seed with stakeholders, decisions, risks, snapshots, and temporal insights.
        </span>
      </Button>
      <Button
        type="button"
        variant="outline"
        onClick={props.onLoadBluestateXl}
        disabled={props.busy}
        className="h-auto flex-col items-start gap-2 whitespace-normal break-words p-4 text-left"
      >
        <span className="text-sm font-semibold">Load BlueState-XL (5-year stress test)</span>
        <span className="text-ink-700 text-xs font-normal">
          Stress-test fixture for Agent Kenny v2 — 5 years of compounded events.
        </span>
      </Button>
      <Button
        type="button"
        variant="outline"
        onClick={props.onLoadPortfolio}
        disabled={props.busy}
        className="h-auto flex-col items-start gap-2 whitespace-normal break-words p-4 text-left"
      >
        <span className="text-sm font-semibold">
          Load DeployAI Portfolio (5 engagements × 26 weeks)
        </span>
        <span className="text-ink-700 text-xs font-normal">
          Cross-engagement isolation stress fixture — five realistic deployments under one tenant.
        </span>
      </Button>
      <Button
        type="button"
        variant="outline"
        onClick={props.onStartFresh}
        disabled={props.busy}
        className="h-auto flex-col items-start gap-2 whitespace-normal break-words p-4 text-left"
      >
        <span className="text-sm font-semibold">Start fresh</span>
        <span className="text-ink-700 text-xs font-normal">
          Configure LLM, create your first engagement, and add a team member.
        </span>
      </Button>
    </div>
  );
}

function LlmStep(props: {
  provider: ProviderChoice;
  setProvider: (v: ProviderChoice) => void;
  modelName: string;
  setModelName: (v: string) => void;
  apiKey: string;
  setApiKey: (v: string) => void;
  onSubmit: () => void;
  busy: boolean;
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        props.onSubmit();
      }}
      className="max-w-xl space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="ob-provider">Provider</Label>
        <select
          id="ob-provider"
          value={props.provider}
          onChange={(e) => props.setProvider(e.target.value as ProviderChoice)}
          className="border-border focus-visible:ring-ring h-9 w-full rounded-md border px-3 text-sm focus-visible:outline-none focus-visible:ring-2"
        >
          {PROVIDERS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="ob-model">Model</Label>
        <Input
          id="ob-model"
          value={props.modelName}
          onChange={(e) => props.setModelName(e.target.value)}
          placeholder={props.provider === "anthropic" ? "claude-opus-4-5" : "(provider default)"}
          autoComplete="off"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="ob-key">API key</Label>
        <Input
          id="ob-key"
          type="password"
          value={props.apiKey}
          onChange={(e) => props.setApiKey(e.target.value)}
          placeholder="sk-…"
          autoComplete="off"
        />
        <p className="text-ink-600 text-xs">
          Stored in your tenant&apos;s local database. Leave blank to fall back to the server&apos;s
          environment variables.
        </p>
      </div>
      <Button type="submit" disabled={props.busy}>
        {props.busy ? "Saving…" : "Continue"}
      </Button>
    </form>
  );
}

function EngagementStep(props: {
  name: string;
  setName: (v: string) => void;
  customerAccount: string;
  setCustomerAccount: (v: string) => void;
  onSubmit: () => void;
  busy: boolean;
}) {
  const canSubmit = props.name.trim().length > 0;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSubmit) props.onSubmit();
      }}
      className="max-w-xl space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="ob-eng-name">Engagement name</Label>
        <Input
          id="ob-eng-name"
          value={props.name}
          onChange={(e) => props.setName(e.target.value)}
          placeholder="Acme migration pilot"
          required
          autoComplete="off"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="ob-eng-customer">Customer account (optional)</Label>
        <Input
          id="ob-eng-customer"
          value={props.customerAccount}
          onChange={(e) => props.setCustomerAccount(e.target.value)}
          placeholder="Acme Corp"
          autoComplete="off"
        />
      </div>
      <Button type="submit" disabled={!canSubmit || props.busy}>
        {props.busy ? "Creating…" : "Create engagement"}
      </Button>
    </form>
  );
}

function MemberStep(props: {
  userName: string;
  setUserName: (v: string) => void;
  email: string;
  setEmail: (v: string) => void;
  role: MemberRole;
  setRole: (v: MemberRole) => void;
  onSubmit: () => void;
  busy: boolean;
}) {
  const canSubmit = props.userName.trim().length > 0;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSubmit) props.onSubmit();
      }}
      className="max-w-xl space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="ob-user-name">Username</Label>
        <Input
          id="ob-user-name"
          value={props.userName}
          onChange={(e) => props.setUserName(e.target.value)}
          placeholder="kenny"
          required
          autoComplete="off"
        />
        <p className="text-ink-600 text-xs">
          Unique-per-tenant identifier. Match your IdP login when you wire one up later.
        </p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="ob-user-email">Email (optional)</Label>
        <Input
          id="ob-user-email"
          type="email"
          value={props.email}
          onChange={(e) => props.setEmail(e.target.value)}
          placeholder="kenny@example.com"
          autoComplete="off"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="ob-role">Role</Label>
        <select
          id="ob-role"
          value={props.role}
          onChange={(e) => props.setRole(e.target.value as MemberRole)}
          className="border-border focus-visible:ring-ring h-9 w-full rounded-md border px-3 text-sm focus-visible:outline-none focus-visible:ring-2"
        >
          {MEMBER_ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </select>
      </div>
      <Button type="submit" disabled={!canSubmit || props.busy}>
        {props.busy ? "Finishing…" : "Finish setup"}
      </Button>
    </form>
  );
}
