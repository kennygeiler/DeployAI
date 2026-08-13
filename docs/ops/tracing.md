# Distributed tracing — OpenTelemetry on the control plane

The control plane (`services/control-plane`) carries explicit OpenTelemetry
tracing: a hand-written ASGI middleware makes one server span per request,
the Agent Kenny nodes open their own child spans, and outbound HTTP injects
W3C `traceparent` by hand. No auto-instrumentation packages — every span is
greppable to the line that created it (`control_plane/infra/tracing.py`).

## Enabling export

Tracing is **off by default**: with no endpoint configured the SDK pipeline
is never installed, the per-request middleware is not added, and every span
helper degrades to OpenTelemetry's built-in no-op spans.

| Env var | Default | Meaning |
| --- | --- | --- |
| `DEPLOYAI_OTEL_EXPORTER_OTLP_ENDPOINT` | unset | OTLP/HTTP collector **base** URL, e.g. `http://tempo:4318`. `/v1/traces` + `/v1/metrics` are appended. Unset → tracing not installed. |
| `DEPLOYAI_OTEL_SERVICE_NAME` | `deployai-control-plane` | `service.name` resource attribute. |

The standard `OTEL_EXPORTER_OTLP_*` / `OTEL_SERVICE_NAME` env vars are still
honored (`control_plane/otel.py`) for operators who drive the SDK the stock
way; `OTEL_SDK_DISABLED=1` force-disables everything.

Examples:

```bash
# Local Jaeger (all-in-one exposes OTLP/HTTP on 4318)
docker run --rm -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one:latest
export DEPLOYAI_OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

# Grafana Cloud (OTLP gateway; basic-auth via the standard headers var)
export DEPLOYAI_OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-<region>.grafana.net/otlp
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <base64 instance:token>"
```

## Span inventory

| Span | Where | Attributes |
| --- | --- | --- |
| `<METHOD> <route>` (SERVER) | `infra/tracing.py` `TracingMiddleware` | `http.method`, `http.route` (template, bounded cardinality), `http.status_code`, `deployai.request_id` |
| `agent_kenny.turn` | `agents/agent_kenny/service.py` (`_run_graph`, shared by the LangGraph **and** legacy drivers; `resume_approval` reuses it with `turn.resumed`) | `deployai.tenant_id`, `deployai.engagement_id`, `deployai.turn_id`, `agent.runtime`, `turn.tool_calls`, `turn.revision_attempts`, `turn.tokens` |
| `agent_kenny.llm_call` | `nodes/llm_call.py` | `llm.model`, `llm.input_tokens`, `llm.output_tokens`, `llm.stop_reason`, `llm.tool_use_count` |
| `agent_kenny.tool_dispatch` | `nodes/tool_dispatch.py` (one span per tool call) | `tool.name`, `tool.external`, `tool.row_count`, `tool.error` |
| `agent_kenny.citations` | `nodes/citations.py` (`verify_citations_parallel`) | `citations.verified`, `citations.unverified`, `citations.cross_engagement`, `citations.external` |
| `agent_kenny.revise` | `nodes/revise.py` (only when a revision fires) | `revision.attempt` |
| `agent_kenny.mcp_call` | `agents/agent_kenny/mcp_client.py` `call_tool` | `mcp.connector_kind`, `mcp.tool`, `mcp.status`; on a guard block, `mcp.denial_reason` (`kill_switch_engaged`, `not_in_allow_list`, `rate_limit_exceeded`, `egress_blocked:<reason>`) |

Node instrumentation lives on the shared node functions, so both agent
drivers (LangGraph `runtime.py` and the legacy loop in `service.py`) emit
the same tree.

## Propagation

- **Inbound**: the middleware extracts W3C `traceparent`; the web BFF
  forwards the caller's header or mints a valid one on Agent Kenny CP calls
  (`apps/web/src/lib/internal/traceparent.ts`, wired through
  `oracle-cp.ts`).
- **Outbound**: the CP injects `traceparent` into outbound MCP calls
  (`mcp_client.py`) and Voyage embedding calls (`voyage_client.py`).
- **Logs**: with `LOG_FORMAT=json`, the active trace id is stamped as
  `trace_id` on every record (alongside `request_id`), so logs ↔ traces
  cross-link.

## No-op default, verified

`tests/unit/test_tracing.py` pins the contract: middleware parents onto an
inbound `traceparent` and stamps the request id; a stubbed agent turn yields
the `turn → llm_call/tool_dispatch/citations` tree; and with no endpoint
configured, nothing is installed and no spans are exported.
