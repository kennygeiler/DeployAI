"use client";

import * as React from "react";
import { z } from "zod";

import { TimestampLabel } from "@/components/common/TimestampLabel.client";
import { Button } from "@/components/ui/button";
import {
  isMcpConfigKind,
  isMcpKillswitchKind,
  isMcpOutboundCallKind,
} from "@/lib/internal/ledger-cp";
import { McpAuditRowSchema, type McpAuditRow } from "@/lib/internal/mcp-audit-cp";
import { connectorBadgeClass, connectorDisplayName } from "@/lib/mcp-connectors";

const ResponseSchema = z.object({ rows: z.array(McpAuditRowSchema) });

type Detail = Record<string, unknown>;

function readString(d: Detail, key: string): string | null {
  const v = d[key];
  return typeof v === "string" && v.length > 0 ? v : null;
}

function readNumber(d: Detail, key: string): number | null {
  const v = d[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function deriveStatus(kind: string, detail: Detail): { label: string; cls: string } {
  if (kind === "mcp_outbound_call") {
    const httpStatus = readNumber(detail, "http_status") ?? readNumber(detail, "status_code");
    if (httpStatus !== null && httpStatus >= 400) {
      return { label: `http ${httpStatus}`, cls: "bg-red-tint text-red-ink" };
    }
    return { label: "ok", cls: "bg-green-tint text-green-ink" };
  }
  if (kind === "mcp_outbound_blocked")
    return { label: "blocked", cls: "bg-orange-tint text-orange-ink" };
  if (kind === "mcp_outbound_rate_limited")
    return { label: "rate-limited", cls: "bg-orange-tint text-orange-ink" };
  if (kind === "mcp_outbound_denied") return { label: "denied", cls: "bg-red-tint text-red-ink" };
  if (kind === "mcp_outbound_killswitch_changed")
    return { label: "kill switch", cls: "bg-red-tint text-red-ink" };
  if (isMcpConfigKind(kind))
    return { label: "config change", cls: "bg-orange-tint text-orange-ink" };
  return { label: kind, cls: "bg-ink-100 text-ink-800" };
}

export function McpActivityTable() {
  const [rows, setRows] = React.useState<McpAuditRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/bff/tenant/mcp-activity?limit=50", { cache: "no-store" });
      if (!r.ok) {
        setErr(`Could not load MCP activity (${r.status})`);
        setRows([]);
        return;
      }
      const parsed = ResponseSchema.safeParse(await r.json());
      if (!parsed.success) {
        setErr("Could not parse MCP activity response");
        setRows([]);
        return;
      }
      setErr(null);
      setRows(parsed.data.rows);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load MCP activity.");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      // The load() body sets loading + rows itself; wrapping in an IIFE
      // keeps React's "no setState directly in effect body" lint happy
      // and lets us no-op state updates after unmount.
      try {
        await load();
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load MCP activity.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  return (
    <section
      aria-labelledby="mcp-activity-heading"
      className="space-y-4"
      data-testid="mcp-activity-panel"
    >
      <div className="flex items-center justify-between">
        <h2 id="mcp-activity-heading" className="text-base font-semibold">
          Recent MCP activity
        </h2>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => void load()}
          disabled={loading}
          data-testid="mcp-activity-refresh"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      {err ? (
        <p role="alert" className="text-sm text-red-ink">
          {err}
        </p>
      ) : null}

      {loading && rows.length === 0 ? (
        <p className="text-ink-600 text-sm">Loading…</p>
      ) : rows.length === 0 && !err ? (
        <p
          className="rounded-card bg-surface px-3 py-6 text-center text-sm text-ink-600 shadow-card"
          data-testid="mcp-activity-empty"
        >
          No outbound MCP activity yet.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-card bg-surface shadow-card">
          <table className="w-full text-sm">
            <thead className="border-b border-line text-xs text-ink-600 uppercase">
              <tr>
                <th scope="col" className="px-3 py-2 text-left">
                  When
                </th>
                <th scope="col" className="px-3 py-2 text-left">
                  Connector
                </th>
                <th scope="col" className="px-3 py-2 text-left">
                  Tool
                </th>
                <th scope="col" className="px-3 py-2 text-left">
                  Status
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  Latency
                </th>
                <th scope="col" className="px-3 py-2 text-left">
                  Actor
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((row) => {
                const detail = row.detail as Detail;
                const connector =
                  readString(detail, "connector_kind") ?? readString(detail, "connector");
                const tool = readString(detail, "tool") ?? readString(detail, "tool_name");
                const latency = readNumber(detail, "latency_ms");
                const status = deriveStatus(row.source_kind, detail);
                const isCall = isMcpOutboundCallKind(row.source_kind);
                const isKill = isMcpKillswitchKind(row.source_kind);
                return (
                  <tr
                    key={row.id}
                    data-testid={`mcp-activity-row-${row.id}`}
                    data-source-kind={row.source_kind}
                    className="align-top"
                  >
                    <td className="px-3 py-2 whitespace-nowrap">
                      <TimestampLabel value={row.occurred_at} className="text-ink-700" />
                    </td>
                    <td className="px-3 py-2">
                      {connector ? (
                        <span
                          className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium ${connectorBadgeClass(connector)}`}
                          data-testid={`mcp-activity-connector-${connector}`}
                        >
                          {connectorDisplayName(connector)}
                        </span>
                      ) : (
                        <span className="text-ink-500 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {tool ? (
                        <span className="text-ink-800 font-mono text-xs">{tool}</span>
                      ) : (
                        <span className="text-ink-500 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${status.cls}`}
                      >
                        {status.label}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      {isCall && latency !== null ? (
                        <span className="text-ink-700 font-mono text-xs">
                          {Math.round(latency)}ms
                        </span>
                      ) : (
                        <span className="text-ink-500 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {row.actor_id ? row.actor_id : isKill ? "kill switch" : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
