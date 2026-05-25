# Control-plane observability

Three endpoints + two env-var knobs cover liveness, readiness, scrape,
and structured logs for the `services/control-plane` FastAPI app.

## Endpoints

All three endpoints are unauthenticated — the expected deployment puts
them behind a cluster boundary (k8s probes + in-cluster Prometheus
scraper). Do not expose them on the public ingress.

| Path       | Status semantics                                                                    | Intended consumer        |
|------------|-------------------------------------------------------------------------------------|--------------------------|
| `/healthz` | Liveness. Process is up + serving HTTP. Always 200 once the app accepts requests.   | k8s liveness probe       |
| `/health`  | Alias of `/healthz` (Story 1.7 docker-compose AC).                                  | docker-compose healthcheck |
| `/readyz`  | Readiness. 200 only when a single `SELECT 1` against `DATABASE_URL` succeeds.       | k8s readiness probe      |
| `/metrics` | Prometheus exposition (`text/plain; version=0.0.4`). Default `prometheus_client` registry. | Prometheus scrape       |

`/readyz` body on failure: `{"status": "not-ready", "reason": "<short>"}`
with HTTP 503. `reason` is the exception class name — useful to tell
"DB pool exhausted" from "DNS not resolving" without leaking SQL state.

## Environment variables

| Var                                 | Default                       | Effect                                                                                       |
|-------------------------------------|-------------------------------|----------------------------------------------------------------------------------------------|
| `LOG_FORMAT`                        | `text`                        | `json` switches the root logger to one JSON object per line (fields below).                  |
| `LOG_LEVEL`                         | `INFO`                        | Standard `logging` level name. Applied to the root logger.                                   |
| `OTEL_EXPORTER_OTLP_ENDPOINT`       | (unset → OTel disabled)       | Base OTLP/HTTP URL. When set, both metrics and traces export.                                |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | (inherits base)             | Per-signal override for metrics.                                                             |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | (inherits base)              | Per-signal override for traces.                                                              |
| `OTEL_SERVICE_NAME`                 | `deployai-control-plane`      | Resource attribute on exported telemetry.                                                    |
| `OTEL_METRIC_EXPORT_INTERVAL`       | `5000`                        | Metric export interval (ms). Clamped to a 1000 ms floor.                                     |
| `OTEL_SDK_DISABLED`                 | (unset)                       | `1` / `true` short-circuits all OTel setup even when an endpoint is configured.              |

If no OTLP endpoint is set, the OTel setup is a no-op — `prometheus_client`
metrics still work via `/metrics` because they use the default in-process
registry, not OTel.

## JSON log fields

When `LOG_FORMAT=json` each record is one line of JSON with:

- `ts` — ISO-8601 timestamp with milliseconds.
- `level` — e.g. `INFO`, `WARNING`, `ERROR`.
- `logger` — `logging` logger name (e.g. `control_plane.workers.x`).
- `message` — formatted log message.
- `exc_info` — formatted traceback when the call passed `exc_info=True`.
- Anything supplied via `extra={...}` is merged at the top level
  (e.g. `tenant_id`, `request_id`).

## Prometheus scrape config snippet

```yaml
scrape_configs:
  - job_name: deployai-control-plane
    metrics_path: /metrics
    scheme: http
    static_configs:
      - targets:
          - control-plane.deployai.svc.cluster.local:8000
    relabel_configs:
      - source_labels: [__address__]
        target_label: instance
```

## k8s probe snippet

```yaml
livenessProbe:
  httpGet: { path: /healthz, port: http }
  initialDelaySeconds: 10
  periodSeconds: 10
readinessProbe:
  httpGet: { path: /readyz, port: http }
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 3
```

## Metrics catalog

D1.d defined a per-request perf budget of **11 SQL statements / 6 roundtrips
/ < 1 s wall-clock**. D2.d turns that budget into Prometheus signals so a
breach is observable, not just documented. All metrics live in the default
`prometheus_client` registry and ship via `/metrics`.

| Metric                                          | Type      | Labels                  | Fires when                                                                 |
|-------------------------------------------------|-----------|-------------------------|----------------------------------------------------------------------------|
| `deployai_db_statements_total`                  | Counter   | `route`, `method`       | Each SQLAlchemy `after_cursor_execute` on the app engine.                  |
| `deployai_http_request_duration_seconds`        | Histogram | `route`, `method`, `status` | Once per HTTP request, observed in the Prometheus middleware.          |
| `deployai_audit_emit_failures_total`            | Counter   | (none)                  | Any exception raised inside `emit_audit_event` (validation or flush).      |
| `deployai_slow_request_total`                   | Counter   | `route`                 | A request's wall-clock duration exceeds 1 s.                               |

`route` is always the FastAPI route *template* (e.g.
`/internal/v1/engagements/{engagement_id}`), never the raw URL — that keeps
label cardinality bounded as new engagements / tenants are created. Requests
that don't match any route fall back to `route="unknown"`.

### Recommended scrape + alert config

- **Scrape interval**: 15 s — fast enough to catch a deploy regression in the
  next on-call sweep, slow enough that the histogram bucket churn is cheap.
- **Slow-request alert**: `rate(deployai_slow_request_total[5m]) > 0.1` —
  more than 10 % of requests breaching the 1 s budget over 5 minutes.
- **Statement-budget alert**:
  `histogram_quantile(0.95, sum by (le, route) (rate(deployai_db_statements_total[5m]))) > 11`
  is the moral check, but `db_statements_total` is a counter not a histogram,
  so the practical alert is on a per-route rate increase relative to the
  baseline (compare `rate(deployai_db_statements_total[5m])` to the prior
  week's same window).
- **Audit emit failure**: `increase(deployai_audit_emit_failures_total[5m]) > 0`
  — any failure is page-worthy; compliance writes must not silently drop.

## Request correlation

Every HTTP request flowing through the control-plane app gets a UUID
correlation id, surfaced three ways:

- **Response header `X-Request-ID`** — echoed on every response so callers
  (browsers, sibling services, k8s probes) can stamp it into their own logs.
- **JSON log field `request_id`** — when `LOG_FORMAT=json`, every record
  emitted while a request is in scope carries the same id at the top level.
- **Text log prefix `[req=<short>]`** — for the default `text` formatter,
  the first 8 chars of the UUID are prepended so humans can eyeball-group
  lines without an external log aggregator.

The middleware accepts an inbound `X-Request-ID` header **only if it parses
as a UUID**. Anything else (empty, malformed, non-UUID) is replaced with a
freshly generated `uuid4()` to keep the id space uniform and to prevent
clients smuggling unbounded strings into log indices.

### Setting your own correlation id

When a sibling service or a job runner originates the request, generate a
UUID upstream and pass it through:

```bash
curl -H "X-Request-ID: $(uuidgen)" https://cp.deployai.internal/healthz
```

The same id appears in the response header and in every log record the
request emits.

### Filtering logs by request id

In JSON mode, grep by the field. With `jq`:

```bash
kubectl logs deploy/control-plane | jq -c 'select(.request_id == "<uuid>")'
```

In text mode, grep by the short prefix:

```bash
kubectl logs deploy/control-plane | grep '\[req=ab12cd34\]'
```

### Correlating with Prometheus + traces

`request_id` is intentionally not a Prometheus label — UUIDs blow up label
cardinality. To go from a slow request to its logs, query the histogram by
route + method + status to find the slow window, then `grep` the JSON logs
for `request_id` records inside that window. When OTel tracing is enabled
(`OTEL_EXPORTER_OTLP_ENDPOINT` set), the same `request_id` field appears
alongside the trace/span ids the OTel SDK injects, so a single log line is
sufficient to jump from logs → traces → metrics.
