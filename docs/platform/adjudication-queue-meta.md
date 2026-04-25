# Adjudication queue `meta` (JSONB)

The control plane stores [`adjudication_queue_items.meta`](../../services/control-plane/src/control_plane/domain/adjudication.py) as **opaque JSONB**. Producers are free to store rule/judge flags, replay identifiers, and notes. The **web** app at route `/admin/adjudication` (see `apps/web/src/app/(internal)/admin/adjudication/page.tsx`) reads the same `meta` and, when a **citation** block is present, renders `CitationChip` and `EvidencePanel` from `@deployai/shared-ui` in the **Memory** column.

Internal API: `GET|POST|PATCH /internal/v1/adjudication-queue-items` (see [adjudication_queue.py](../../services/control-plane/src/control_plane/api/routes/adjudication_queue.py); OpenAPI is generated at `/docs` when the service runs).

## Citation + evidence (optional)

If `meta` includes a `citation_envelope` that validates as **citation envelope v0.1.0**, the web app maps it to the shared citation UI. The envelope shape and semantics are defined in [Citation envelope v0.1.0](../contracts/citation-envelope.md) and in TypeScript at `packages/contracts/src/citation-envelope.ts`.

### Required for the citation column

| Key | Type | Description |
| --- | --- | --- |
| `citation_envelope` | object | v0.1.0 payload: `schema_version`, `node_id`, `graph_epoch`, `evidence_span` (`start`, `end`, `source_ref`), `retrieval_phase`, `confidence_score`, `signed_timestamp`. |

### Optional (web)

| Key | Type | Description |
| --- | --- | --- |
| `evidence_body` | string | Quoted text for the evidence panel; **highlight** uses UTF-16 indices from `citation_envelope.evidence_span` against this string. The web app truncates to `ADJ_EVIDENCE_BODY_MAX_CHARS` (100k) on parse. |
| `citation_label` | string | Short chip label; trimmed. Default: `Cited source`. |
| `citation_panel_state` | string | `loading` \| `loaded` \| `degraded` \| `tombstoned` (drives `EvidencePanel`). Default: `loaded`. |
| `citation_visual_state` | string | `overridden` \| `tombstoned` (chip badges). Omitted: default. |
| `citation_supersession` | string | `current` \| `superseded` \| `unknown` \| `tombstoned` (metadata row). |
| `citation_supersession_detail` | string | Shown when supersession is `superseded`. |
| `citation_degraded_hint` | string | Extra copy in degraded mode. |
| `citation_tombstone_message` | string | Copy when the panel is tombstoned. |

### Example (minimal, valid)

```json
{
  "rule_pass": true,
  "judge_pass": false,
  "citation_envelope": {
    "schema_version": "0.1.0",
    "node_id": "550e8400-e29b-41d4-a716-446655440000",
    "graph_epoch": 0,
    "evidence_span": {
      "start": 0,
      "end": 5,
      "source_ref": "urn:transcript#session-1"
    },
    "retrieval_phase": "oracle",
    "confidence_score": 0.88,
    "signed_timestamp": "2026-04-23T12:00:00.000Z"
  },
  "evidence_body": "Hello"
}
```

**Parser:** `apps/web/.../parseAdjudicationCitation.ts` (`parseAdjudicationCitation`).

## Other keys

Any additional keys (e.g. `rule_pass`, `judge_pass`, `eval_run_id`) are stored and returned as-is. The web list view does not render them today; they remain available to future admin surfaces or other consumers.
