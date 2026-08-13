# Outbound-dependency resilience (control plane)

What happens when each thing the control plane talks to goes down: the
documented fail-open / fail-closed policy, the circuit breakers that
enforce part of it, and what a user actually sees.

Breaker implementation:
`services/control-plane/src/control_plane/infra/circuit_breaker.py`
(classic closed → open → half-open, per dependency).

## Environment

| Env | Default | Meaning |
| --- | --- | --- |
| `DEPLOYAI_CIRCUIT_FAILURE_THRESHOLD` | `5` | Consecutive transport-level failures before a dependency's breaker opens. `0` disables circuit breaking entirely. |
| `DEPLOYAI_CIRCUIT_COOLDOWN_S` | `30` | Seconds an open breaker waits before admitting one half-open probe call. |

Breakers are **on by default** — this is safe because a breaker only trips
after N *consecutive* failures and any success resets the count, so a
healthy dependency never trips. Only transport-level outcomes count as
failures (timeouts, connect errors, upstream 5xx); a 4xx or a malformed
response body proves the dependency is up and records as success, so a
misconfigured token cannot masquerade as an outage.

## Policy table

| Dependency | Failure behavior | Breaker policy | What degrades |
| --- | --- | --- | --- |
| **Anthropic** (LLM, `packages/llm-provider-py`) | Retry with exponential backoff inside the provider: 3 attempts, 1s base delay, 30s max delay, 120s max elapsed; retryable = 429/5xx + transient transport errors (`llm_provider_py/util.py`). Persistent failure raises out of the turn. | No breaker (retry policy already handles transients; a turn without the LLM cannot proceed anyway). | The turn ends with an SSE `error` frame (`KennyAgentService` catches the exception and emits `ErrorChunk` — `service.py`). The user sees "turn failed"; nothing partial is persisted as final. |
| **MCP connectors** (Slack/Linear/GDrive/Notion/GitHub, `agents/agent_kenny/mcp_client.py`) | Five pre-network guards: kill switch, allow-list, per-tenant rate limit, SSRF egress guard, then **one breaker per connector** (`mcp:<kind>`). Fail-closed-fast: with the circuit open the doomed network call is skipped and `McpCircuitOpen` flows through the same denial machinery as other guards — distinct audit kind `mcp_circuit_open`, span attribute `mcp.denial_reason=circuit_open`. | Breaker per connector; a dead Slack upstream never blocks GitHub calls. Trips on consecutive timeouts / connect errors / 5xx only. | The model receives a synthesized is_error `tool_result` ("external connector temporarily unavailable (circuit open); retry in ~Ns") wrapped in the `<external_data>` envelope, and keeps the turn moving with internal tools. Dashboard SSE shows status `circuit_open`. At turn start, a connector whose `tools/list` hits an open circuit is dropped from that turn's tool merge (`mcp_loader` degraded path). |
| **Voyage embedder** (`agents/agent_kenny/embeddings/voyage_client.py`) | One in-client retry on 5xx/network error, then `VoyageError`. The breaker wraps the HTTP call; open circuit raises `VoyageCircuitOpen` — a `VoyageError` subclass — with **no network attempt**, so every caller degrades exactly as it does for a live Voyage outage. | One process-wide `voyage` breaker (module-level, shared across embedder instances since the worker rebuilds its client per tick). | `vector_search` surfaces a `ToolError` → is_error tool_result → the model falls back to `keyword_search` and its other tools; the user still gets an answer, just from keyword rather than semantic retrieval. The embedder worker marks affected `embedding_jobs` rows failed for later retry. (Unset `VOYAGE_API_KEY` remains the separate zero-vector local-dev fallback and never touches the breaker.) |
| **Redis** | *Rate limiter* (`infra/rate_limit.py`): **fails open** — Redis errors log a warning and admit the request (availability over enforcement). *Session store* (`auth/session_service.py`, the only other Redis consumer): **fails closed** — login, token refresh, logout, and revoke-all raise, so those requests 5xx while Redis is down. Already-issued access JWTs keep verifying (signature check is local) until their TTL expires, so active users are unaffected for up to 15 minutes. | No breaker — both consumers are request-scoped with their own policy; skipping Redis faster would not change either outcome. | With Redis down: no fleet-wide rate limiting; no new logins or refreshes until it returns. |
| **Postgres** | **Hard dependency, fail closed.** No breaker or fallback — the ledger, tenancy, and checkpoint store are the product's source of truth. | n/a | Requests fail while Postgres is down. Agent turns are durable across the outage: every LangGraph superstep is checkpointed to Postgres, and a turn interrupted by process death resumes from its checkpoint with zero shared in-memory state — proven by `services/control-plane/tests/integration/test_agent_durability.py`. |

## Observability

- Gauge `deployai_circuit_state{dependency}` — 0 closed, 1 half-open, 2 open.
- Counter `deployai_circuit_opens_total{dependency}` — open transitions.
- Warning log `circuit_breaker dependency=... transition=...` on every
  state change.
- MCP breaker denials additionally land a `mcp_circuit_open` ledger row
  (tenant-scoped audit trail, detail carries `retry_after_s`).

Dependency label values today: `mcp:slack`, `mcp:linear`, `mcp:gdrive`,
`mcp:notion`, `mcp:github`, `voyage`.

## Honest caveats

- **Breaker state is per process.** Like the in-memory API rate limiter,
  there is no cross-instance coordination: each control-plane replica
  trips and recovers on its own evidence, and state resets on restart.
  That is acceptable for a breaker (it protects each process's event loop
  from stalling on a dead dependency), but do not read the gauge from one
  replica as fleet truth.
- The half-open probe budget is 1: after the cooldown, exactly one real
  call tests the dependency; concurrent callers during the probe are
  rejected with `retry_after_s=0` (retry imminent).
