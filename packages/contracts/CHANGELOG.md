# @deployai/contracts

All notable changes to DeployAI language-agnostic contracts are documented here. This project follows [Semantic Versioning](https://semver.org/) per NFR55.

## 0.1.0 — 2026-04-23

- Initial **citation envelope** contract (`schema_version: "0.1.0"`) used at every agent ↔ control-plane boundary (FR27).
- Zod (`citation-envelope.ts`) is the authoring source of truth; committed JSON Schema under `schema/` is CI-gated via `pnpm run contract:check`.
- Python mirror: `deployai-citation` (`services/_shared/citation`).
