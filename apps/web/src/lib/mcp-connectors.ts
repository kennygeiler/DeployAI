/**
 * v2 Phase 5 Wave 3J — MCP outbound connector catalog (per scope-v2 §9.1).
 *
 * Single source of truth for the **display metadata + UX hints** the
 * integrations admin UI (Wave 3H) renders when a tenant admin enables an
 * external MCP server. The runtime catalog (the list of `ConnectorKind`
 * literals enforced server-side) lives on the CP side in
 * `control_plane.domain.mcp_outbound.CONNECTOR_KINDS` and
 * `control_plane.agents.agent_kenny.mcp_connectors.CONNECTOR_KINDS`; this
 * module mirrors that catalog so the UI never invents a kind the DB
 * CHECK constraint would reject. Widening this catalog requires:
 *   1. an alembic migration ALTERing `ck_tenant_mcp_configs_connector_kind`,
 *   2. a matching widening in the two Python catalogs above,
 *   3. a new entry here.
 *
 * `oauthSupported` is the OAuth-start affordance toggle for the UI: only
 * `slack` is wired end-to-end today (Wave 2E + Wave 3J env). The other
 * four return HTTP 501 from the CP OAuth routes until per-connector
 * flows land in a follow-up wave; the UI hides the "Connect" button for
 * those and the admin supplies a long-lived token via the form instead.
 */

export type ConnectorKind = "slack" | "linear" | "gdrive" | "notion" | "github";

export interface ConnectorSpec {
  /** Discriminator — matches the CP `ConnectorKind` Literal verbatim. */
  kind: ConnectorKind;
  /** Human label rendered in the integrations catalog (e.g. "Slack"). */
  displayName: string;
  /** One-sentence description shown beneath the display name. */
  description: string;
  /**
   * True only when the CP has an end-to-end OAuth start/callback wired.
   * v1: only Slack. The UI hides the "Connect" button for the rest and
   * falls back to a manual auth-token form.
   */
  oauthSupported: boolean;
  /**
   * Common MCP tool names the tenant admin is likely to want when shaping
   * the allow-list. Used purely as UX hints in the allow-list editor —
   * the authoritative tool list is the one the MCP server itself
   * advertises at agent-loop start (Wave 2D `mcp_client.py`).
   */
  suggestedTools: string[];
  /**
   * Pre-fill hint for the MCP server URL. Null today because each tenant
   * runs their own MCP server (or uses a hosted instance with a tenant-
   * specific subdomain); pasting one URL would mislead.
   */
  defaultEndpoint: string | null;
  /** Link out to the MCP server repo / docs. */
  docsUrl: string;
}

// TODO Wave 3J+: replace these placeholder docsUrls with the canonical
// per-connector MCP server repos as they stabilise. The modelcontextprotocol/
// servers monorepo is the upstream catalog; individual servers may move to
// vendor-owned repos (e.g. github/github-mcp-server is the official GitHub
// one). Until each is verified, we point at the catalog so links don't
// silently rot. Tracked in scope-v2 §9.1.
const MCP_SERVERS_CATALOG_URL = "https://github.com/modelcontextprotocol/servers";

export const MCP_CONNECTOR_CATALOG: Record<ConnectorKind, ConnectorSpec> = {
  slack: {
    kind: "slack",
    displayName: "Slack",
    description:
      "Search workspace messages and post into channels so Kenny can cite live conversations alongside ledger evidence.",
    oauthSupported: true,
    suggestedTools: ["search_messages", "list_channels", "send_message"],
    defaultEndpoint: null,
    docsUrl: MCP_SERVERS_CATALOG_URL,
  },
  linear: {
    kind: "linear",
    displayName: "Linear",
    description:
      "Read and triage Linear issues so Kenny can correlate engineering work to engagement decisions and risks.",
    oauthSupported: false,
    suggestedTools: ["list_issues", "create_issue", "search_issues", "comment"],
    defaultEndpoint: null,
    docsUrl: MCP_SERVERS_CATALOG_URL,
  },
  gdrive: {
    kind: "gdrive",
    displayName: "Google Drive",
    description:
      "Search and read Google Drive files so Kenny can cite source documents (briefs, contracts, slide decks) on demand.",
    oauthSupported: false,
    suggestedTools: ["search_files", "read_file"],
    defaultEndpoint: null,
    docsUrl: MCP_SERVERS_CATALOG_URL,
  },
  notion: {
    kind: "notion",
    displayName: "Notion",
    description:
      "Search Notion pages and query databases so Kenny can pull tenant-owned playbooks and meeting notes into its answers.",
    oauthSupported: false,
    suggestedTools: ["search", "read_page", "list_databases", "query_database"],
    defaultEndpoint: null,
    docsUrl: MCP_SERVERS_CATALOG_URL,
  },
  github: {
    kind: "github",
    displayName: "GitHub",
    description:
      "Search code, read files, and inspect issues / pull requests so Kenny can ground engineering questions in the actual repo state.",
    oauthSupported: false,
    suggestedTools: [
      "search_code",
      "read_file",
      "list_issues",
      "create_issue",
      "search_pull_requests",
    ],
    defaultEndpoint: null,
    docsUrl: MCP_SERVERS_CATALOG_URL,
  },
};

/**
 * Stable iteration order for the UI (alphabetical-ish; matches the order
 * the CP `CONNECTOR_KINDS` tuple uses so visual + server enumerations
 * line up).
 */
export const CONNECTOR_KINDS: ConnectorKind[] = ["slack", "linear", "gdrive", "notion", "github"];

/** Convenience accessor — narrower than `MCP_CONNECTOR_CATALOG[kind]` at call sites. */
export function getConnectorSpec(kind: ConnectorKind): ConnectorSpec {
  return MCP_CONNECTOR_CATALOG[kind];
}
