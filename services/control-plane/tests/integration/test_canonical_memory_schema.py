"""Integration tests for Story 1.8 canonical memory schema.

Run with ``uv run pytest -m integration tests/integration/`` after starting
Docker. The default ``pytest`` invocation excludes the ``integration``
marker (see ``pyproject.toml``), so CI's unit gate stays hermetic.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = pytest.mark.integration


def _insert_event(conn: Any, tenant_id: uuid.UUID, *, event_type: str = "meeting.held") -> uuid.UUID:
    row = conn.execute(
        text(
            """
            INSERT INTO canonical_memory_events (tenant_id, event_type, occurred_at)
            VALUES (:tenant_id, :event_type, now())
            RETURNING id
            """
        ),
        {"tenant_id": tenant_id, "event_type": event_type},
    ).one()
    return row.id


# ---------------------------------------------------------------------------
# AC12 #1 — happy-path inserts
# ---------------------------------------------------------------------------


def test_canonical_memory_event_inserts_with_uuid_v7_default(postgres_engine: Engine, tenant_id: uuid.UUID) -> None:
    with postgres_engine.begin() as conn:
        event_id = _insert_event(conn, tenant_id)
        row = conn.execute(
            text("SELECT id, tenant_id, created_at, event_type FROM canonical_memory_events WHERE id = :id"),
            {"id": event_id},
        ).one()

    assert row.id == event_id
    assert row.tenant_id == tenant_id
    assert row.created_at is not None
    assert row.event_type == "meeting.held"
    # UUID v7 marker: version nibble is 7.
    assert (event_id.int >> 76) & 0xF == 7


# ---------------------------------------------------------------------------
# AC12 #2 + #3 — append-only trigger fires on UPDATE and DELETE
# ---------------------------------------------------------------------------


def test_canonical_memory_event_update_is_rejected(postgres_engine: Engine, tenant_id: uuid.UUID) -> None:
    with postgres_engine.begin() as conn:
        event_id = _insert_event(conn, tenant_id)

    with pytest.raises(DBAPIError) as exc_info:
        with postgres_engine.begin() as conn:
            conn.execute(
                text("UPDATE canonical_memory_events SET event_type = 'mutated' WHERE id = :id"),
                {"id": event_id},
            )
    assert "append-only" in str(exc_info.value)


def test_canonical_memory_event_delete_is_rejected(postgres_engine: Engine, tenant_id: uuid.UUID) -> None:
    with postgres_engine.begin() as conn:
        event_id = _insert_event(conn, tenant_id)

    with pytest.raises(DBAPIError) as exc_info:
        with postgres_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM canonical_memory_events WHERE id = :id"),
                {"id": event_id},
            )
    assert "append-only" in str(exc_info.value)


# ---------------------------------------------------------------------------
# AC12 #4 — UUID v7 is monotonically K-sortable across inserts
# ---------------------------------------------------------------------------


def _uuid_v7_ts_ms(u: uuid.UUID) -> int:
    """Extract the 48-bit unix_ts_ms prefix from a UUID v7."""

    return int.from_bytes(u.bytes[:6], "big")


def test_uuid_v7_timestamp_prefix_is_monotonic(postgres_engine: Engine, tenant_id: uuid.UUID) -> None:
    """UUID v7 guarantees K-sortability on the 48-bit ms timestamp prefix.

    Per RFC 9562 §5.7, byte-wise order within the same millisecond is
    implementation-defined — only the 48-bit ms prefix is strictly
    non-decreasing. Spread inserts across separate transactions so
    ``clock_timestamp()`` advances between calls; the assertion then
    tests the K-sortable contract without relying on submillisecond
    monotonicity (which our plpgsql implementation does not provide).
    """

    ids: list[uuid.UUID] = []
    for _ in range(5):
        with postgres_engine.begin() as conn:
            ids.append(_insert_event(conn, tenant_id))

    # Every id must be version 7.
    for u in ids:
        assert (u.int >> 76) & 0xF == 7

    # 48-bit ms prefix is strictly non-decreasing across inserts.
    for earlier, later in pairwise(ids):
        assert _uuid_v7_ts_ms(earlier) <= _uuid_v7_ts_ms(later), (
            f"UUID v7 timestamp prefix regressed: {earlier} !<= {later}"
        )


# ---------------------------------------------------------------------------
# AC12 #5 — identity_attribute_history open-row uniqueness + versioning
# ---------------------------------------------------------------------------


def test_identity_attribute_history_open_row_uniqueness(postgres_engine: Engine, tenant_id: uuid.UUID) -> None:
    now = datetime.now(UTC)

    with postgres_engine.begin() as conn:
        identity_id = conn.execute(
            text(
                """
                INSERT INTO identity_nodes (tenant_id, canonical_name, primary_email_hash)
                VALUES (:tenant_id, 'Dana Carter', 'sha256:deadbeef')
                RETURNING id
                """
            ),
            {"tenant_id": tenant_id},
        ).scalar_one()

        conn.execute(
            text(
                """
                INSERT INTO identity_attribute_history
                    (tenant_id, identity_id, attribute_name, attribute_value, valid_from)
                VALUES (:tenant_id, :identity_id, 'role', 'chief-of-staff', :valid_from)
                """
            ),
            {"tenant_id": tenant_id, "identity_id": identity_id, "valid_from": now - timedelta(days=30)},
        )

    # Second OPEN row for the same (identity, attribute) violates the partial-unique index.
    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO identity_attribute_history
                        (tenant_id, identity_id, attribute_name, attribute_value, valid_from)
                    VALUES (:tenant_id, :identity_id, 'role', 'deputy-chief-of-staff', :valid_from)
                    """
                ),
                {"tenant_id": tenant_id, "identity_id": identity_id, "valid_from": now},
            )

    # Closing the first open row then opening a new one succeeds.
    with postgres_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE identity_attribute_history SET valid_to = :closed_at "
                "WHERE identity_id = :identity_id AND attribute_name = 'role' AND valid_to IS NULL"
            ),
            {"identity_id": identity_id, "closed_at": now},
        )
        conn.execute(
            text(
                """
                INSERT INTO identity_attribute_history
                    (tenant_id, identity_id, attribute_name, attribute_value, valid_from)
                VALUES (:tenant_id, :identity_id, 'role', 'deputy-chief-of-staff', :valid_from)
                """
            ),
            {"tenant_id": tenant_id, "identity_id": identity_id, "valid_from": now},
        )

    with postgres_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT attribute_value, valid_to FROM identity_attribute_history "
                "WHERE identity_id = :identity_id ORDER BY valid_from ASC"
            ),
            {"identity_id": identity_id},
        ).all()
    assert len(rows) == 2
    assert rows[0].valid_to is not None  # closed
    assert rows[1].valid_to is None  # current


# ---------------------------------------------------------------------------
# AC12 #6 — identity_supersessions CHECK (different_ids)
# ---------------------------------------------------------------------------


def test_identity_supersession_rejects_self_link(postgres_engine: Engine, tenant_id: uuid.UUID) -> None:
    with postgres_engine.begin() as conn:
        identity_id = conn.execute(
            text(
                """
                INSERT INTO identity_nodes (tenant_id, canonical_name, primary_email_hash)
                VALUES (:tenant_id, 'Dana Carter', 'sha256:deadbeef')
                RETURNING id
                """
            ),
            {"tenant_id": tenant_id},
        ).scalar_one()

    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO identity_supersessions
                        (tenant_id, superseded_identity_id, canonical_identity_id, reason)
                    VALUES (:tenant_id, :id, :id, 'self-link should fail')
                    """
                ),
                {"tenant_id": tenant_id, "id": identity_id},
            )


def test_identity_supersession_resolves_duplicate_to_canonical(postgres_engine: Engine, tenant_id: uuid.UUID) -> None:
    with postgres_engine.begin() as conn:
        canonical_id = conn.execute(
            text(
                "INSERT INTO identity_nodes (tenant_id, canonical_name, primary_email_hash) "
                "VALUES (:t, 'Dana Carter', 'sha256:aaaa') RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar_one()
        duplicate_id = conn.execute(
            text(
                "INSERT INTO identity_nodes (tenant_id, canonical_name, primary_email_hash, is_canonical) "
                "VALUES (:t, 'D. Carter', 'sha256:bbbb', false) RETURNING id"
            ),
            {"t": tenant_id},
        ).scalar_one()
        conn.execute(
            text(
                """
                INSERT INTO identity_supersessions
                    (tenant_id, superseded_identity_id, canonical_identity_id, reason)
                VALUES (:t, :dup, :canon, 'merge: same primary_email_hash')
                """
            ),
            {"t": tenant_id, "dup": duplicate_id, "canon": canonical_id},
        )

    with postgres_engine.connect() as conn:
        resolved = conn.execute(
            text(
                """
                SELECT canonical_identity_id
                FROM identity_supersessions
                WHERE superseded_identity_id = :dup
                """
            ),
            {"dup": duplicate_id},
        ).scalar_one()
    assert resolved == canonical_id


# ---------------------------------------------------------------------------
# AC12 #7 — learning_state_t enum rejects bogus values
# ---------------------------------------------------------------------------


def test_solidified_learning_enum_rejects_unknown_state(postgres_engine: Engine, tenant_id: uuid.UUID) -> None:
    with pytest.raises(DBAPIError):
        with postgres_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO solidified_learnings
                        (tenant_id, belief, evidence_event_ids, state)
                    VALUES (:t, 'test belief', ARRAY[]::uuid[], 'bogus'::learning_state_t)
                    """
                ),
                {"t": tenant_id},
            )


# ---------------------------------------------------------------------------
# AC12 #8 — lifecycle transition append + state update
# ---------------------------------------------------------------------------


def test_learning_lifecycle_transition_end_to_end(postgres_engine: Engine, tenant_id: uuid.UUID) -> None:
    with postgres_engine.begin() as conn:
        event_id = _insert_event(conn, tenant_id, event_type="decision.recorded")

        learning_id = conn.execute(
            text(
                """
                INSERT INTO solidified_learnings
                    (tenant_id, belief, evidence_event_ids)
                VALUES (:t, 'pilot scope locked', ARRAY[:ev]::uuid[])
                RETURNING id
                """
            ),
            {"t": tenant_id, "ev": event_id},
        ).scalar_one()

        conn.execute(
            text(
                """
                INSERT INTO learning_lifecycle_states
                    (tenant_id, learning_id, state, transitioned_at, reason)
                VALUES (:t, :l, 'solidified', now(), 'two independent witnesses')
                """
            ),
            {"t": tenant_id, "l": learning_id},
        )
        conn.execute(
            text("UPDATE solidified_learnings SET state = 'solidified' WHERE id = :l"),
            {"l": learning_id},
        )

    with postgres_engine.connect() as conn:
        current_state = conn.execute(
            text("SELECT state FROM solidified_learnings WHERE id = :l"),
            {"l": learning_id},
        ).scalar_one()
        transitions = conn.execute(
            text(
                "SELECT state, reason FROM learning_lifecycle_states "
                "WHERE learning_id = :l ORDER BY transitioned_at ASC"
            ),
            {"l": learning_id},
        ).all()

    assert str(current_state) == "solidified"
    assert len(transitions) == 1
    assert str(transitions[0].state) == "solidified"


# ---------------------------------------------------------------------------
# AC12 #9 — tombstone bytea roundtrip
# ---------------------------------------------------------------------------


def test_tombstone_inserts_with_bytea_signature(postgres_engine: Engine, tenant_id: uuid.UUID) -> None:
    authority_actor_id = uuid.uuid4()
    original_node_id = uuid.uuid4()
    signature = b"\x00\x01\x02\x03ed25519-sig-bytes"

    with postgres_engine.begin() as conn:
        row_id = conn.execute(
            text(
                """
                INSERT INTO tombstones
                    (tenant_id, original_node_id, retention_reason,
                     authority_actor_id, destroyed_at, signature)
                VALUES (:t, :orig, 'NFR33 7-year retention', :actor, now(), :sig)
                RETURNING id
                """
            ),
            {
                "t": tenant_id,
                "orig": original_node_id,
                "actor": authority_actor_id,
                "sig": signature,
            },
        ).scalar_one()

    with postgres_engine.connect() as conn:
        row = conn.execute(
            text("SELECT signature, tsa_timestamp FROM tombstones WHERE id = :id"),
            {"id": row_id},
        ).one()
    assert bytes(row.signature) == signature
    assert row.tsa_timestamp is None  # Story 1.13 populates.


# ---------------------------------------------------------------------------
# AC12 bonus — schema_proposals stub accepts rows (Story 1.17 owns the flow)
# ---------------------------------------------------------------------------


def test_schema_proposals_stub_accepts_rows(postgres_engine: Engine, tenant_id: uuid.UUID) -> None:
    proposer_id = uuid.uuid4()
    with postgres_engine.begin() as conn:
        row_id = conn.execute(
            text(
                """
                INSERT INTO schema_proposals
                    (tenant_id, proposer_actor_id, proposed_ddl)
                VALUES (:t, :p, 'ALTER TABLE canonical_memory_events ADD COLUMN foo text')
                RETURNING id
                """
            ),
            {"t": tenant_id, "p": proposer_id},
        ).scalar_one()

    with postgres_engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM schema_proposals WHERE id = :id"),
            {"id": row_id},
        ).scalar_one()
    assert status == "pending"
