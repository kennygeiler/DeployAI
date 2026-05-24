"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type AuditEventDTO = {
  id: string;
  tenant_id: string;
  actor_id: string;
  category: string;
  summary: string;
  detail: Record<string, unknown>;
  ref_id: string | null;
  created_at: string;
};

type ListResponse = { events: AuditEventDTO[] };

const DEFAULT_LIMIT = 50;

function buildQs(opts: { limit: number; actor?: string; kind?: string; before?: string }): string {
  const qs = new URLSearchParams();
  qs.set("limit", String(opts.limit));
  if (opts.actor) qs.set("actor", opts.actor);
  if (opts.kind) qs.set("kind", opts.kind);
  if (opts.before) qs.set("before", opts.before);
  return qs.toString();
}

export function AuditLogList() {
  const [events, setEvents] = React.useState<AuditEventDTO[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  const [actor, setActor] = React.useState("");
  const [kind, setKind] = React.useState("");
  const [limit, setLimit] = React.useState(DEFAULT_LIMIT);
  const [exhausted, setExhausted] = React.useState(false);

  const filters = React.useMemo(
    () => ({ actor: actor.trim(), kind: kind.trim(), limit }),
    [actor, kind, limit],
  );

  const load = React.useCallback(async () => {
    const qs = buildQs({
      limit: filters.limit,
      ...(filters.actor ? { actor: filters.actor } : {}),
      ...(filters.kind ? { kind: filters.kind } : {}),
    });
    const r = await fetch(`/api/bff/tenant/audit?${qs}`, { method: "GET" });
    if (!r.ok) {
      setErr(`Could not load audit events (${r.status})`);
      return;
    }
    setErr(null);
    const body = (await r.json()) as ListResponse;
    setEvents(body.events);
    setExhausted(body.events.length < filters.limit);
  }, [filters]);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        await load();
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load audit events.");
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

  const onLoadOlder = React.useCallback(async () => {
    if (events.length === 0) return;
    const cursor = events[events.length - 1]!.created_at;
    setLoadingMore(true);
    try {
      const qs = buildQs({
        limit: filters.limit,
        before: cursor,
        ...(filters.actor ? { actor: filters.actor } : {}),
        ...(filters.kind ? { kind: filters.kind } : {}),
      });
      const r = await fetch(`/api/bff/tenant/audit?${qs}`, { method: "GET" });
      if (!r.ok) {
        setErr(`Could not load older events (${r.status})`);
        return;
      }
      setErr(null);
      const body = (await r.json()) as ListResponse;
      setEvents((prev) => [...prev, ...body.events]);
      setExhausted(body.events.length < filters.limit);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load older events.");
    } finally {
      setLoadingMore(false);
    }
  }, [events, filters]);

  return (
    <section aria-labelledby="audit-log-heading" className="space-y-6">
      <div>
        <h2 id="audit-log-heading" className="text-base font-semibold">
          Activity events
        </h2>
        <p className="text-ink-600 mt-1 text-sm">
          Most recent events first. Filters apply when you tab out of the input.
        </p>
      </div>

      <form className="grid grid-cols-1 gap-3 sm:grid-cols-3" onSubmit={(e) => e.preventDefault()}>
        <div className="space-y-2">
          <Label htmlFor="audit-actor">Actor (UUID)</Label>
          <Input
            id="audit-actor"
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            placeholder="any"
            autoComplete="off"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="audit-kind">Kind</Label>
          <Input
            id="audit-kind"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            placeholder="any"
            autoComplete="off"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="audit-limit">Page size</Label>
          <Input
            id="audit-limit"
            type="number"
            min={1}
            max={500}
            value={limit}
            onChange={(e) => {
              const n = Number.parseInt(e.target.value, 10);
              if (Number.isFinite(n) && n >= 1 && n <= 500) setLimit(n);
            }}
          />
        </div>
      </form>

      {err ? <p className="text-error-700 text-sm">{err}</p> : null}

      {loading ? (
        <p className="text-ink-600 text-sm">Loading…</p>
      ) : events.length === 0 ? (
        <p className="text-ink-600 text-sm">No activity events match these filters.</p>
      ) : (
        <div className="border-border overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-surface-subtle text-ink-700 text-xs uppercase">
              <tr>
                <th scope="col" className="px-3 py-2 text-left">
                  When
                </th>
                <th scope="col" className="px-3 py-2 text-left">
                  Kind
                </th>
                <th scope="col" className="px-3 py-2 text-left">
                  Actor
                </th>
                <th scope="col" className="px-3 py-2 text-left">
                  Summary
                </th>
              </tr>
            </thead>
            <tbody className="divide-border divide-y">
              {events.map((ev) => (
                <tr key={ev.id} className="align-top">
                  <td className="px-3 py-2 font-mono text-xs whitespace-nowrap">{ev.created_at}</td>
                  <td className="px-3 py-2 font-mono text-xs">{ev.category}</td>
                  <td className="px-3 py-2 font-mono text-xs">{ev.actor_id}</td>
                  <td className="px-3 py-2">{ev.summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => void onLoadOlder()}
          disabled={loading || loadingMore || exhausted || events.length === 0}
        >
          {loadingMore ? "Loading…" : exhausted ? "No older events" : "Load older"}
        </Button>
      </div>
    </section>
  );
}
