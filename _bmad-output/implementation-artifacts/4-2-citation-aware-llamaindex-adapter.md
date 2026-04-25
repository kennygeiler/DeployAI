# Story 4-2: Citation-aware LlamaIndex adapter (AR7)

**Status:** done  
**Epic:** Epic 4

## Summary

- Package: `packages/llama-citation-adapter` (`deployai-llama-citation-adapter`), depends on `llama-index-core` + `deployai-citation`.
- `CitationValidatingRetriever` wraps `BaseRetriever`, validates `metadata["citation_envelope"]` with `CitationEnvelopeV01`, increments `CitationMetrics.rejections` and logs on drop.
- Tests: contract hook, pass/drop/mixed/async (malformed never reaches “agent” output).

## Completion

- [x] Code + unit/async tests
- [x] `sprint-status.yaml` story `4-2-citation-aware-llamaindex-adapter` → `done` (with epic-4)
