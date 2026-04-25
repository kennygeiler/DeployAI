"""FR25 / DP10 — Oracle suggestions-only posture (Story 6-5)."""

from __future__ import annotations

from oracle.budget import BudgetedOracleResponse
from oracle.retrieve import ActionPosture, OracleItem, OracleResponse

# Future override-driven surfaces may use other postures; Oracle agent boundary does not.
_ORACLE_ITEM_POSTURE: ActionPosture = "suggestion"


def assert_oracle_items_suggestions_only(
    items: tuple[OracleItem, ...] | list[OracleItem],
) -> None:
    """Contract: no ``action_posture`` other than ``suggestion`` on Oracle primary items."""
    for it in items:
        if it.action_posture != _ORACLE_ITEM_POSTURE:
            msg = f"Oracle item must be suggestions-only, got {it.action_posture!r} (node_id={it.node_id!r})"
            raise AssertionError(msg)


def validate_oracle_response_posture(response: OracleResponse) -> None:
    """Run after retrieval if items are published to a surface."""
    assert_oracle_items_suggestions_only(response.items)


def validate_budgeted_oracle_posture(emit: BudgetedOracleResponse) -> None:
    """Run after :func:`oracle.budget.apply_three_item_budget` before emitting Alert / Digest."""
    assert_oracle_items_suggestions_only(emit.primary)
