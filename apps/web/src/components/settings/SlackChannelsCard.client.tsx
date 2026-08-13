"use client";

import * as React from "react";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Engagement } from "@/lib/bff/engagement-types";
import {
  type SlackChannelMapping,
  type SlackPendingChannel,
  zSlackChannelMapping,
  zSlackPendingChannel,
} from "@/lib/internal/slack-intake-cp";

/**
 * Wave 5 SL1 — Slack channel intake settings.
 *
 * The consent model: inviting the DeployAI bot to a channel is the
 * consent boundary; messages are only stored once the channel is mapped
 * to an engagement here. Bot-invited-but-unmapped channels appear as
 * "pending" (channel id + name only — no content is stored for them),
 * with a map-to-engagement picker. Revoking a mapping stops intake and
 * discards anything not yet folded into canonical memory.
 */

const zListResponse = z.object({
  mappings: z.array(zSlackChannelMapping),
  pending: z.array(zSlackPendingChannel),
});

const zEngagementsResponse = z.object({
  engagements: z.array(z.object({ id: z.string(), name: z.string() }).loose()),
});

const SELECT_CLS =
  "border-border focus-visible:ring-ring h-9 w-full rounded-md border px-3 text-sm focus-visible:outline-none focus-visible:ring-2";

export function SlackChannelsCard() {
  const [mappings, setMappings] = React.useState<SlackChannelMapping[]>([]);
  const [pending, setPending] = React.useState<SlackPendingChannel[]>([]);
  const [engagements, setEngagements] = React.useState<Pick<Engagement, "id" | "name">[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  // Per-pending-channel engagement selection.
  const [picks, setPicks] = React.useState<Record<string, string>>({});
  // Manual add — for channels whose invite predates the pending tracking.
  const [manualChannel, setManualChannel] = React.useState("");
  const [manualEngagement, setManualEngagement] = React.useState("");

  const load = React.useCallback(async () => {
    const [r, re] = await Promise.all([
      fetch("/api/bff/tenant/slack-channels", { method: "GET" }),
      fetch("/api/bff/engagements", { method: "GET" }),
    ]);
    if (!r.ok) {
      setErr(`Could not load Slack channels (${r.status})`);
      return;
    }
    const parsed = zListResponse.safeParse(await r.json());
    if (!parsed.success) {
      setErr("Could not parse server response.");
      return;
    }
    setErr(null);
    setMappings(parsed.data.mappings);
    setPending(parsed.data.pending);
    if (re.ok) {
      const pe = zEngagementsResponse.safeParse(await re.json());
      if (pe.success) {
        setEngagements(pe.data.engagements);
      }
    }
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        await load();
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load Slack channels.");
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

  const engagementName = React.useCallback(
    (id: string) => engagements.find((e) => e.id === id)?.name ?? id,
    [engagements],
  );

  const mapChannel = React.useCallback(
    async (channelId: string, channelName: string, engagementId: string) => {
      if (!engagementId) {
        toast.error("Pick an engagement first.");
        return;
      }
      setBusy(true);
      try {
        const r = await fetch("/api/bff/tenant/slack-channels", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            channel_id: channelId,
            channel_name: channelName,
            engagement_id: engagementId,
          }),
        });
        if (!r.ok) {
          const text = await r.text();
          toast.error("Could not map channel", { description: text.slice(0, 240) });
          return;
        }
        toast.success(`Mapped ${channelName || channelId} — messages will now be ingested.`);
        await load();
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  const revoke = React.useCallback(
    async (m: SlackChannelMapping) => {
      setBusy(true);
      try {
        const r = await fetch(`/api/bff/tenant/slack-channels/${encodeURIComponent(m.id)}/revoke`, {
          method: "POST",
        });
        if (!r.ok) {
          const text = await r.text();
          toast.error("Could not revoke mapping", { description: text.slice(0, 240) });
          return;
        }
        toast.success(
          `Revoked ${m.channel_name || m.channel_id} — un-ingested messages were discarded.`,
        );
        await load();
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  return (
    <section aria-labelledby="slack-channels-heading" className="space-y-4">
      <div>
        <h2 id="slack-channels-heading" className="text-base font-semibold">
          Slack channel intake
        </h2>
        <p className="text-ink-600 mt-1 text-sm">
          Inviting the DeployAI bot to a channel is the consent boundary: nothing is stored until
          you map the channel to an engagement here. Mapped channels&apos; messages are batched into
          per-day / per-thread snapshots and run through extraction; unmapped channels are counted
          and dropped. Revoking stops intake and discards anything not yet ingested.
        </p>
      </div>

      {err ? <p className="text-red-ink text-sm">{err}</p> : null}
      {loading ? <p className="text-ink-600 text-sm">Loading…</p> : null}

      {!loading && pending.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">Pending channels (bot invited, not mapped)</h3>
          <ul className="divide-border divide-y rounded-md border">
            {pending.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-2 p-3">
                <span className="min-w-40 text-sm font-medium">
                  #{p.channel_name || p.channel_id}
                </span>
                <select
                  aria-label={`Engagement for ${p.channel_name || p.channel_id}`}
                  value={picks[p.channel_id] ?? ""}
                  onChange={(e) => setPicks((s) => ({ ...s, [p.channel_id]: e.target.value }))}
                  className={`${SELECT_CLS} max-w-64 flex-1`}
                >
                  <option value="">Pick an engagement…</option>
                  {engagements.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.name}
                    </option>
                  ))}
                </select>
                <Button
                  type="button"
                  size="sm"
                  disabled={busy || !picks[p.channel_id]}
                  onClick={() =>
                    void mapChannel(p.channel_id, p.channel_name, picks[p.channel_id] ?? "")
                  }
                >
                  Map channel
                </Button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {!loading ? (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">Mapped channels</h3>
          {mappings.length === 0 ? (
            <p className="text-ink-600 text-sm">
              No channels are mapped yet. Invite the bot to a channel, then map it here.
            </p>
          ) : (
            <ul className="divide-border divide-y rounded-md border">
              {mappings.map((m) => (
                <li key={m.id} className="flex flex-wrap items-center gap-2 p-3">
                  <span className="min-w-40 text-sm font-medium">
                    #{m.channel_name || m.channel_id}
                  </span>
                  <span className="text-ink-600 flex-1 text-sm">
                    → {engagementName(m.engagement_id)}
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => void revoke(m)}
                  >
                    Revoke
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}

      {!loading ? (
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            void mapChannel(manualChannel.trim(), "", manualEngagement).then(() => {
              setManualChannel("");
            });
          }}
        >
          <h3 className="text-sm font-medium">Map a channel by ID</h3>
          <p className="text-ink-600 text-sm">
            For channels the bot already joined before pending tracking. Find the ID in Slack:
            channel details → “Channel ID”.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <Label htmlFor="slack-manual-channel">Channel ID</Label>
              <Input
                id="slack-manual-channel"
                value={manualChannel}
                onChange={(e) => setManualChannel(e.target.value)}
                placeholder="C0123456789"
                className="w-48"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="slack-manual-engagement">Engagement</Label>
              <select
                id="slack-manual-engagement"
                value={manualEngagement}
                onChange={(e) => setManualEngagement(e.target.value)}
                className={`${SELECT_CLS} w-64`}
              >
                <option value="">Pick an engagement…</option>
                {engagements.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                  </option>
                ))}
              </select>
            </div>
            <Button
              type="submit"
              size="sm"
              disabled={busy || !manualChannel.trim() || !manualEngagement}
            >
              Map channel
            </Button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
