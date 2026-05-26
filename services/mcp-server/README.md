# DeployAI MCP server (v2 Phase 4)

Standalone FastAPI service that exposes DeployAI's engagement matrix +
ledger to external Model Context Protocol clients (Claude desktop, any MCP
client). Read-only. Bearer-token auth against ``tenant_api_keys``.

Run locally:

```
uv sync
uv run uvicorn mcp_server.main:app --host 0.0.0.0 --port 3030
```

See ``docs/agent-kenny/scope-v2.md`` §8 for the spec.
