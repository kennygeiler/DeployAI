"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { Engagement } from "@/lib/bff/engagement-types";
import type { ApiKey } from "@/lib/internal/api-keys-cp";

import { ApiKeyMintDialog, type EngagementOption } from "./ApiKeyMintDialog.client";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function ApiKeyList() {
  const [keys, setKeys] = React.useState<ApiKey[]>([]);
  const [engagements, setEngagements] = React.useState<EngagementOption[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = React.useState(false);

  const load = React.useCallback(async () => {
    setErr(null);
    const [keysResp, engResp] = await Promise.all([
      fetch("/api/bff/tenant/api-keys", { method: "GET" }),
      fetch("/api/bff/engagements", { method: "GET" }),
    ]);
    if (!keysResp.ok) {
      setErr(`Could not load api keys (${keysResp.status})`);
      return;
    }
    if (!engResp.ok) {
      setErr(`Could not load engagements (${engResp.status})`);
      return;
    }
    const keysBody = (await keysResp.json()) as { api_keys: ApiKey[] };
    const engBody = (await engResp.json()) as { engagements: Engagement[] };
    setKeys(keysBody.api_keys);
    setEngagements(engBody.engagements.map((e) => ({ id: e.id, name: e.name })));
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        await load();
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load api keys.");
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

  const onRevoke = React.useCallback(
    async (id: string) => {
      const ok = window.confirm(
        "Revoke this api key? The next request from any client using it will be rejected.",
      );
      if (!ok) return;
      const r = await fetch(`/api/bff/tenant/api-keys/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      if (!r.ok) {
        toast.error("Could not revoke api key");
        return;
      }
      await load();
      toast.success("API key revoked");
    },
    [load],
  );

  if (loading) {
    return <p className="text-ink-600 text-sm">Loading…</p>;
  }

  return (
    <section aria-labelledby="api-keys-heading" className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 id="api-keys-heading" className="sr-only">
          API keys
        </h2>
        <Button type="button" onClick={() => setDialogOpen(true)}>
          Mint api key
        </Button>
      </div>

      {err ? <p className="text-error-700 text-sm">{err}</p> : null}

      {keys.length === 0 ? (
        <p className="text-ink-600 text-sm">No api keys yet.</p>
      ) : (
        <ul className="space-y-2" data-testid="api-keys-list">
          {keys.map((k) => (
            <li key={k.id} className="border-border rounded-md border p-3 text-sm">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div>
                  <p className="font-medium">{k.name}</p>
                  <p className="text-ink-600 text-xs">
                    engagement: {k.engagement_id ?? "tenant-wide"} · scopes: {k.scopes.join(", ")}
                  </p>
                </div>
                <div className="text-ink-600 text-xs">
                  <p>created: {formatDate(k.created_at)}</p>
                  <p>last used: {formatDate(k.last_used_at)}</p>
                  {k.revoked_at ? <p>revoked: {formatDate(k.revoked_at)}</p> : null}
                </div>
              </div>
              {!k.revoked_at ? (
                <div className="mt-2 flex justify-end">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void onRevoke(k.id)}
                  >
                    Revoke
                  </Button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      <ApiKeyMintDialog
        open={dialogOpen}
        engagements={engagements}
        onOpenChange={setDialogOpen}
        onMinted={() => {
          void load();
        }}
      />
    </section>
  );
}
