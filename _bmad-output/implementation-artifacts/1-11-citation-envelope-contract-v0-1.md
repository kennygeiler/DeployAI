# Story 1.11: Citation envelope contract v0.1.0

Status: **done** (merged via [PR #12](https://github.com/kennygeiler/DeployAI/pull/12))

## Delivered

- `packages/contracts` — Zod `CitationEnvelopeSchema`, frozen `schema_version: "0.1.0"`, committed JSON Schema, `pnpm run contract:check` (semantic deep equality + Vitest).
- `services/_shared/citation` — `deployai-citation` Pydantic mirror; path dependency of `deployai-control-plane`.
- `migrations/contracts/README.md` — breaking-change policy (NFR55).
- `docs/contracts/citation-envelope.md` — field semantics (FR27).
- Root `contract:check`, `turbo.json` task, `ci.yml` smoke step.

## Code review (adversarial)

- **Schema sync:** Byte-equality was too brittle vs Prettier; `contract-check` uses `isDeepStrictEqual` on parsed JSON.
- **Python:** `RetrievalPhaseV01` validated in a `field_validator`; ISO timestamp regex aligned with tests; `Final[Literal["0.1.0"]]` for mypy.

## Out of scope (deferred)

- HTTP agent boundary validator in control-plane — lands with agent routes.
- Auto-codegen of Pydantic from JSON Schema — hand parity is sufficient for v0.1.
