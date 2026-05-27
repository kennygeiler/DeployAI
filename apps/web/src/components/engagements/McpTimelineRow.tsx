"use client";

import * as React from "react";

import { TimestampLabel } from "@/components/common/TimestampLabel.client";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";
import {
  isMcpConfigKind,
  isMcpKillswitchKind,
  isMcpOutboundCallKind,
} from "@/lib/internal/ledger-cp";
import { connectorBadgeClass, connectorDisplayName } from "@/lib/mcp-connectors";

/**
 * Wave 3I — custom row renderer for MCP-related ledger events in the
 * engagement timeline.
 *
 * The default timeline row shows ``occurred_at | source_kind | summary``
 * which doesn't surface the connector / tool / latency that the user
 * actually cares about when auditing outbound calls. This component
 * unpacks the redacted detail blob that Wave 2D emits and shows:
 *
 *   [Slack] tool slack.search_messages · 142ms · ok    [Outbound MCP]
 *
 * For config-change kinds (created/updated/deleted/oauth-rotated) the
 * tag becomes "Config change" and the latency drops out. For the
 * tenant-wide ``mcp_outbound_killswitch_changed`` kind we render a
 * destructive-red "Kill switch" tag plus the boolean ``disabled`` value
 * so the timeline immediately shows incident-response actions.
 *
 * Detail-shape assumptions match ``mcp_client.py`` (Wave 2D) and
 * ``tenant_mcp_*_internal.py`` (Wave 2E/2F). Missing fields fall back to
 * generic labels so a future detail-shape change doesn't crash the row.
 */

type Detail = Record<string, unknown>;

function readString(d: Detail, key: string): string | null {
  const v = d[key];
  return typeof v === "string" && v.length > 0 ? v : null;
}

function readNumber(d: Detail, key: string): number | null {
  const v = d[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function readBool(d: Detail, key: string): boolean | null {
  const v = d[key];
  return typeof v === "boolean" ? v : null;
}

const STATUS_BADGE: Record<string, string> = {
  mcp_outbound_call: "bg-emerald-100 text-emerald-900",
  mcp_outbound_blocked: "bg-amber-100 text-amber-900",
  mcp_outbound_rate_limited: "bg-amber-100 text-amber-900",
  mcp_outbound_denied: "bg-error-100 text-error-900",
};

function statusLabel(kind: string): string {
  switch (kind) {
    case "mcp_outbound_call":
      return "ok";
    case "mcp_outbound_blocked":
      return "blocked";
    case "mcp_outbound_rate_limited":
      return "rate-limited";
    case "mcp_outbound_denied":
      return "denied";
    default:
      return kind;
  }
}

const CONFIG_LABELS: Record<string, string> = {
  mcp_config_created: "created",
  mcp_config_updated: "updated",
  mcp_config_deleted: "deleted",
  mcp_oauth_token_rotated: "OAuth rotated",
};

export type McpTimelineRowProps = {
  event: Pick<LedgerEvent, "id" | "occurred_at" | "source_kind" | "summary" | "detail" | "actor_id">;
  /**
   * Optional test hook + parent-scoped row id. Same shape as the other
   * timeline rows so the existing event-jump scroll mechanism keeps
   * working when we hand off the ref.
   */
  testId?: string;
};

export function McpTimelineRow({ event, testId }: McpTimelineRowProps): React.ReactElement {
  const kind = event.source_kind;
  const detail: Detail = (event.detail ?? {}) as Detail;
  const connectorKind = readString(detail, "connector_kind") ?? readString(detail, "connector");
  const tool = readString(detail, "tool") ?? readString(detail, "tool_name");
  const latencyMs = readNumber(detail, "latency_ms");

  if (isMcpKillswitchKind(kind)) {
    const disabled = readBool(detail, "disabled");
    return (
      <div
        data-testid={testId ?? `mcp-timeline-row-${event.id}`}
        data-mcp-kind={kind}
        className="space-y-1"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <TimestampLabel value={event.occurred_at} className="text-ink-700" />
          <span className="bg-error-100 text-error-900 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase">
            Kill switch
          </span>
        </div>
        <p className="text-ink-700 text-sm">
          {disabled === null
            ? event.summary
            : disabled
              ? "Outbound MCP disabled (kill switch ON)"
              : "Outbound MCP re-enabled (kill switch OFF)"}
        </p>
        {event.actor_id ? (
          <p className="text-ink-500 font-mono text-xs">actor {event.actor_id}</p>
        ) : null}
      </div>
    );
  }

  if (isMcpConfigKind(kind)) {
    const connectorLabel = connectorKind ? connectorDisplayName(connectorKind) : null;
    const action = CONFIG_LABELS[kind] ?? kind;
    return (
      <div
        data-testid={testId ?? `mcp-timeline-row-${event.id}`}
        data-mcp-kind={kind}
        className="space-y-1"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <TimestampLabel value={event.occurred_at} className="text-ink-700" />
          <span className="bg-amber-100 text-amber-900 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase">
            Config change
          </span>
        </div>
        <p className="text-ink-700 text-sm">
          {connectorLabel ? `${connectorLabel} · ${action}` : action}
          {event.summary ? ` — ${event.summary}` : null}
        </p>
      </div>
    );
  }

  if (isMcpOutboundCallKind(kind)) {
    const status = statusLabel(kind);
    const statusClass = STATUS_BADGE[kind] ?? "bg-ink-100 text-ink-800";
    return (
      <div
        data-testid={testId ?? `mcp-timeline-row-${event.id}`}
        data-mcp-kind={kind}
        className="space-y-1"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <TimestampLabel value={event.occurred_at} className="text-ink-700" />
          <span className="bg-paper-200 text-ink-800 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase">
            Outbound MCP
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {connectorKind ? (
            <span
              data-testid={`mcp-connector-badge-${connectorKind}`}
              className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium ${connectorBadgeClass(connectorKind)}`}
            >
              {connectorDisplayName(connectorKind)}
            </span>
          ) : null}
          {tool ? (
            <span className="text-ink-800 font-mono text-xs">{tool}</span>
          ) : (
            <span className="text-ink-500 text-xs">unknown tool</span>
          )}
          <span
            className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusClass}`}
            data-testid={`mcp-status-${kind}`}
          >
            {status}
          </span>
          {latencyMs !== null ? (
            <span className="text-ink-600 text-xs" data-testid="mcp-latency">
              {Math.round(latencyMs)}ms
            </span>
          ) : null}
        </div>
        {event.summary ? <p className="text-ink-600 text-xs">{event.summary}</p> : null}
      </div>
    );
  }

  // Defensive fallback — caller should have used the default renderer.
  return (
    <div className="space-y-1">
      <TimestampLabel value={event.occurred_at} className="text-ink-700" />
      <p className="text-ink-700 text-sm">{event.summary}</p>
    </div>
  );
}
