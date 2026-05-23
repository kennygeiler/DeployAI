"use client";

import * as React from "react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { EventSearchHit } from "@/lib/internal/event-search-cp";

type Status = "idle" | "loading" | "ready" | "error";

const DEBOUNCE_MS = 250;

function highlight(snippet: string, query: string): React.ReactNode {
  if (!query) return snippet;
  const idx = snippet.toLowerCase().indexOf(query.toLowerCase());
  if (idx < 0) return snippet;
  const before = snippet.slice(0, idx);
  const match = snippet.slice(idx, idx + query.length);
  const after = snippet.slice(idx + query.length);
  return (
    <>
      {before}
      <mark className="bg-yellow-200 px-0.5 text-inherit">{match}</mark>
      {after}
    </>
  );
}

function formatOccurredAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function EventSearch() {
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<EventSearchHit[]>([]);
  const [status, setStatus] = React.useState<Status>("idle");
  const [err, setErr] = React.useState<string | null>(null);

  const trimmed = query.trim();
  const isActive = trimmed.length >= 2;

  React.useEffect(() => {
    if (!isActive) {
      return;
    }
    let cancelled = false;
    const t = setTimeout(() => {
      if (cancelled) return;
      setStatus("loading");
      void (async () => {
        try {
          const r = await fetch(`/api/bff/search?q=${encodeURIComponent(trimmed)}`, {
            cache: "no-store",
          });
          if (cancelled) return;
          if (!r.ok) {
            setErr(`Search failed (${r.status})`);
            setStatus("error");
            return;
          }
          const body = (await r.json()) as { results?: EventSearchHit[] };
          setResults(Array.isArray(body.results) ? body.results : []);
          setErr(null);
          setStatus("ready");
        } catch (e) {
          if (!cancelled) {
            setErr(e instanceof Error ? e.message : "Search failed.");
            setStatus("error");
          }
        }
      })();
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [trimmed, isActive]);

  const visibleResults = isActive ? results : [];
  const visibleStatus: Status = isActive ? status : "idle";
  const visibleErr = isActive ? err : null;

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="event-search-q">Query</Label>
        <Input
          id="event-search-q"
          name="q"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. LiDAR, vendor, kickoff"
          autoComplete="off"
        />
        <p className="text-ink-600 text-xs">
          Matches a case-insensitive substring against every event&apos;s payload.
        </p>
      </div>

      {visibleErr ? <p className="text-error-700 text-sm">{visibleErr}</p> : null}

      {visibleStatus === "idle" && !visibleErr ? (
        <p className="text-ink-600 text-sm">
          Search every email, meeting note, and field note in your tenant.
        </p>
      ) : null}

      {visibleStatus === "loading" ? <p className="text-ink-600 text-sm">Searching…</p> : null}

      {visibleStatus === "ready" && visibleResults.length === 0 ? (
        <p className="text-ink-600 text-sm">No matches.</p>
      ) : null}

      {visibleResults.length > 0 ? (
        <ul className="divide-border divide-y rounded-md border" data-testid="event-search-results">
          {visibleResults.map((hit) => (
            <li key={hit.id} className="space-y-1 p-3">
              <div className="flex items-center gap-2 text-xs">
                <Badge variant="outline">{hit.event_type}</Badge>
                <time className="text-ink-600" dateTime={hit.occurred_at}>
                  {formatOccurredAt(hit.occurred_at)}
                </time>
                {hit.engagement_id ? (
                  <Link
                    href={`/engagements/${hit.engagement_id}`}
                    className="text-primary hover:underline"
                  >
                    Open engagement
                  </Link>
                ) : null}
              </div>
              <p className="text-ink-900 text-sm">{highlight(hit.snippet, trimmed)}</p>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
