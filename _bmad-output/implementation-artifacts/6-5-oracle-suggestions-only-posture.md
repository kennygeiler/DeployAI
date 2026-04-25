# Story 6-5 — Oracle suggestions-only posture (done)

**Epic:** 6 · **FRs:** FR25, **DP10**

## Shipped

- `OracleItem.action_posture: Literal["suggestion"]` (default) on every retrieved row; `oracle_retrieve` sets it explicitly.
- `oracle/posture.py`: `assert_oracle_items_suggestions_only`, `validate_oracle_response_posture`, `validate_budgeted_oracle_posture`.
- `docs/standards/agent-posture.md`: PR checklist (no `executed` / auto-execute patterns).
- `tests/test_posture.py` contract tests.

## Notes

- User-driven override events (future) remain out of band; this story only enforces the Oracle agent boundary.
