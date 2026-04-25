"""3-item hard budget and “What I Ranked Out” footer (FR22, FR24, FR34).

Surfaces (In-Meeting Alert, Morning Digest) share the same agent-level cap: at most
three ``primary`` items; everything else is listed in ``ranked_out`` with a
one-line suppression reason. Composition: :func:`oracle_retrieve` →
:func:`apply_three_item_budget`.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Literal

from oracle.retrieve import (
    CorpusConfidenceMarker,
    ExplicitNullResult,
    OracleItem,
    OracleResponse,
)

PRIMARY_BUDGET = 3

OracleSurface = Literal["in_meeting_alert", "morning_digest"]


@dataclass(frozen=True, slots=True)
class RankedOutItem:
    """Suppressed candidate named for the ranked-out footer (FR24)."""

    label: str
    reason: str


@dataclass(frozen=True, slots=True)
class BudgetedOracleResponse:
    """Oracle emission after the 3-item hard budget (Story 6-4)."""

    primary: tuple[OracleItem, ...]
    ranked_out: tuple[RankedOutItem, ...]
    corpus_confidence_marker: CorpusConfidenceMarker
    null_result: ExplicitNullResult | None
    surface: OracleSurface
    """Same cap for In-Meeting Alert and Morning Digest (FR34)."""


def _item_label(item: OracleItem) -> str:
    t = (item.text or "").strip()
    if not t:
        return item.node_id or "untitled"
    return textwrap.shorten(t, width=100, placeholder="…")


def _ranked_out_reason(*, place_1_indexed: int, total: int) -> str:
    return f"Below top-{PRIMARY_BUDGET} by contextual_fit_score (rank {place_1_indexed} of {total})."


def apply_three_item_budget(
    response: OracleResponse,
    *,
    surface: OracleSurface = "in_meeting_alert",
) -> BudgetedOracleResponse:
    """Split ranked items into at most ``PRIMARY_BUDGET`` primary rows plus a ranked-out footer.

    Passes through :attr:`~oracle.retrieve.OracleResponse.corpus_confidence_marker` and
    ``null_result`` from retrieval (CCM reflects the full gated corpus before the cut).
    """
    if response.null_result is not None or not response.items:
        return BudgetedOracleResponse(
            primary=(),
            ranked_out=(),
            corpus_confidence_marker=response.corpus_confidence_marker,
            null_result=response.null_result,
            surface=surface,
        )

    items = list(response.items)
    n = len(items)
    take = min(PRIMARY_BUDGET, n)
    primary = tuple(items[:take])
    out: list[RankedOutItem] = []
    for i in range(take, n):
        it = items[i]
        place = i + 1
        out.append(
            RankedOutItem(
                label=_item_label(it),
                reason=_ranked_out_reason(place_1_indexed=place, total=n),
            )
        )
    return BudgetedOracleResponse(
        primary=primary,
        ranked_out=tuple(out),
        corpus_confidence_marker=response.corpus_confidence_marker,
        null_result=None,
        surface=surface,
    )


def assert_primary_at_most_three(emit: BudgetedOracleResponse) -> None:
    """Contract hook for CI / Alert emissions: ``len(primary) ≤ 3`` (hard budget)."""
    if len(emit.primary) > PRIMARY_BUDGET:
        msg = f"primary budget exceeded: {len(emit.primary)} > {PRIMARY_BUDGET}"
        raise AssertionError(msg)
