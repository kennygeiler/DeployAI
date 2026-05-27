"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  CONNECTOR_KINDS,
  type ConnectorKind,
  type KillSwitchState,
  type TenantMcpConfigRead,
} from "@/lib/internal/mcp-configs-cp";

/**
 * v2 Phase 5 Wave 3H — outbound-MCP integrations admin UI.
 *
 * Header section: big kill-switch toggle. When ON, Agent Kenny refuses
 * every external MCP call for this tenant (threat-model §5.5 Option B).
 * Confirmation modal guards the OFF -> ON transition because flipping it
 * mid-conversation aborts any in-flight outbound work.
 *
 * Connector catalog: read-only list of the 5 supported kinds. Pure
 * reference — `<select>` in the add/edit modal picks from the same set.
 *
 * Configs table: one row per `tenant_mcp_configs` row. Per-row actions:
 * edit, delete, connect-with-slack (slack-only when `!has_auth_token`).
 *
 * Slack OAuth flow (kept deliberately simple):
 *   1. Click "Connect with Slack" -> POST oauth/start, opens
 *      authorization_url in a new tab, surfaces a paste form for
 *      `code` + `state`.
 *   2. User completes auth in Slack -> Slack redirects to redirect_uri,
 *      surfacing code + state.
 *   3. User copies code + state into the paste form -> POST oauth/callback
 *      -> CP exchanges + encrypts + persists.
 * Why paste-mode rather than popup listener: redirect_uri lives in CP
 * settings (Wave 3J pipes the real env); the BFF doesn't host the
 * callback page yet, so the user owns the bounce. Simple, no postMessage
 * plumbing, no race conditions. Replace with popup listener in 3J.
 */

const CONNECTOR_LABELS: Record<ConnectorKind, string> = {
  slack: "Slack",
  linear: "Linear",
  gdrive: "Google Drive",
  notion: "Notion",
  github: "GitHub",
};

const CONNECTOR_DESCRIPTIONS: Record<ConnectorKind, string> = {
  slack: "Search messages, post replies, resolve users + channels.",
  linear: "List issues, projects, cycles. Read-only in v1.",
  gdrive: "List + read docs Kenny needs as evidence. Read-only.",
  notion: "Search pages + databases. Read-only.",
  github: "Search PRs, issues, commit messages. Read-only.",
};

export type IntegrationsClientProps = {
  tenantId: string;
  initialConfigs: TenantMcpConfigRead[];
  initialKillSwitch: KillSwitchState;
  initialLoadError?: string | null;
};

function urlOk(value: string): boolean {
  try {
    const u = new URL(value);
    return u.protocol === "https:";
  } catch {
    return false;
  }
}

export function IntegrationsClient({
  tenantId,
  initialConfigs,
  initialKillSwitch,
  initialLoadError,
}: IntegrationsClientProps) {
  const [configs, setConfigs] = React.useState<TenantMcpConfigRead[]>(initialConfigs);
  const [killSwitch, setKillSwitch] = React.useState<KillSwitchState>(initialKillSwitch);
  const [loadError, setLoadError] = React.useState<string | null>(initialLoadError ?? null);

  const [editing, setEditing] = React.useState<TenantMcpConfigRead | null>(null);
  const [addOpen, setAddOpen] = React.useState(false);
  const [pendingDelete, setPendingDelete] = React.useState<TenantMcpConfigRead | null>(null);
  const [killConfirmOpen, setKillConfirmOpen] = React.useState(false);
  const [oauthFor, setOauthFor] = React.useState<TenantMcpConfigRead | null>(null);

  const refresh = React.useCallback(async () => {
    if (!tenantId) return;
    try {
      const r = await fetch(`/api/internal/v1/tenants/${encodeURIComponent(tenantId)}/mcp_configs`);
      if (!r.ok) {
        setLoadError(`Could not reload integrations (${r.status})`);
        return;
      }
      const body = (await r.json()) as { configs: TenantMcpConfigRead[] };
      setConfigs(body.configs);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Could not reload integrations.");
    }
  }, [tenantId]);

  const onKillSwitchToggle = React.useCallback(
    async (next: boolean) => {
      if (!tenantId) return;
      const r = await fetch(
        `/api/internal/v1/tenants/${encodeURIComponent(tenantId)}/mcp_killswitch`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ disabled: next }),
        },
      );
      if (!r.ok) {
        toast.error("Could not change kill switch");
        return;
      }
      const body = (await r.json()) as KillSwitchState;
      setKillSwitch(body);
      toast.success(
        body.disabled
          ? "Outbound MCP DISABLED for this tenant"
          : "Outbound MCP re-enabled for this tenant",
      );
    },
    [tenantId],
  );

  const onDeleteConfirm = React.useCallback(async () => {
    if (!pendingDelete || !tenantId) return;
    const r = await fetch(
      `/api/internal/v1/tenants/${encodeURIComponent(tenantId)}/mcp_configs/${encodeURIComponent(pendingDelete.id)}`,
      { method: "DELETE" },
    );
    if (!r.ok) {
      toast.error(`Could not delete integration (${r.status})`);
      return;
    }
    setPendingDelete(null);
    toast.success("Integration deleted");
    await refresh();
  }, [pendingDelete, tenantId, refresh]);

  return (
    <div className="space-y-8" data-testid="integrations-client">
      <KillSwitchPanel
        state={killSwitch}
        onRequestEnable={() => setKillConfirmOpen(true)}
        onDisable={() => void onKillSwitchToggle(false)}
      />

      <CatalogSection />

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold">Configured integrations</h2>
          <Button type="button" onClick={() => setAddOpen(true)}>
            Add integration
          </Button>
        </div>
        {loadError ? <p className="text-error-700 text-sm">{loadError}</p> : null}
        {configs.length === 0 ? (
          <p className="text-ink-600 text-sm" data-testid="configs-empty">
            No integrations configured yet. Click <em>Add integration</em> to wire one up.
          </p>
        ) : (
          <table className="w-full text-sm" data-testid="configs-table">
            <thead className="text-ink-600 text-xs uppercase">
              <tr className="border-border border-b">
                <th className="py-2 text-left font-medium">Name</th>
                <th className="py-2 text-left font-medium">Kind</th>
                <th className="py-2 text-left font-medium">Endpoint</th>
                <th className="py-2 text-left font-medium">Enabled</th>
                <th className="py-2 text-left font-medium">Auth</th>
                <th className="py-2 text-left font-medium">Tools</th>
                <th className="py-2 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {configs.map((c) => (
                <tr
                  key={c.id}
                  className="border-border border-b align-top"
                  data-testid={`config-row-${c.id}`}
                >
                  <td className="py-2 font-medium">{c.name}</td>
                  <td className="py-2">{CONNECTOR_LABELS[c.connector_kind]}</td>
                  <td className="py-2 text-xs break-all">{c.endpoint}</td>
                  <td className="py-2">{c.enabled ? "yes" : "no"}</td>
                  <td className="py-2" data-testid={`config-row-${c.id}-auth`}>
                    {c.has_auth_token ? "token set" : "missing"}
                  </td>
                  <td className="py-2">
                    {c.allowed_tools === null ? "all" : `${c.allowed_tools.length} allow-listed`}
                  </td>
                  <td className="py-2 text-right">
                    <div className="flex justify-end gap-2">
                      <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(c)}>
                        Edit
                      </Button>
                      {c.connector_kind === "slack" && !c.has_auth_token ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => setOauthFor(c)}
                          data-testid={`connect-slack-${c.id}`}
                        >
                          Connect with Slack
                        </Button>
                      ) : null}
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => setPendingDelete(c)}
                      >
                        Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Keying the dialog by the target id (or "new") remounts it whenever the
          target changes, so the form's `useState` initializers re-run from the
          fresh `existing` prop — avoids the `setState in useEffect` lint and
          matches the React 19 idiom for "derive on mount, reset by key". */}
      <ConfigDialog
        key={editing ? `edit-${editing.id}` : addOpen ? "new" : "closed"}
        open={addOpen || editing !== null}
        tenantId={tenantId}
        existing={editing}
        onOpenChange={(o) => {
          if (!o) {
            setAddOpen(false);
            setEditing(null);
          }
        }}
        onSaved={() => {
          setAddOpen(false);
          setEditing(null);
          void refresh();
        }}
      />

      <DeleteDialog
        config={pendingDelete}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => void onDeleteConfirm()}
      />

      <KillSwitchConfirmDialog
        open={killConfirmOpen}
        onCancel={() => setKillConfirmOpen(false)}
        onConfirm={() => {
          setKillConfirmOpen(false);
          void onKillSwitchToggle(true);
        }}
      />

      <SlackOAuthDialog
        key={oauthFor ? `oauth-${oauthFor.id}` : "oauth-closed"}
        config={oauthFor}
        tenantId={tenantId}
        onClose={() => setOauthFor(null)}
        onConnected={() => {
          setOauthFor(null);
          void refresh();
        }}
      />
    </div>
  );
}

function KillSwitchPanel({
  state,
  onRequestEnable,
  onDisable,
}: {
  state: KillSwitchState;
  onRequestEnable: () => void;
  onDisable: () => void;
}) {
  const isOn = state.disabled;
  return (
    <section
      className={
        "rounded-md border p-4 " +
        (isOn ? "border-error-500 bg-error-50" : "border-border bg-bg-subtle")
      }
      data-testid="killswitch-panel"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">
            Outbound MCP killed: <span data-testid="killswitch-state">{isOn ? "ON" : "OFF"}</span>
          </h2>
          {isOn ? (
            <p className="text-error-700 mt-1 text-sm" data-testid="killswitch-warning">
              Agent Kenny cannot call any external MCP server while this is on. All in-flight calls
              return <code>McpOutboundDisabled</code>.
            </p>
          ) : (
            <p className="text-ink-600 mt-1 text-sm">
              Flip ON for incident response. Per-connector toggles stay intact and resume when you
              flip OFF.
            </p>
          )}
        </div>
        {isOn ? (
          <Button type="button" variant="outline" onClick={onDisable} data-testid="killswitch-off">
            Turn OFF
          </Button>
        ) : (
          <Button
            type="button"
            variant="outline"
            onClick={onRequestEnable}
            data-testid="killswitch-on"
          >
            Kill all outbound MCP
          </Button>
        )}
      </div>
    </section>
  );
}

function CatalogSection() {
  return (
    <section className="space-y-2" data-testid="connector-catalog">
      <h2 className="text-base font-semibold">Supported connectors</h2>
      <ul className="border-border divide-border divide-y rounded-md border">
        {CONNECTOR_KINDS.map((k) => (
          <li key={k} className="flex items-start justify-between gap-3 px-3 py-2">
            <div>
              <p className="text-sm font-medium">{CONNECTOR_LABELS[k]}</p>
              <p className="text-ink-600 text-xs">{CONNECTOR_DESCRIPTIONS[k]}</p>
            </div>
            <code className="text-ink-600 text-xs">{k}</code>
          </li>
        ))}
      </ul>
    </section>
  );
}

function KillSwitchConfirmDialog({
  open,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onCancel();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Kill all outbound MCP traffic?</DialogTitle>
          <DialogDescription>
            Agent Kenny will refuse every external MCP call for this tenant until you turn the
            switch OFF. In-flight calls will fail with <code>McpOutboundDisabled</code>. Per-config
            toggles are preserved.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
          </DialogClose>
          <Button type="button" onClick={onConfirm} data-testid="killswitch-confirm">
            Kill outbound MCP
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeleteDialog({
  config,
  onCancel,
  onConfirm,
}: {
  config: TenantMcpConfigRead | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog
      open={config !== null}
      onOpenChange={(o) => {
        if (!o) onCancel();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete integration?</DialogTitle>
          <DialogDescription>
            {config ? (
              <>
                The <strong>{config.name}</strong> ({CONNECTOR_LABELS[config.connector_kind]})
                integration will be removed. Any encrypted OAuth token is dropped from disk; revoke
                the underlying token in the upstream workspace if you want to be thorough.
              </>
            ) : null}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
          </DialogClose>
          <Button type="button" onClick={onConfirm} data-testid="delete-confirm">
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ConfigDialog({
  open,
  tenantId,
  existing,
  onOpenChange,
  onSaved,
}: {
  open: boolean;
  tenantId: string;
  existing: TenantMcpConfigRead | null;
  onOpenChange: (o: boolean) => void;
  onSaved: () => void;
}) {
  const isEdit = existing !== null;
  const [name, setName] = React.useState(existing?.name ?? "");
  const [connectorKind, setConnectorKind] = React.useState<ConnectorKind>(
    existing?.connector_kind ?? "slack",
  );
  const [endpoint, setEndpoint] = React.useState(existing?.endpoint ?? "");
  const [enabled, setEnabled] = React.useState<boolean>(existing?.enabled ?? true);
  const [allowedTools, setAllowedTools] = React.useState<string>(
    existing?.allowed_tools ? existing.allowed_tools.join(", ") : "",
  );
  const [allowAll, setAllowAll] = React.useState<boolean>(
    existing ? existing.allowed_tools === null : true,
  );
  const [saving, setSaving] = React.useState(false);

  // No useEffect-driven reset: the parent re-mounts this component via a `key`
  // prop tied to the target id (or "new"/"closed"), so every useState above
  // re-initializes from the fresh `existing` prop on mount. Avoids the
  // React 19 `react-hooks/set-state-in-effect` lint and matches the "derive
  // on mount, reset by key" idiom.

  const nameInvalid = !name.trim();
  const endpointInvalid = !urlOk(endpoint.trim());

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (nameInvalid) {
      toast.error("Name is required");
      return;
    }
    if (endpointInvalid) {
      toast.error("Endpoint must be a valid https URL");
      return;
    }
    const tools = allowAll
      ? null
      : allowedTools
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
    setSaving(true);
    try {
      const url = isEdit
        ? `/api/internal/v1/tenants/${encodeURIComponent(tenantId)}/mcp_configs/${encodeURIComponent(existing!.id)}`
        : `/api/internal/v1/tenants/${encodeURIComponent(tenantId)}/mcp_configs`;
      const r = await fetch(url, {
        method: isEdit ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          ...(isEdit ? {} : { connector_kind: connectorKind }),
          endpoint: endpoint.trim(),
          enabled,
          allowed_tools: tools,
        }),
      });
      if (!r.ok) {
        const text = await r.text();
        toast.error(isEdit ? "Could not save changes" : "Could not create integration", {
          description: text.slice(0, 240),
        });
        return;
      }
      toast.success(isEdit ? "Integration saved" : "Integration created");
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={onSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{isEdit ? "Edit integration" : "Add integration"}</DialogTitle>
            <DialogDescription>
              {isEdit
                ? "Update this connector's metadata, allow-list, or enabled state."
                : "Wire a new external MCP server. The OAuth token can be pasted later (or run the Slack flow)."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="cfg-name">Name</Label>
            <Input
              id="cfg-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Acme Slack"
              autoComplete="off"
              required
              aria-invalid={nameInvalid}
            />
            {nameInvalid ? <p className="text-error-700 text-xs">Name is required.</p> : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="cfg-kind">Connector</Label>
            <select
              id="cfg-kind"
              className="border-border bg-background ring-offset-background focus:ring-2 focus:ring-ring h-9 w-full rounded-md border px-3 text-sm disabled:opacity-50"
              value={connectorKind}
              onChange={(e) => setConnectorKind(e.target.value as ConnectorKind)}
              disabled={isEdit}
              aria-disabled={isEdit}
            >
              {CONNECTOR_KINDS.map((k) => (
                <option key={k} value={k}>
                  {CONNECTOR_LABELS[k]}
                </option>
              ))}
            </select>
            {isEdit ? (
              <p className="text-ink-600 text-xs">
                Connector kind is immutable. Delete + recreate to change it.
              </p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="cfg-endpoint">Endpoint (https)</Label>
            <Input
              id="cfg-endpoint"
              value={endpoint}
              onChange={(e) => setEndpoint(e.target.value)}
              placeholder="https://slack-mcp.example.com/sse"
              autoComplete="off"
              required
              aria-invalid={endpointInvalid}
            />
            {endpoint && endpointInvalid ? (
              <p className="text-error-700 text-xs">Endpoint must be a valid https:// URL.</p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="cfg-allowed">Allowed tools (comma-separated)</Label>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={allowAll}
                onChange={(e) => setAllowAll(e.target.checked)}
              />
              <span>Allow every tool this MCP advertises (null allow-list)</span>
            </label>
            <Input
              id="cfg-allowed"
              value={allowedTools}
              onChange={(e) => setAllowedTools(e.target.value)}
              placeholder="search_messages, post_message"
              autoComplete="off"
              disabled={allowAll}
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            <span>Enabled (Kenny may call this MCP)</span>
          </label>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={saving || nameInvalid || endpointInvalid}>
              {saving ? "Saving…" : isEdit ? "Save" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function SlackOAuthDialog({
  config,
  tenantId,
  onClose,
  onConnected,
}: {
  config: TenantMcpConfigRead | null;
  tenantId: string;
  onClose: () => void;
  onConnected: () => void;
}) {
  // Parent re-mounts this component via a `key` tied to the OAuth target,
  // so per-config state initializes fresh each open — no useEffect-driven
  // reset needed (and no React 19 set-state-in-effect lint trip).
  const [authUrl, setAuthUrl] = React.useState<string | null>(null);
  const [state, setState] = React.useState<string>("");
  const [code, setCode] = React.useState("");
  const [pasteState, setPasteState] = React.useState("");
  const [starting, setStarting] = React.useState(false);
  const [finishing, setFinishing] = React.useState(false);

  const onStart = React.useCallback(async () => {
    if (!config) return;
    setStarting(true);
    try {
      // Default redirect_uri: the same page. Real production redirect URI
      // lands via Wave 3J env wiring; for the v1 paste-mode flow the
      // user just needs Slack to land *somewhere* they can read the
      // query string from.
      const redirectUri = `${window.location.origin}/settings/integrations`;
      const r = await fetch(
        `/api/internal/v1/tenants/${encodeURIComponent(tenantId)}/mcp_configs/${encodeURIComponent(config.id)}/oauth/start`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ redirect_uri: redirectUri }),
        },
      );
      if (!r.ok) {
        toast.error(`Could not start Slack OAuth (${r.status})`);
        return;
      }
      const body = (await r.json()) as { authorization_url: string; state: string };
      setAuthUrl(body.authorization_url);
      setState(body.state);
      setPasteState(body.state);
      // Open Slack in a new tab — explicit user action so popup blockers
      // don't fire (this fires from a button click).
      window.open(body.authorization_url, "_blank", "noopener,noreferrer");
    } finally {
      setStarting(false);
    }
  }, [config, tenantId]);

  const onFinish = React.useCallback(async () => {
    if (!config) return;
    if (!code.trim() || !pasteState.trim()) {
      toast.error("Paste both code and state");
      return;
    }
    setFinishing(true);
    try {
      const r = await fetch(
        `/api/internal/v1/tenants/${encodeURIComponent(tenantId)}/mcp_configs/${encodeURIComponent(config.id)}/oauth/callback`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: code.trim(), state: pasteState.trim() }),
        },
      );
      if (!r.ok) {
        toast.error(`Slack OAuth callback failed (${r.status})`);
        return;
      }
      toast.success("Slack connected");
      onConnected();
    } finally {
      setFinishing(false);
    }
  }, [code, pasteState, config, tenantId, onConnected]);

  return (
    <Dialog
      open={config !== null}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Connect with Slack</DialogTitle>
          <DialogDescription>
            Two-step flow: start the OAuth in a new tab, then paste the <code>code</code> and{" "}
            <code>state</code> values Slack redirects you to.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Button
            type="button"
            onClick={() => void onStart()}
            disabled={starting}
            data-testid="oauth-start"
          >
            {starting ? "Opening Slack…" : authUrl ? "Re-open Slack" : "1. Open Slack auth"}
          </Button>
          {authUrl ? (
            <p className="text-ink-600 text-xs break-all">
              State token: <code>{state}</code>
            </p>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="oauth-code">2. Paste code from Slack redirect</Label>
            <Input
              id="oauth-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              autoComplete="off"
              placeholder="123.456.abc..."
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="oauth-state">Paste state</Label>
            <Input
              id="oauth-state"
              value={pasteState}
              onChange={(e) => setPasteState(e.target.value)}
              autoComplete="off"
              placeholder="(state token from step 1)"
            />
          </div>
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
          </DialogClose>
          <Button type="button" onClick={() => void onFinish()} disabled={finishing}>
            {finishing ? "Connecting…" : "3. Connect"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
