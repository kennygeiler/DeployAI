# @deployai/llama-citation-adapter (Python)

`CitationValidatingRetriever` wraps any LlamaIndex `BaseRetriever` and **drops** nodes whose `metadata["citation_envelope"]` is missing or not a valid `CitationEnvelopeV01` (FR27, Epic 4-2, AR7).

- Implementation: `src/llama_citation_adapter/adapter.py`
- Tests: `tests/test_adapter.py`
- Rejections: `metrics.rejections` on `CitationMetrics` + structured log field `citation_envelope_rejections`
- Coverage: `pnpm run test:cov` (from this directory) prints `src/llama_citation_adapter/` line/branch report.

```python
from llama_citation_adapter import CitationValidatingRetriever

# inner: any BaseRetriever
wrapped = CitationValidatingRetriever(inner, metrics=...)
```
