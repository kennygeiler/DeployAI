"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { TenantLlmConfig } from "@/lib/internal/llm-config-cp";

/**
 * Sprint 1 — LLM provider settings form.
 *
 * Provider + model + API key only. The API key field is write-only: GETs
 * never return the raw secret, just the last-4 fingerprint via
 * `api_key_masked`. Leaving the key field blank on save preserves the
 * previously stored key (so the user can change model without
 * re-pasting).
 *
 * When no row exists (provider=`null`), the agent factory falls back to
 * env defaults (DEPLOYAI_LLM_PROVIDER / ANTHROPIC_API_KEY) — this is
 * what dev/CI uses. The empty-state copy tells the user that.
 */

type ProviderChoice = "anthropic" | "openai" | "stub";
const PROVIDERS: readonly ProviderChoice[] = ["anthropic", "openai", "stub"];

export function LlmConfigForm() {
  const [cfg, setCfg] = React.useState<TenantLlmConfig | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  const [provider, setProvider] = React.useState<ProviderChoice>("anthropic");
  const [modelName, setModelName] = React.useState("");
  const [apiKey, setApiKey] = React.useState("");

  const [failoverEnabled, setFailoverEnabled] = React.useState(false);
  const [secondaryProvider, setSecondaryProvider] = React.useState<ProviderChoice>("openai");
  const [secondaryModelName, setSecondaryModelName] = React.useState("");
  const [secondaryApiKey, setSecondaryApiKey] = React.useState("");

  const load = React.useCallback(async () => {
    const r = await fetch("/api/bff/tenant/llm-config", { method: "GET" });
    if (!r.ok) {
      setErr(`Could not load config (${r.status})`);
      return;
    }
    setErr(null);
    const body = (await r.json()) as { config: TenantLlmConfig | null };
    const c = body.config;
    setCfg(c);
    if (c) {
      if (PROVIDERS.includes(c.provider as ProviderChoice)) {
        setProvider(c.provider as ProviderChoice);
      }
      setModelName(c.model_name ?? "");
      const hasSecondary = c.secondary_provider !== null;
      setFailoverEnabled(hasSecondary);
      if (hasSecondary && PROVIDERS.includes(c.secondary_provider as ProviderChoice)) {
        setSecondaryProvider(c.secondary_provider as ProviderChoice);
      }
      setSecondaryModelName(c.secondary_model_name ?? "");
    }
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        await load();
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load LLM config.");
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

  const onSubmit = React.useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setSaving(true);
      try {
        const r = await fetch("/api/bff/tenant/llm-config", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider,
            model_name: modelName.trim() || null,
            // Send the api_key only if the user typed one in this session.
            // Empty string preserves the previously stored key server-side.
            ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
            // Always send the secondary trio so the BFF + CP can mirror
            // the toggle state. Nulls clear the failover side; values
            // enable it. A blank secondary_api_key while enabled is
            // treated as "preserve the stored secret" (same rule as the
            // primary key).
            secondary_provider: failoverEnabled ? secondaryProvider : null,
            secondary_model_name: failoverEnabled ? secondaryModelName.trim() || null : null,
            secondary_api_key:
              failoverEnabled && secondaryApiKey.trim() ? secondaryApiKey.trim() : null,
          }),
        });
        if (!r.ok) {
          const text = await r.text();
          toast.error("Could not save LLM config", { description: text.slice(0, 240) });
          return;
        }
        const body = (await r.json()) as { config: TenantLlmConfig };
        setCfg(body.config);
        setApiKey(""); // never echo back; mask shows the stored fingerprint
        setSecondaryApiKey("");
        toast.success("LLM config saved");
      } finally {
        setSaving(false);
      }
    },
    [
      provider,
      modelName,
      apiKey,
      failoverEnabled,
      secondaryProvider,
      secondaryModelName,
      secondaryApiKey,
    ],
  );

  if (loading) {
    return <p className="text-ink-600 text-sm">Loading…</p>;
  }

  return (
    <form onSubmit={onSubmit} aria-labelledby="llm-config-heading" className="max-w-xl space-y-4">
      <div>
        <h2 id="llm-config-heading" className="text-base font-semibold">
          LLM provider
        </h2>
        <p className="text-ink-600 mt-1 text-sm">
          {cfg
            ? "Saved per tenant. Used by the extraction + synthesis agents on every refresh."
            : "Not configured yet — agents fall back to the server's environment defaults until you save here."}
        </p>
      </div>

      {err ? <p className="text-error-700 text-sm">{err}</p> : null}

      <div className="space-y-2">
        <Label htmlFor="provider">Provider</Label>
        <select
          id="provider"
          name="provider"
          value={provider}
          onChange={(e) => setProvider(e.target.value as ProviderChoice)}
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
        <Label htmlFor="model_name">Model</Label>
        <Input
          id="model_name"
          name="model_name"
          value={modelName}
          onChange={(e) => setModelName(e.target.value)}
          placeholder={provider === "anthropic" ? "claude-opus-4-5" : "(provider default)"}
          autoComplete="off"
        />
        <p className="text-ink-600 text-xs">
          Leave blank to use the provider library&apos;s default model.
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="api_key">API key</Label>
        <Input
          id="api_key"
          name="api_key"
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={cfg?.has_api_key ? (cfg.api_key_masked ?? "•••• stored") : "(none stored)"}
          autoComplete="off"
        />
        <p className="text-ink-600 text-xs">
          {cfg?.has_api_key
            ? "Leave blank to keep the stored key. Type a new value to replace it."
            : "Required for the chosen provider unless the server has one in the environment."}
        </p>
      </div>

      <div className="border-border space-y-3 border-t pt-4">
        <div className="flex items-center gap-2">
          <input
            id="failover_enabled"
            name="failover_enabled"
            type="checkbox"
            checked={failoverEnabled}
            onChange={(e) => setFailoverEnabled(e.target.checked)}
            className="border-border h-4 w-4 rounded"
          />
          <Label htmlFor="failover_enabled" className="cursor-pointer">
            Enable failover
          </Label>
        </div>
        <p className="text-ink-600 text-xs">
          When the primary provider errors out, agents retry on the secondary before bubbling the
          failure up.
        </p>

        {failoverEnabled ? (
          <div className="space-y-4 pl-1">
            <div className="space-y-2">
              <Label htmlFor="secondary_provider">Secondary provider</Label>
              <select
                id="secondary_provider"
                name="secondary_provider"
                value={secondaryProvider}
                onChange={(e) => setSecondaryProvider(e.target.value as ProviderChoice)}
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
              <Label htmlFor="secondary_model_name">Secondary model</Label>
              <Input
                id="secondary_model_name"
                name="secondary_model_name"
                value={secondaryModelName}
                onChange={(e) => setSecondaryModelName(e.target.value)}
                placeholder={
                  secondaryProvider === "anthropic" ? "claude-opus-4-5" : "(provider default)"
                }
                autoComplete="off"
              />
              <p className="text-ink-600 text-xs">
                Leave blank to use the provider library&apos;s default model.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="secondary_api_key">Secondary API key</Label>
              <Input
                id="secondary_api_key"
                name="secondary_api_key"
                type="password"
                value={secondaryApiKey}
                onChange={(e) => setSecondaryApiKey(e.target.value)}
                placeholder={
                  cfg?.has_secondary_api_key
                    ? (cfg.secondary_api_key_masked ?? "•••• stored")
                    : "(none stored)"
                }
                autoComplete="off"
              />
              <p className="text-ink-600 text-xs">
                {cfg?.has_secondary_api_key
                  ? "Leave blank to keep the stored key. Type a new value to replace it."
                  : "Required for the chosen provider unless the server has one in the environment."}
              </p>
            </div>
          </div>
        ) : null}
      </div>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
        {cfg ? (
          <span className="text-ink-600 text-xs">
            Last updated {new Date(cfg.updated_at).toLocaleString()}
          </span>
        ) : null}
      </div>
    </form>
  );
}
