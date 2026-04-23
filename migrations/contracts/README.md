# Contract migrations

Breaking changes to `packages/contracts` (field removal, type narrowing, new **required** fields) must ship with a human-readable note in this directory **before** the schema change lands on `main`.

**Expand-only** changes (new optional properties) are allowed without a migration file if `pnpm run contract:check` and `CHANGELOG.md` are updated.

**Naming:** `MIGRATION-<from>-to-<to>.md` (for example, `MIGRATION-0.1.0-to-0.2.0.md`).

**Contents (minimum):**

- Motivation
- Field-by-field delta vs the previous Zod/JSON schema
- Consumer impact (Control Plane, web, edge agent, Go FOIA CLI)
- Rollout / feature-flag plan if applicable
