# FOIA / evidence bundle formats

DeployAI uses versioned on-disk layouts for offline verification (FR61, NFR29). This document describes the formats the FOIA CLI (`apps/foia-cli`) understands today and how canonical-memory export bundles will extend it.

## `deployai.edge.transcript.v1` (Epic 11 Story 11.3)

Produced by the edge agent (`edge_agent_write_transcript_bundle`). A bundle is a **directory** containing:

| File | Purpose |
|------|---------|
| `manifest.json` | Metadata, hashes, optional RFC3161 token |
| `segments.json` | Canonical JSON array of UTF-8 segment strings (exact bytes hashed) |
| `transcript.sig` | Standard Base64 encoding of a **64-byte** detached Ed25519 signature |

### Canonical hashing

- **Transcript SHA-256:** `SHA256` of the raw bytes of `segments.json` as written (compact JSON array; generator uses `serde_json::to_vec` / Go `json.Marshal` for an equivalent `[]string`).
- **Merkle chain:** Let `acc₀` be 32 zero bytes. For each segment `sᵢ` in order: `accᵢ₊₁ = SHA256(accᵢ ‖ UTF8(sᵢ))`. The **Merkle root** is the final `accₙ` (32 bytes), encoded as **lowercase hex** in the manifest.

### Signed payload (UTF-8)

The Ed25519 signature covers exactly this message (newline-terminated lines):

```text
DEPLOYAI_EDGE_TRANSCRIPT_V1
device_id:<uuid-or-stable-id>
merkle_root:<64 lowercase hex chars>
transcript_sha256:<64 lowercase hex chars>
```

### `manifest.json` (camelCase JSON)

- `format`: literal `deployai.edge.transcript.v1`
- `deviceId`, `publicKeyEd25519B64` (32-byte Ed25519 public key, standard Base64)
- `merkleRootHex`, `transcriptSha256Hex`
- `segmentsFile`: usually `segments.json`
- `createdAtUnixMs`: wall clock at bundle creation
- `rfc3161` (optional): `{ "tsaUrl": "...", "tokenDerBase64": "..." }` — DER-encoded **TimeStampToken** (PKCS#7) from an RFC 3161 HTTP TSA; the imprint is the **32-byte Merkle root** (SHA-256 message imprint). Offline verification uses `foia verify` (and `github.com/digitorus/timestamp` to parse and verify the CMS when certificates are embedded).

### Verification

```bash
foia verify path/to/bundle-dir
```

Pass `--public-key-b64` to require a specific registered key (must match `publicKeyEd25519B64` in the manifest). Use `--skip-tsa` to validate only the device signature and Merkle chain when a token is present but trust-store validation is not desired.

**Committed golden fixtures** (Story 11.6, no network): `apps/foia-cli/testdata/edge-transcript-v1-valid` and `…-tampered` are exercised by `go test ./pkg/verify/...`. Regenerate after format changes with `go run ./hack/gen-golden-edge-bundle` from `apps/foia-cli`.

## `deployai.edge.transcript.v2`

Same directory layout as v1. Additions:

- **`format`:** `deployai.edge.transcript.v2`
- **`consentSha256Hex`:** SHA-256 of the UTF-8 consent JSON string (64 hex chars), or omit / all zeros when absent.
- **Signed payload** adds a line after v1 fields:

```text
DEPLOYAI_EDGE_TRANSCRIPT_V2
device_id:…
merkle_root:…
transcript_sha256:…
consent_sha256:…
```

## Offline edge revocation (Story 11.7)

Sidecar JSON:

```json
{ "revocations": [ { "deviceId": "…", "revokedAtUnixMs": 1714147200000 } ] }
```

```bash
foia verify --edge-revocation revocations.json path/to/bundle-dir
```

Fails (after crypto checks) when `manifest.createdAtUnixMs >= revokedAtUnixMs` for a matching `deviceId`.

## `deployai.foia.export.v0` (Story 12.2 skeleton)

```bash
foia export --out ./export-dir --account <id> [--from unix-ms] [--to unix-ms]
```

Writes `manifest.json` + placeholder `events.jsonl`. Full canonical-memory export replaces this in later stories.
