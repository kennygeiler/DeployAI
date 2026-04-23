# Citation envelope v0.1.0 (FR27)

The citation envelope is the mandatory shape for any agent output that references canonical memory. It is defined in Zod at `packages/contracts/src/citation-envelope.ts` and checked into JSON Schema at `packages/contracts/schema/citation-envelope-0.1.0.schema.json` for cross-language consumers.

| Field | Type | Semantics |
| --- | --- | --- |
| `schema_version` | `"0.1.0"` | Frozen semver; bumps require `CHANGELOG.md` + usually `migrations/contracts/`. |
| `node_id` | UUID | Canonical graph node the citation points at. |
| `graph_epoch` | int (≥0) | Identity-graph epoch the resolver used (time-versioning; Story 1.8+). |
| `evidence_span` | object | Inclusive **character offsets** into `source_ref` (0-based). `end` ≥ `start`. |
| `evidence_span.source_ref` | string | Opaque URN/URL pointing at evidence (e.g. transcript id). |
| `retrieval_phase` | enum | One of `cartographer`, `oracle`, `master_strategist`, `synthesis` — which retrieval posture produced the citation. |
| `confidence_score` | float [0,1] | Calibrated or policy-scoped confidence. |
| `signed_timestamp` | ISO 8601 string | When the envelope was bound (TSA or platform clock per Story 1.13+). |

Python services import `CitationEnvelopeV01` from the `deployai-citation` package.

See also: `docs/security/cross-tenant-fuzz.md` (tenant boundary) and `packages/contracts/CHANGELOG.md` (version history).
