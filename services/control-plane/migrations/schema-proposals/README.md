# Schema proposal migration scaffolds (Story 1-17)

When a Platform Admin **promotes** a pending proposal through the control-plane
internal API, the service writes an **expand** stub here:

`migrations/schema-proposals/<proposal-id>.py`

**These files are not part of the Alembic head chain** until a human reviews
and moves (or rewrites) them under `alembic/versions/`. Promoted fields only
become queryable after a real expand revision is merged to `main` and applied.

```http
# Example internal API
GET    /internal/v1/tenants/{tid}/schema-proposals?status=pending
POST   /internal/v1/tenants/{tid}/schema-proposals
POST   /internal/v1/tenants/{tid}/schema-proposals/{id}/promote
POST   /internal/v1/tenants/{tid}/schema-proposals/{id}/reject
# Headers: X-DeployAI-Internal-Key, and for review actions: X-Deployai-Reviewer-Actor-Id: <uuid>
```

Tests may set `DEPLOYAI_SCHEMA_PROPOSAL_SCAFFOLD_DIR` to a temp directory.
