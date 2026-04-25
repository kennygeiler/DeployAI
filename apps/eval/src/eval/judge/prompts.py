"""System prompts for tier-2 LLM judge (populated in Story 4-6 when provider is wired)."""

JUDGE_SYSTEM_V0 = """You are an evaluator comparing agent retrieval citations to a golden set.
For each query, consider relevance and whether cited node IDs match the expected evidence.
Output strict JSON only; the runner validates shape."""
