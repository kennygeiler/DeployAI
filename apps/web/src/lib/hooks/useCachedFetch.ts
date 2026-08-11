"use client";

/**
 * Wave 2.5 U6 — minimal stale-while-revalidate fetch cache.
 *
 * react-query is not a dependency of this app, so this hand-rolled hook
 * provides the slice the Brief needs: a module-level cache keyed by URL,
 * in-flight dedupe, stale-while-revalidate on re-mount, and targeted
 * invalidation so a mutation refreshes only its own section instead of the
 * old refetch-everything pattern.
 */

import * as React from "react";

import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";

type CacheEntry = {
  data: unknown;
  error: string | null;
  updatedAt: number;
  inflight: Promise<void> | null;
};

const cache = new Map<string, CacheEntry>();
const subscribers = new Map<string, Set<() => void>>();

const DEFAULT_STALE_MS = 15_000;

function notify(key: string): void {
  for (const cb of subscribers.get(key) ?? []) {
    cb();
  }
}

async function defaultFetcher(key: string): Promise<unknown> {
  const r = await fetch(key, { cache: "no-store" });
  if (!r.ok) {
    throw new Error(await readStrategistBffErrorDescription(r));
  }
  return (await r.json()) as unknown;
}

function revalidate(key: string, fetcher: (key: string) => Promise<unknown>): Promise<void> {
  const existing = cache.get(key);
  if (existing?.inflight) {
    return existing.inflight; // dedupe concurrent callers
  }
  const entry: CacheEntry = existing ?? { data: null, error: null, updatedAt: 0, inflight: null };
  cache.set(key, entry);
  entry.inflight = (async () => {
    try {
      const data = await fetcher(key);
      entry.data = data;
      entry.error = null;
    } catch (e) {
      entry.error = e instanceof Error ? e.message : "Request failed.";
    } finally {
      entry.updatedAt = Date.now();
      entry.inflight = null;
      notify(key);
    }
  })();
  return entry.inflight;
}

/**
 * Drop every cached entry whose key starts with `prefix` and refetch the
 * ones that still have mounted subscribers. Mutations call this with their
 * section's key so unrelated sections keep their cache.
 */
export function invalidateCachedFetch(prefix: string): void {
  for (const key of [...cache.keys()]) {
    if (!key.startsWith(prefix)) continue;
    if ((subscribers.get(key)?.size ?? 0) > 0) {
      const entry = cache.get(key)!;
      entry.updatedAt = 0;
      void revalidate(key, defaultFetcher);
    } else {
      cache.delete(key);
    }
  }
}

/** Test hook — reset module state between cases. */
export function clearCachedFetchForTests(): void {
  cache.clear();
  subscribers.clear();
}

export type CachedFetchResult<T> = {
  data: T | null;
  error: string | null;
  /** True until the first response (or cached value) is available. */
  pending: boolean;
  refresh: () => Promise<void>;
};

export function useCachedFetch<T>(
  key: string | null,
  opts: { staleMs?: number } = {},
): CachedFetchResult<T> {
  const staleMs = opts.staleMs ?? DEFAULT_STALE_MS;
  const [, force] = React.useReducer((n: number) => n + 1, 0);

  React.useEffect(() => {
    if (key === null) return undefined;
    let subs = subscribers.get(key);
    if (!subs) {
      subs = new Set();
      subscribers.set(key, subs);
    }
    const cb = () => force();
    subs.add(cb);

    const entry = cache.get(key);
    if (!entry || Date.now() - entry.updatedAt > staleMs) {
      void revalidate(key, defaultFetcher);
    }
    return () => {
      subs.delete(cb);
    };
  }, [key, staleMs]);

  const refresh = React.useCallback(async () => {
    if (key === null) return;
    const entry = cache.get(key);
    if (entry) entry.updatedAt = 0;
    await revalidate(key, defaultFetcher);
  }, [key]);

  if (key === null) {
    return { data: null, error: null, pending: false, refresh };
  }
  const entry = cache.get(key);
  return {
    data: (entry?.data as T | null) ?? null,
    error: entry?.error ?? null,
    pending: !entry || (entry.data === null && entry.error === null),
    refresh,
  };
}
