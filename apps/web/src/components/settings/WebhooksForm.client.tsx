"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Webhook, WebhookCreateResponse, WebhookDelivery } from "@/lib/internal/webhooks-cp";

/**
 * Sprint 8 — per-tenant webhook subscriptions form.
 *
 * List existing webhooks, add a new one (server auto-generates the secret
 * which is shown ONCE on creation), edit or delete each row inline, and
 * expand a row to see its recent delivery log.
 */

const EVENT_CHOICES: readonly string[] = [
  "insight.created",
  "proposal.added",
  "extraction.completed",
];

export function WebhooksForm() {
  const [webhooks, setWebhooks] = React.useState<Webhook[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);

  const [name, setName] = React.useState("");
  const [url, setUrl] = React.useState("");
  const [selectedEvents, setSelectedEvents] = React.useState<Set<string>>(new Set());
  const [creating, setCreating] = React.useState(false);
  const [flashSecret, setFlashSecret] = React.useState<{ id: string; secret: string } | null>(null);

  const load = React.useCallback(async () => {
    const r = await fetch("/api/bff/tenant/webhooks", { method: "GET" });
    if (!r.ok) {
      setErr(`Could not load webhooks (${r.status})`);
      return;
    }
    setErr(null);
    const body = (await r.json()) as { webhooks: Webhook[] };
    setWebhooks(body.webhooks);
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        await load();
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load webhooks.");
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

  const toggleEvent = React.useCallback((event: string) => {
    setSelectedEvents((prev) => {
      const next = new Set(prev);
      if (next.has(event)) {
        next.delete(event);
      } else {
        next.add(event);
      }
      return next;
    });
  }, []);

  const onCreate = React.useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setCreating(true);
      try {
        const r = await fetch("/api/bff/tenant/webhooks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: name.trim(),
            url: url.trim(),
            events: Array.from(selectedEvents),
          }),
        });
        if (!r.ok) {
          const text = await r.text();
          toast.error("Could not create webhook", { description: text.slice(0, 240) });
          return;
        }
        const body = (await r.json()) as { webhook: WebhookCreateResponse };
        if (body.webhook.secret) {
          setFlashSecret({ id: body.webhook.id, secret: body.webhook.secret });
        }
        setName("");
        setUrl("");
        setSelectedEvents(new Set());
        await load();
        toast.success("Webhook created");
      } finally {
        setCreating(false);
      }
    },
    [name, url, selectedEvents, load],
  );

  const onDelete = React.useCallback(
    async (id: string) => {
      const r = await fetch(`/api/bff/tenant/webhooks/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      if (!r.ok && r.status !== 204) {
        toast.error("Could not delete webhook");
        return;
      }
      await load();
      toast.success("Webhook deleted");
    },
    [load],
  );

  if (loading) {
    return <p className="text-ink-600 text-sm">Loading…</p>;
  }

  return (
    <section aria-labelledby="webhooks-heading" className="max-w-3xl space-y-6">
      <div>
        <h2 id="webhooks-heading" className="text-base font-semibold">
          Webhooks
        </h2>
        <p className="text-ink-600 mt-1 text-sm">
          Receive signed POST payloads for tenant events. Signed with HMAC-SHA256 using a
          per-webhook secret in the <code>X-DeployAI-Signature</code> header.
        </p>
      </div>

      {err ? <p className="text-error-700 text-sm">{err}</p> : null}

      <form onSubmit={onCreate} className="border-border space-y-4 rounded-md border p-4">
        <h3 className="text-sm font-semibold">Add webhook</h3>
        <div className="space-y-2">
          <Label htmlFor="wh-name">Name</Label>
          <Input
            id="wh-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="ops slack"
            autoComplete="off"
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="wh-url">URL</Label>
          <Input
            id="wh-url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/hook"
            autoComplete="off"
            required
          />
          <p className="text-ink-600 text-xs">Must be https (or http://localhost* for dev).</p>
        </div>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Events</legend>
          {EVENT_CHOICES.map((ev) => (
            <label key={ev} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={selectedEvents.has(ev)}
                onChange={() => toggleEvent(ev)}
              />
              <span>{ev}</span>
            </label>
          ))}
        </fieldset>
        <Button type="submit" disabled={creating}>
          {creating ? "Creating…" : "Create webhook"}
        </Button>
      </form>

      {flashSecret ? (
        <div className="border-accent bg-accent/10 rounded-md border p-3 text-sm">
          <p className="font-semibold">Webhook secret (shown once)</p>
          <p className="text-ink-600 mt-1 text-xs">
            Copy this now — you will not be able to see it again.
          </p>
          <code className="bg-bg-subtle mt-2 block break-all rounded px-2 py-1 text-xs">
            {flashSecret.secret}
          </code>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="mt-2"
            onClick={() => setFlashSecret(null)}
          >
            Dismiss
          </Button>
        </div>
      ) : null}

      <div className="space-y-3">
        <h3 className="text-sm font-semibold">Existing webhooks</h3>
        {webhooks.length === 0 ? (
          <p className="text-ink-600 text-sm">No webhooks yet.</p>
        ) : (
          <ul className="space-y-3">
            {webhooks.map((w) => (
              <WebhookRow key={w.id} webhook={w} onDelete={() => onDelete(w.id)} onChanged={load} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function WebhookRow({
  webhook,
  onDelete,
  onChanged,
}: {
  webhook: Webhook;
  onDelete: () => void | Promise<void>;
  onChanged: () => void | Promise<void>;
}) {
  const [editing, setEditing] = React.useState(false);
  const [name, setName] = React.useState(webhook.name);
  const [url, setUrl] = React.useState(webhook.url);
  const [active, setActive] = React.useState(webhook.active);
  const [events, setEvents] = React.useState<Set<string>>(new Set(webhook.events));
  const [saving, setSaving] = React.useState(false);

  const [showDeliveries, setShowDeliveries] = React.useState(false);
  const [deliveries, setDeliveries] = React.useState<WebhookDelivery[] | null>(null);
  const [deliveriesLoading, setDeliveriesLoading] = React.useState(false);

  const toggleEvent = (ev: string) => {
    setEvents((prev) => {
      const next = new Set(prev);
      if (next.has(ev)) next.delete(ev);
      else next.add(ev);
      return next;
    });
  };

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const r = await fetch(`/api/bff/tenant/webhooks/${encodeURIComponent(webhook.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          url,
          active,
          events: Array.from(events),
        }),
      });
      if (!r.ok) {
        toast.error("Could not update webhook");
        return;
      }
      setEditing(false);
      await onChanged();
      toast.success("Webhook updated");
    } finally {
      setSaving(false);
    }
  };

  const loadDeliveries = React.useCallback(async () => {
    setDeliveriesLoading(true);
    try {
      const r = await fetch(
        `/api/bff/tenant/webhooks/${encodeURIComponent(webhook.id)}/deliveries?limit=50`,
      );
      if (!r.ok) {
        toast.error("Could not load deliveries");
        return;
      }
      const body = (await r.json()) as { deliveries: WebhookDelivery[] };
      setDeliveries(body.deliveries);
    } finally {
      setDeliveriesLoading(false);
    }
  }, [webhook.id]);

  const toggleDeliveries = async () => {
    const next = !showDeliveries;
    setShowDeliveries(next);
    if (next && deliveries === null) {
      await loadDeliveries();
    }
  };

  return (
    <li className="border-border rounded-md border p-3">
      {editing ? (
        <form onSubmit={onSave} className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor={`name-${webhook.id}`}>Name</Label>
            <Input
              id={`name-${webhook.id}`}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`url-${webhook.id}`}>URL</Label>
            <Input id={`url-${webhook.id}`} value={url} onChange={(e) => setUrl(e.target.value)} />
          </div>
          <fieldset className="space-y-1">
            <legend className="text-xs font-medium">Events</legend>
            {EVENT_CHOICES.map((ev) => (
              <label key={ev} className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={events.has(ev)} onChange={() => toggleEvent(ev)} />
                <span>{ev}</span>
              </label>
            ))}
          </fieldset>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
            <span>Active</span>
          </label>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setEditing(false);
                setName(webhook.name);
                setUrl(webhook.url);
                setActive(webhook.active);
                setEvents(new Set(webhook.events));
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div>
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold">
                {webhook.name}
                {!webhook.active ? (
                  <span className="text-ink-600 ml-2 text-xs">(inactive)</span>
                ) : null}
              </p>
              <p className="text-ink-600 text-xs break-all">{webhook.url}</p>
              <p className="text-ink-600 mt-1 text-xs">
                Events: {webhook.events.length === 0 ? "(none)" : webhook.events.join(", ")}
              </p>
              <p className="text-ink-600 text-xs">Secret: {webhook.secret_masked ?? "(none)"}</p>
            </div>
            <div className="flex flex-shrink-0 gap-2">
              <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(true)}>
                Edit
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => void onDelete()}>
                Delete
              </Button>
            </div>
          </div>
          <div className="mt-2">
            <Button type="button" size="sm" variant="ghost" onClick={() => void toggleDeliveries()}>
              {showDeliveries ? "Hide deliveries" : "Show recent deliveries"}
            </Button>
            {showDeliveries ? (
              <div className="mt-2">
                {deliveriesLoading ? (
                  <p className="text-ink-600 text-xs">Loading…</p>
                ) : !deliveries || deliveries.length === 0 ? (
                  <p className="text-ink-600 text-xs">No deliveries yet.</p>
                ) : (
                  <ul className="space-y-1 text-xs">
                    {deliveries.map((d) => (
                      <li key={d.id} className="border-border border-l-2 pl-2">
                        <span className="font-mono">{d.status}</span> · <span>{d.event_name}</span>
                        {d.response_status !== null ? (
                          <span> · HTTP {d.response_status}</span>
                        ) : null}
                        {" · "}
                        <span className="text-ink-600">{d.attempts} attempt(s)</span>
                        {d.error ? <div className="text-error-700 break-all">{d.error}</div> : null}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : null}
          </div>
        </div>
      )}
    </li>
  );
}
