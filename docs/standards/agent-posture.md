# Agent posture (suggestions only)

DeployAI agents must not **auto-execute** user-impacting actions. Surfaces are **suggestion-first** (FR25, DP10).

## Oracle (`services/oracle`)

- Every emitted `OracleItem` has `action_posture: "suggestion"` (see `oracle.retrieve.OracleItem`).
- Do **not** add `action_posture: "executed"`, `auto_execute`, or equivalent on Oracle payloads without a **user-originated** override event (separate product path).
- After retrieval and after `apply_three_item_budget`, call `validate_oracle_response_posture` / `validate_budgeted_oracle_posture` before persisting or sending to a surface.

## PR / code review checklist

- [ ] Grep the diff for: `action_posture` values other than `suggestion`, `executed`, `auto_execute`, `autorun`, `run_immediately`, `no_confirm`.
- [ ] New Oracle or Strategist code paths: confirm user confirmation (or future override event) is in the design, not a silent side effect.
- [ ] If a third posture is required later, document it here and add an explicit type + migration plan.

## Related

- Story 6-5 (Epic 6): `assert_oracle_items_suggestions_only` in `services/oracle/src/oracle/posture.py`
