# @deployai/contracts

Cross-language schema contracts (Story 1.11, FR27, NFR55). The citation envelope is authored in `src/citation-envelope.ts` (Zod). JSON Schema is emitted to `schema/` and must match the Zod source (`pnpm run contract:check`).

- `pnpm run emit-schema` — refresh `schema/citation-envelope-0.1.0.schema.json` after Zod changes.
- `pnpm run contract:check` — Vitest + byte-stable JSON Schema diff (CI + local).
