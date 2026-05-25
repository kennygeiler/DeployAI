"""Unit tests for export Markdown + PDF renderers (Phase C inc 13.1)."""

from __future__ import annotations

from typing import Any

import pytest

from control_plane.export.renderer import render_markdown, render_pdf


def _weasyprint_loads() -> bool:
    try:
        import weasyprint  # noqa: F401
    except OSError:
        return False
    return True


_FIXTURE: dict[str, Any] = {
    "engagement": {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "NYC DOT LiDAR rollout",
        "customer_account": "NYC DOT",
        "current_phase": "P2_scoping",
        "created_at": "2026-05-01T10:00:00+00:00",
    },
    "members": [
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "user_id": "33333333-3333-3333-3333-333333333333",
            "role": "deployment_strategist",
        }
    ],
    "matrix_nodes": [
        {
            "id": "44444444-4444-4444-4444-444444444444",
            "node_type": "stakeholder",
            "title": "Jane Sponsor",
            "status": None,
            "attributes": {"title": "VP"},
        }
    ],
    "matrix_edges": [
        {
            "id": "55555555-5555-5555-5555-555555555555",
            "edge_type": "sponsors",
            "from_node_id": "44444444-4444-4444-4444-444444444444",
            "to_node_id": "66666666-6666-6666-6666-666666666666",
            "attributes": {},
        }
    ],
    "insights": [
        {
            "id": "77777777-7777-7777-7777-777777777777",
            "agent": "oracle",
            "insight_type": "risk",
            "severity": "high",
            "title": "Sponsor at risk",
            "body": "VP is leaving",
            "status": "open",
        }
    ],
    "recent_activity_events": [
        {
            "id": "88888888-8888-8888-8888-888888888888",
            "actor_id": "33333333-3333-3333-3333-333333333333",
            "category": "matrix.node.create",
            "summary": "Created stakeholder Jane Sponsor",
            "created_at": "2026-05-02T11:00:00+00:00",
        }
    ],
}


def test_render_markdown_contains_all_sections() -> None:
    md = render_markdown(_FIXTURE)
    assert "# NYC DOT LiDAR rollout" in md
    assert "## Members" in md
    assert "## Matrix nodes" in md
    assert "## Matrix edges" in md
    assert "## Insights" in md
    assert "## Recent activity" in md
    assert "deployment_strategist" in md
    assert "Jane Sponsor" in md
    assert "sponsors" in md
    assert "Sponsor at risk" in md
    assert "matrix.node.create" in md


def test_render_markdown_empty_sections() -> None:
    empty: dict[str, Any] = {
        "engagement": {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Empty",
            "customer_account": None,
            "current_phase": "P1_pre_engagement",
            "created_at": None,
        },
        "members": [],
        "matrix_nodes": [],
        "matrix_edges": [],
        "insights": [],
        "recent_activity_events": [],
    }
    md = render_markdown(empty)
    assert "_no members_" in md
    assert "_no nodes_" in md
    assert "_no edges_" in md
    assert "_no insights_" in md
    assert "_no recent activity_" in md


@pytest.mark.skipif(not _weasyprint_loads(), reason="weasyprint native libs (cairo/pango) unavailable")
def test_render_pdf_returns_pdf_bytes() -> None:
    md = render_markdown(_FIXTURE)
    pdf = render_pdf(md)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-")
