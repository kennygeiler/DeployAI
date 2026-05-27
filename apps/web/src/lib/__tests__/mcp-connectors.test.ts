import { describe, expect, it } from "vitest";

import {
  CONNECTOR_KINDS,
  MCP_CONNECTOR_CATALOG,
  getConnectorSpec,
  type ConnectorKind,
} from "@/lib/mcp-connectors";

describe("MCP_CONNECTOR_CATALOG", () => {
  it("covers all 5 v1 connector kinds with stable order", () => {
    expect(CONNECTOR_KINDS).toEqual(["slack", "linear", "gdrive", "notion", "github"]);
    expect(CONNECTOR_KINDS).toHaveLength(5);
  });

  it("has a catalog entry for every kind and a kind entry for every catalog row", () => {
    const catalogKeys = Object.keys(MCP_CONNECTOR_CATALOG).sort();
    const kinds = [...CONNECTOR_KINDS].sort();
    expect(catalogKeys).toEqual(kinds);
  });

  it("every spec round-trips its kind discriminator", () => {
    for (const kind of CONNECTOR_KINDS) {
      const spec = MCP_CONNECTOR_CATALOG[kind];
      expect(spec.kind).toBe(kind);
    }
  });

  it("every spec ships a non-empty displayName and description", () => {
    for (const kind of CONNECTOR_KINDS) {
      const spec = MCP_CONNECTOR_CATALOG[kind];
      expect(spec.displayName.length).toBeGreaterThan(0);
      expect(spec.description.length).toBeGreaterThan(0);
    }
  });

  it("every spec ships a non-empty suggestedTools list", () => {
    for (const kind of CONNECTOR_KINDS) {
      const spec = MCP_CONNECTOR_CATALOG[kind];
      expect(spec.suggestedTools.length).toBeGreaterThan(0);
      // Tool names should be non-empty strings; the runtime allow-list
      // editor surfaces these verbatim.
      for (const tool of spec.suggestedTools) {
        expect(typeof tool).toBe("string");
        expect(tool.length).toBeGreaterThan(0);
      }
    }
  });

  it("only slack has oauthSupported = true in v1", () => {
    const oauthEnabled = CONNECTOR_KINDS.filter((k) => MCP_CONNECTOR_CATALOG[k].oauthSupported);
    expect(oauthEnabled).toEqual(["slack"]);
  });

  it("every spec leaves defaultEndpoint null (tenants supply their own MCP URL)", () => {
    for (const kind of CONNECTOR_KINDS) {
      expect(MCP_CONNECTOR_CATALOG[kind].defaultEndpoint).toBeNull();
    }
  });

  it("every spec ships an https docsUrl", () => {
    for (const kind of CONNECTOR_KINDS) {
      const url = MCP_CONNECTOR_CATALOG[kind].docsUrl;
      expect(url.startsWith("https://")).toBe(true);
    }
  });

  it("ships the concrete tool hints called out in the scope-v2 Wave 3J brief", () => {
    // Locks the specific tool names down so a careless reshape doesn't
    // silently drop the research-backed defaults that Wave 3H's allow-
    // list editor relies on. If the catalog needs to change, the brief +
    // this assertion both need an explicit update.
    expect(MCP_CONNECTOR_CATALOG.slack.suggestedTools).toEqual([
      "search_messages",
      "list_channels",
      "send_message",
    ]);
    expect(MCP_CONNECTOR_CATALOG.linear.suggestedTools).toEqual([
      "list_issues",
      "create_issue",
      "search_issues",
      "comment",
    ]);
    expect(MCP_CONNECTOR_CATALOG.gdrive.suggestedTools).toEqual(["search_files", "read_file"]);
    expect(MCP_CONNECTOR_CATALOG.notion.suggestedTools).toEqual([
      "search",
      "read_page",
      "list_databases",
      "query_database",
    ]);
    expect(MCP_CONNECTOR_CATALOG.github.suggestedTools).toEqual([
      "search_code",
      "read_file",
      "list_issues",
      "create_issue",
      "search_pull_requests",
    ]);
  });
});

describe("getConnectorSpec", () => {
  it("returns the catalog row for a known kind", () => {
    const kind: ConnectorKind = "slack";
    expect(getConnectorSpec(kind)).toBe(MCP_CONNECTOR_CATALOG.slack);
  });
});
