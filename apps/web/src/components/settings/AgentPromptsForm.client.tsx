"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  AGENT_NAMES,
  type AgentName,
  type AgentPromptEntry,
  type AgentPromptsRead,
} from "@/lib/internal/agent-prompts-cp";

/**
 * Sprint 5 — per-tenant agent prompt overrides settings form.
 *
 * Three textareas (Cartographer / Oracle / Master Strategist). Each one
 * shows the resolved prompt (override if present, baked-in default
 * otherwise) and offers Save / Reset to default. "Reset" only enables
 * for an override (not for a default).
 */

const AGENT_LABELS: Record<AgentName, string> = {
  cartographer: "Cartographer (matrix extractor)",
  oracle: "Oracle (per-engagement insights)",
  master_strategist: "Master Strategist (cross-engagement insights)",
};

type DraftMap = Record<AgentName, string>;
type SavedMap = Record<AgentName, AgentPromptEntry>;

function emptyDrafts(): DraftMap {
  return { cartographer: "", oracle: "", master_strategist: "" };
}

export function AgentPromptsForm() {
  const [saved, setSaved] = React.useState<SavedMap | null>(null);
  const [drafts, setDrafts] = React.useState<DraftMap>(emptyDrafts());
  const [busy, setBusy] = React.useState<AgentName | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);

  const applyResponse = React.useCallback((body: AgentPromptsRead) => {
    setSaved(body.prompts);
    setDrafts({
      cartographer: body.prompts.cartographer.value,
      oracle: body.prompts.oracle.value,
      master_strategist: body.prompts.master_strategist.value,
    });
  }, []);

  const load = React.useCallback(async () => {
    const r = await fetch("/api/bff/tenant/agent-prompts", { method: "GET" });
    if (!r.ok) {
      setErr(`Could not load prompts (${r.status})`);
      return;
    }
    setErr(null);
    applyResponse((await r.json()) as AgentPromptsRead);
  }, [applyResponse]);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        await load();
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load agent prompts.");
        }
      }
      if (!cancelled) {
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  const onSave = React.useCallback(
    async (name: AgentName) => {
      setBusy(name);
      try {
        const r = await fetch(`/api/bff/tenant/agent-prompts/${encodeURIComponent(name)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt_text: drafts[name] }),
        });
        if (!r.ok) {
          const text = await r.text();
          toast.error("Could not save prompt", { description: text.slice(0, 240) });
          return;
        }
        const body = (await r.json()) as { entry: AgentPromptEntry };
        setSaved((prev) => (prev ? { ...prev, [name]: body.entry } : prev));
        toast.success(`${AGENT_LABELS[name]} prompt saved`);
      } finally {
        setBusy(null);
      }
    },
    [drafts],
  );

  const onReset = React.useCallback(
    async (name: AgentName) => {
      setBusy(name);
      try {
        const r = await fetch(`/api/bff/tenant/agent-prompts/${encodeURIComponent(name)}`, {
          method: "DELETE",
        });
        if (!r.ok && r.status !== 204) {
          const text = await r.text();
          toast.error("Could not reset prompt", { description: text.slice(0, 240) });
          return;
        }
        // Re-fetch the list so the textarea snaps to the baked-in default.
        await load();
        toast.success(`${AGENT_LABELS[name]} prompt reset to default`);
      } finally {
        setBusy(null);
      }
    },
    [load],
  );

  if (loading) {
    return <p className="text-ink-600 text-sm">Loading…</p>;
  }

  return (
    <section aria-labelledby="agent-prompts-heading" className="max-w-3xl space-y-6">
      <div>
        <h2 id="agent-prompts-heading" className="text-base font-semibold">
          Agent system prompts
        </h2>
        <p className="text-ink-600 mt-1 text-sm">
          Override the system prompt each agent uses. Reset to default reverts to the shipped prompt
          for that agent.
        </p>
      </div>

      {err ? <p className="text-error-700 text-sm">{err}</p> : null}

      {AGENT_NAMES.map((name) => {
        const entry = saved?.[name];
        const isDefault = entry?.is_default ?? true;
        return (
          <form
            key={name}
            onSubmit={(e) => {
              e.preventDefault();
              void onSave(name);
            }}
            className="space-y-2"
          >
            <div className="flex items-baseline justify-between">
              <Label htmlFor={`agent-prompt-${name}`}>{AGENT_LABELS[name]}</Label>
              <span className="text-ink-600 text-xs">
                {isDefault ? "Using baked-in default" : "Custom override saved"}
              </span>
            </div>
            <Textarea
              id={`agent-prompt-${name}`}
              name={`agent-prompt-${name}`}
              rows={10}
              value={drafts[name]}
              onChange={(e) => setDrafts((prev) => ({ ...prev, [name]: e.target.value }))}
              className="font-mono text-xs"
            />
            <div className="flex items-center gap-3">
              <Button type="submit" disabled={busy === name}>
                {busy === name ? "Saving…" : "Save"}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={busy === name || isDefault}
                onClick={() => void onReset(name)}
              >
                Reset to default
              </Button>
            </div>
          </form>
        );
      })}
    </section>
  );
}
