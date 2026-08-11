"""Unit tests for the LangGraph runtime plumbing (pilot-refresh D1-D4).

No LLM, no DB — covers the approval policy, thread-id scheme, runtime
selector, the new SSE frame, conninfo normalization, and the guard that
pins our captured checkpoint DDL to the installed library version.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime

import pytest

from control_plane.agents.agent_kenny.approvals import (
    approval_required_for,
    build_approval_payload,
    summarize_args,
)
from control_plane.agents.agent_kenny.checkpointer import checkpointer_conninfo
from control_plane.agents.agent_kenny.runtime import (
    AGENT_RUNTIME_ENV,
    GRAPH_RECURSION_LIMIT,
    RUNTIME_LANGGRAPH,
    RUNTIME_LEGACY,
    _state_update,
    agent_runtime,
    build_thread_id,
    parse_thread_id,
)
from control_plane.agents.agent_kenny.stream import format_chunk
from control_plane.agents.agent_kenny.types import (
    MAX_REVISION_ATTEMPTS,
    MAX_TOOL_CALLS_PER_TURN,
    AgentState,
    ApprovalRequiredChunk,
)

# --- approval policy ----------------------------------------------------------


def test_external_write_tools_require_approval() -> None:
    assert approval_required_for("slack__send_message") is True
    assert approval_required_for("linear__create-issue") is True
    assert approval_required_for("github__add_comment") is True
    assert approval_required_for("notion__update_page") is True


def test_external_read_tools_do_not_require_approval() -> None:
    assert approval_required_for("slack__search_messages") is False
    assert approval_required_for("gdrive__get_file") is False
    assert approval_required_for("github__list_issues") is False


def test_internal_tools_never_require_approval_by_default() -> None:
    assert approval_required_for("query_ledger") is False
    assert approval_required_for("get_engagement_summary") is False
    assert approval_required_for("propose_action") is False


def test_env_override_forces_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_AGENT_APPROVAL_TOOLS", "propose_action, slack__search_messages")
    assert approval_required_for("propose_action") is True
    assert approval_required_for("slack__search_messages") is True
    assert approval_required_for("query_ledger") is False


def test_summarize_args_truncates() -> None:
    rendered = summarize_args({"body": "x" * 1000})
    assert len(rendered) <= 420
    assert rendered.endswith("...(truncated)")


def test_build_approval_payload_single_and_batch() -> None:
    single = build_approval_payload([{"name": "slack__send_message", "input": {"channel": "#deals"}}])
    assert single["tool"] == "slack__send_message"
    assert "slack__send_message" in single["question"]
    assert "#deals" in single["args_summary"]

    batch = build_approval_payload(
        [
            {"name": "slack__send_message", "input": {"channel": "#a"}},
            {"name": "linear__create_issue", "input": {"title": "t"}},
        ]
    )
    assert batch["tool"] == "slack__send_message"
    assert "2 write-capable tools" in batch["question"]
    assert "linear__create_issue" in batch["args_summary"]


# --- runtime selector + thread ids -------------------------------------------


def test_agent_runtime_defaults_to_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(AGENT_RUNTIME_ENV, raising=False)
    assert agent_runtime() == RUNTIME_LEGACY
    monkeypatch.setenv(AGENT_RUNTIME_ENV, "langgraph")
    assert agent_runtime() == RUNTIME_LANGGRAPH
    monkeypatch.setenv(AGENT_RUNTIME_ENV, "LangGraph")
    assert agent_runtime() == RUNTIME_LANGGRAPH
    monkeypatch.setenv(AGENT_RUNTIME_ENV, "something-else")
    assert agent_runtime() == RUNTIME_LEGACY


def test_thread_id_round_trip() -> None:
    t, e = uuid.uuid4(), uuid.uuid4()
    for key in (str(uuid.uuid4()), f"turn-{uuid.uuid4()}"):
        thread_id = build_thread_id(t, e, key)
        parsed = parse_thread_id(thread_id)
        assert parsed == (t, e, key)


def test_parse_thread_id_rejects_malformed() -> None:
    assert parse_thread_id("nonsense") is None
    assert parse_thread_id("tenant:abc:engagement:def:conversation:x") is None
    assert parse_thread_id("") is None


def test_recursion_limit_covers_worst_case_supersteps() -> None:
    # retrieve + capped llm/dispatch loop + capped citation loop +
    # adversarial + persist, with headroom.
    worst_case = 1 + (2 * MAX_TOOL_CALLS_PER_TURN + 1) + 3 * (MAX_REVISION_ATTEMPTS + 1) + 2
    assert GRAPH_RECURSION_LIMIT >= worst_case


# --- state channel projection -------------------------------------------------


def test_state_update_excludes_external_tools() -> None:
    state = AgentState(
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        user_message="hi",
        started_at=datetime(2026, 8, 11, tzinfo=UTC),
    )
    state.external_tools = [object()]
    update = _state_update(state)
    assert "external_tools" not in update
    expected_fields = {f.name for f in dataclasses.fields(AgentState)} - {"external_tools"}
    assert set(update) == expected_fields


# --- SSE frame ----------------------------------------------------------------


def test_approval_required_frame_shape() -> None:
    frame = format_chunk(
        ApprovalRequiredChunk(
            question="Allow?",
            tool="slack__send_message",
            args_summary='{"channel": "#deals"}',
            thread_id="tenant:t:engagement:e:conversation:c",
        )
    )
    text = frame.decode()
    assert text.startswith("event: approval_required\n")
    assert '"question":"Allow?"' in text
    assert '"tool":"slack__send_message"' in text
    assert '"thread_id":"tenant:t:engagement:e:conversation:c"' in text
    assert text.endswith("\n\n")


# --- checkpointer -------------------------------------------------------------


def test_conninfo_strips_sqlalchemy_driver_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host:5432/db")
    assert checkpointer_conninfo() == "postgresql://u:p@host:5432/db"
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host/db")
    assert checkpointer_conninfo() == "postgresql://u:p@host/db"
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db")
    assert checkpointer_conninfo() == "postgresql://u:p@host/db"


def test_migration_ddl_matches_installed_library_version() -> None:
    """Migration 20260811_0054 captured langgraph-checkpoint-postgres's
    MIGRATIONS list at 10 entries (indexes 0-9, all pre-seeded into
    checkpoint_migrations). If a library upgrade adds migrations, this
    fails so the new DDL gets captured into a follow-up Alembic migration
    instead of silently diverging from what the saver expects."""
    from langgraph.checkpoint.postgres.base import BasePostgresSaver

    assert len(BasePostgresSaver.MIGRATIONS) == 10, (
        "langgraph-checkpoint-postgres MIGRATIONS changed; add a new Alembic "
        "migration capturing the new statements (see 20260811_0054)"
    )
