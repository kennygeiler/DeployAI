"""Unit tests for the lint worker helpers (v2 Phase 0.6, scope-v2 §4).

Pure-Python checks live alongside SQL-bound checks in ``wiki_lint``. This
module exercises the side-effect-free helpers (``_stance``,
``_parse_citations``, ``_detail_fingerprint``) and the in-memory ``MatrixNode``
description scan path of ``check_missing_cite``. The SQL-bound checks are
covered in ``tests/integration/test_lint_worker.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from control_plane.agents.synthesis.claim_cite import Citation
from control_plane.workers import wiki_lint


def test_stance_approval_only() -> None:
    assert wiki_lint._stance("The proposal was approved by the steering committee.") == "approval"


def test_stance_rejection_only() -> None:
    assert wiki_lint._stance("Migration was rejected on cost grounds.") == "rejection"


def test_stance_neutral_returns_none() -> None:
    assert wiki_lint._stance("This is a neutral summary with no verdict.") is None


def test_stance_both_returns_none() -> None:
    text = "Approved at first, then rejected after legal review."
    assert wiki_lint._stance(text) is None


def test_stance_empty_returns_none() -> None:
    assert wiki_lint._stance("") is None
    assert wiki_lint._stance(None) is None


def test_parse_citations_extracts_each_kind() -> None:
    eid = uuid.uuid4()
    nid = uuid.uuid4()
    iid = uuid.uuid4()
    text = f"See [event:{eid}], [node:{nid}], and [insight:{iid}]."
    cites = wiki_lint._parse_citations(text)
    kinds = {c.kind for c in cites}
    assert kinds == {"event", "node", "insight"}
    ids = {c.id for c in cites}
    assert ids == {eid, nid, iid}


def test_parse_citations_dedupes_repeats() -> None:
    eid = uuid.uuid4()
    text = f"first [event:{eid}] middle [event:{eid}] last [event:{eid}]"
    cites = wiki_lint._parse_citations(text)
    assert len(cites) == 1
    assert cites[0].id == eid


def test_parse_citations_skips_malformed() -> None:
    text = "Garbage [event:not-a-uuid] is dropped."
    assert wiki_lint._parse_citations(text) == []


def test_detail_fingerprint_is_stable_across_key_order() -> None:
    a = {"missing_event_ids": ["b", "a"], "count": 2}
    b = {"count": 2, "missing_event_ids": ["b", "a"]}
    assert wiki_lint._detail_fingerprint(a) == wiki_lint._detail_fingerprint(b)


def test_detail_fingerprint_differs_when_payload_differs() -> None:
    a = wiki_lint._detail_fingerprint({"x": 1})
    b = wiki_lint._detail_fingerprint({"x": 2})
    assert a != b


@pytest.mark.asyncio
async def test_check_missing_cite_finds_uncited_paragraphs() -> None:
    """Hand-crafted MatrixNode with two paragraphs, second missing a cite."""
    tenant = uuid.uuid4()
    eng = uuid.uuid4()
    node_id = uuid.uuid4()
    eid = uuid.uuid4()

    node = MagicMock()
    node.id = node_id
    node.attributes = {
        "description": (
            f"First paragraph carries a cite [event:{eid}].\n\nSecond paragraph forgot to cite anything at all."
        ),
    }

    session = AsyncMock()

    async def _exec(stmt: Any) -> Any:
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [node]
        result.scalars.return_value = scalars
        return result

    session.execute = _exec
    findings = await wiki_lint.check_missing_cite(
        session,
        tenant_id=tenant,
        engagement_id=eng,
    )
    assert len(findings) == 1
    kind, target_kind, target_id, detail = findings[0]
    assert kind == "missing_cite"
    assert target_kind == "matrix_node"
    assert target_id == node_id
    assert detail["paragraph_index"] == 1
    assert detail["total_paragraphs"] == 2


@pytest.mark.asyncio
async def test_check_missing_cite_skips_empty_descriptions() -> None:
    tenant = uuid.uuid4()
    eng = uuid.uuid4()
    node = MagicMock()
    node.id = uuid.uuid4()
    node.attributes = {}

    session = AsyncMock()

    async def _exec(stmt: Any) -> Any:
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [node]
        result.scalars.return_value = scalars
        return result

    session.execute = _exec
    findings = await wiki_lint.check_missing_cite(
        session,
        tenant_id=tenant,
        engagement_id=eng,
    )
    assert findings == []


@pytest.mark.asyncio
async def test_check_contradictions_pairs_opposite_stances() -> None:
    tenant = uuid.uuid4()
    eng = uuid.uuid4()
    shared_node = uuid.uuid4()
    now = datetime.now(UTC)

    approve = MagicMock()
    approve.id = uuid.uuid4()
    approve.body = "Steering committee approved the migration plan."
    approve.citation_node_ids = [shared_node]
    approve.citation_event_ids = []
    approve.created_at = now
    approve.agent = "kenny"

    reject = MagicMock()
    reject.id = uuid.uuid4()
    reject.body = "Migration was rejected after a follow-up cost review."
    reject.citation_node_ids = [shared_node]
    reject.citation_event_ids = []
    reject.created_at = now
    reject.agent = "kenny"

    session = AsyncMock()

    async def _exec(stmt: Any) -> Any:
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [approve, reject]
        result.scalars.return_value = scalars
        return result

    session.execute = _exec
    findings = await wiki_lint.check_contradictions(
        session,
        tenant_id=tenant,
        engagement_id=eng,
    )
    assert len(findings) == 1
    kind, target_kind, _target_id, detail = findings[0]
    assert kind == "contradiction"
    assert target_kind == "matrix_insight"
    assert detail["other_insight_id"] == str(reject.id)
    assert detail["a_stance"] == "approval"
    assert detail["b_stance"] == "rejection"


@pytest.mark.asyncio
async def test_check_contradictions_ignores_same_stance() -> None:
    tenant = uuid.uuid4()
    eng = uuid.uuid4()
    shared_node = uuid.uuid4()
    now = datetime.now(UTC)

    a = MagicMock()
    a.id = uuid.uuid4()
    a.body = "Plan approved on Tuesday."
    a.citation_node_ids = [shared_node]
    a.citation_event_ids = []
    a.created_at = now

    b = MagicMock()
    b.id = uuid.uuid4()
    b.body = "Also approved on the same call."
    b.citation_node_ids = [shared_node]
    b.citation_event_ids = []
    b.created_at = now

    session = AsyncMock()

    async def _exec(stmt: Any) -> Any:
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [a, b]
        result.scalars.return_value = scalars
        return result

    session.execute = _exec
    findings = await wiki_lint.check_contradictions(
        session,
        tenant_id=tenant,
        engagement_id=eng,
    )
    assert findings == []


@pytest.mark.asyncio
async def test_check_contradictions_ignores_no_overlap() -> None:
    tenant = uuid.uuid4()
    eng = uuid.uuid4()
    now = datetime.now(UTC)

    a = MagicMock()
    a.id = uuid.uuid4()
    a.body = "Plan approved."
    a.citation_node_ids = [uuid.uuid4()]
    a.citation_event_ids = []
    a.created_at = now

    b = MagicMock()
    b.id = uuid.uuid4()
    b.body = "Different plan rejected."
    b.citation_node_ids = [uuid.uuid4()]
    b.citation_event_ids = []
    b.created_at = now

    session = AsyncMock()

    async def _exec(stmt: Any) -> Any:
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [a, b]
        result.scalars.return_value = scalars
        return result

    session.execute = _exec
    findings = await wiki_lint.check_contradictions(
        session,
        tenant_id=tenant,
        engagement_id=eng,
    )
    assert findings == []


def test_unresolved_citations_helper_skips_empty_prose() -> None:
    # Pure-Python guard: parsing returns empty list for blank input.
    assert wiki_lint._parse_citations("") == []


def test_citation_kind_filter_excludes_unknown() -> None:
    """Sanity: only the four supported cite kinds are parsed."""
    text = f"[unknown:{uuid.uuid4()}]"
    assert wiki_lint._parse_citations(text) == []


def test_citation_record_is_hashable() -> None:
    cid = uuid.uuid4()
    cite = Citation(kind="event", id=cid)
    assert hash(cite) == hash(Citation(kind="event", id=cid))
