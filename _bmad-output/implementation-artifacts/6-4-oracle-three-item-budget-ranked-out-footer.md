# Story 6-4 — Oracle 3-item budget + "What I Ranked Out" (done)

**Epic:** 6 · **FRs:** FR22, FR24, FR34 (Morning Digest same cap as In-Meeting Alert)

## Shipped

- `services/oracle/src/oracle/budget.py`: `apply_three_item_budget(OracleResponse, surface=...)` → `BudgetedOracleResponse` with `primary` (≤3 `OracleItem`s), `ranked_out` (`label` + one-line `reason`), passthrough `corpus_confidence_marker` / `null_result` from retrieval.
- Surfaces: `surface="in_meeting_alert"` | `"morning_digest"` (identical behavior; label for downstream).
- `assert_primary_at_most_three(emit)` for contract tests (`len(primary) ≤ 3`).
- Tests: `tests/test_budget.py` — 20 candidates → 3 primary + 17 ranked_out, contract loop, null passthrough, Morning Digest cap, negative test for assert helper.

## Notes

- UI copy for the footer is still owned by surfaces; the agent boundary exposes structured `ranked_out` only.
