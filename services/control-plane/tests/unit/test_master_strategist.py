"""Unit tests for the Phase 7.4 Master Strategist synthesis agent.

Pure function — no DB, no FastAPI. Predicates run deterministically; the
fake LLM returns hand-crafted JSON for the phrasing step.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

from llm_provider_py.types import CapabilityMatrix, ChatMessage
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed

from control_plane.agents.master_strategist import (
    PortfolioEngagement,
    PortfolioNode,
    master_strategist_candidates,
    master_strategist_phrase,
    run_master_strategist,
)


class _FakeLLM:
    id = "fake"

    def __init__(self, response: str = "[]") -> None:
        self.response = response
        self.call_count = 0
        self.last_messages: list[ChatMessage] | None = None

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        _ = temperature, max_output_tokens
        self.last_messages = messages
        self.call_count += 1
        return self.response

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        _ = messages, temperature, max_output_tokens
        for chunk in (self.chat_complete(messages),):
            yield chunk

    def embed(self, text: str) -> list[float]:
        return pseudo_embed(text, 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


_TENANT = uuid.UUID("00000000-0000-7000-8000-000000000099")


def _eng(
    *,
    name: str,
    status: str = "active",
    roles: tuple[str, ...] = ("deployment_strategist", "fde", "biz_dev"),
    risks: tuple[str, ...] = (),
    systems: tuple[str, ...] = (),
) -> PortfolioEngagement:
    eng_id = uuid.uuid4()
    nodes = []
    for t in risks:
        nodes.append(PortfolioNode(id=uuid.uuid4(), node_type="risk", title=t))
    for t in systems:
        nodes.append(PortfolioNode(id=uuid.uuid4(), node_type="system", title=t))
    return PortfolioEngagement(
        id=eng_id,
        name=name,
        status=status,
        current_phase="discovery",
        member_roles=roles,
        nodes=tuple(nodes),
        edges=(),
    )


def test_no_portfolio_returns_empty() -> None:
    cands = master_strategist_candidates(tenant_id=_TENANT, engagements=[])
    assert cands == []


def test_recurring_risk_fires_when_jaccard_threshold_met_across_two_engagements() -> None:
    eng_a = _eng(name="Acme County", risks=("vendor data residency",))
    eng_b = _eng(name="Travis County", risks=("vendor data residency concerns",))
    cands = master_strategist_candidates(tenant_id=_TENANT, engagements=[eng_a, eng_b])
    types = {c.insight_type for c in cands}
    assert "recurring_risk_pattern" in types
    c = next(c for c in cands if c.insight_type == "recurring_risk_pattern")
    assert c.severity == "medium"  # 2 engagements only


def test_recurring_risk_high_severity_at_three_or_more() -> None:
    eng_a = _eng(name="Acme", risks=("data residency",))
    eng_b = _eng(name="Travis", risks=("data residency concerns",))
    eng_c = _eng(name="Polk", risks=("data residency rules",))
    cands = master_strategist_candidates(tenant_id=_TENANT, engagements=[eng_a, eng_b, eng_c])
    recurring = [c for c in cands if c.insight_type == "recurring_risk_pattern"]
    assert len(recurring) == 1
    assert recurring[0].severity == "high"


def test_recurring_risk_skips_single_engagement_repetition() -> None:
    # Two identical risks on the SAME engagement should not fire.
    eng = _eng(name="Acme", risks=("data residency", "data residency"))
    cands = master_strategist_candidates(tenant_id=_TENANT, engagements=[eng])
    assert not [c for c in cands if c.insight_type == "recurring_risk_pattern"]


def test_system_concentration_fires_at_three_engagements() -> None:
    # All three use the same system — Jaccard = 1.0 ≥ 0.7 threshold.
    eng_a = _eng(name="A", systems=("ArcGIS Enterprise",))
    eng_b = _eng(name="B", systems=("ArcGIS Enterprise",))
    eng_c = _eng(name="C", systems=("ArcGIS Enterprise",))
    cands = master_strategist_candidates(tenant_id=_TENANT, engagements=[eng_a, eng_b, eng_c])
    types = {c.insight_type for c in cands}
    assert "system_concentration" in types


def test_system_concentration_skipped_at_two_engagements() -> None:
    eng_a = _eng(name="A", systems=("ArcGIS Enterprise",))
    eng_b = _eng(name="B", systems=("ArcGIS Enterprise",))
    cands = master_strategist_candidates(tenant_id=_TENANT, engagements=[eng_a, eng_b])
    assert not [c for c in cands if c.insight_type == "system_concentration"]


def test_role_coverage_gap_fires_when_peers_have_role() -> None:
    # Two of three engagements have an FDE; the one without should be flagged.
    has_fde = ("deployment_strategist", "fde", "biz_dev")
    no_fde = ("deployment_strategist", "biz_dev")
    eng_a = _eng(name="A", roles=has_fde)
    eng_b = _eng(name="B", roles=has_fde)
    eng_c = _eng(name="C", roles=no_fde)
    cands = master_strategist_candidates(tenant_id=_TENANT, engagements=[eng_a, eng_b, eng_c])
    gap = [c for c in cands if c.insight_type == "role_coverage_gap"]
    # Only one engagement is missing the role.
    assert len(gap) == 1


def test_role_coverage_gap_ignores_inactive_engagements() -> None:
    eng_a = _eng(name="A", roles=("fde",))
    eng_b = _eng(name="B", roles=("fde",))
    eng_c = _eng(name="C", roles=(), status="paused")
    cands = master_strategist_candidates(tenant_id=_TENANT, engagements=[eng_a, eng_b, eng_c])
    assert not [c for c in cands if c.insight_type == "role_coverage_gap"]


def test_dedup_key_is_stable_across_runs() -> None:
    eng_a = _eng(name="A", risks=("data residency",))
    eng_b = _eng(name="B", risks=("data residency",))
    a = master_strategist_candidates(tenant_id=_TENANT, engagements=[eng_a, eng_b])
    b = master_strategist_candidates(tenant_id=_TENANT, engagements=[eng_a, eng_b])
    a_keys = sorted(c.dedup_key for c in a)
    b_keys = sorted(c.dedup_key for c in b)
    assert a_keys == b_keys


def test_phrase_zips_llm_response_to_drafts() -> None:
    eng_a = _eng(name="A", risks=("data residency",))
    eng_b = _eng(name="B", risks=("data residency",))
    cands = master_strategist_candidates(tenant_id=_TENANT, engagements=[eng_a, eng_b])
    llm = _FakeLLM(
        response=json.dumps([{"title": "Data residency is a recurring risk", "body": "Three engagements show this."}])
    )
    drafts = master_strategist_phrase(tenant_name="acme-org", engagements=[eng_a, eng_b], candidates=cands, llm=llm)
    assert len(drafts) == 1
    assert drafts[0].title.startswith("Data residency")
    assert drafts[0].insight_type == "recurring_risk_pattern"
    assert llm.call_count == 1


def test_run_master_strategist_skips_llm_when_no_candidates() -> None:
    llm = _FakeLLM(response="[]")
    drafts = run_master_strategist(tenant_id=_TENANT, tenant_name="empty", engagements=[], llm=llm)
    assert drafts == []
    assert llm.call_count == 0


def test_phrase_handles_bad_json() -> None:
    eng_a = _eng(name="A", risks=("data residency",))
    eng_b = _eng(name="B", risks=("data residency",))
    cands = master_strategist_candidates(tenant_id=_TENANT, engagements=[eng_a, eng_b])
    llm = _FakeLLM(response="not json at all")
    drafts = master_strategist_phrase(tenant_name="x", engagements=[eng_a, eng_b], candidates=cands, llm=llm)
    assert drafts == []
