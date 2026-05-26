"""Integration: Phase 5 Wave 1A — ``tenant_mcp_configs`` schema lands cleanly.

Covers (scope-v2 §9.1):

1. Migration creates the table with the expected columns + check
   constraints (connector_kind + transport).
2. ORM insert + Pydantic ``TenantMcpConfigRead`` round-trip.
3. Unique ``(tenant_id, name)`` is enforced.
4. ``ON DELETE CASCADE`` fires when the parent ``app_tenants`` row is
   removed.
5. RLS policy ``tenant_rls_tenant_mcp_configs`` rejects cross-tenant
   reads under the low-privilege ``deployai_app`` role (mirrors the
   ``test_tenant_isolation.test_cross_tenant_read_filtered`` style).

Run with ``uv run pytest -m integration``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Generator

import pytest
import pytest_asyncio
from deployai_tenancy import TenantScopedSession
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import Session

from control_plane.domain.mcp_outbound import (
    CONNECTOR_KINDS,
    TenantMcpConfig,
    TenantMcpConfigRead,
)

pytestmark = pytest.mark.integration


TENANT_A = uuid.UUID("00000000-0000-7000-8000-0000000000aa")
TENANT_B = uuid.UUID("00000000-0000-7000-8000-0000000000bb")
_APP_PASSWORD = "deployai-app-test"


def _seed_tenant(conn: object, tenant_id: uuid.UUID, *, name: str = "mcp-test") -> None:
    conn.execute(  # type: ignore[attr-defined]
        text("INSERT INTO app_tenants (id, name) VALUES (:t, :n)"),
        {"t": str(tenant_id), "n": name},
    )


# ---------------------------------------------------------------------------
# AC1 — table + check constraints exist
# ---------------------------------------------------------------------------


def test_tenant_mcp_configs_table_exists_with_expected_columns(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'tenant_mcp_configs'"
            )
        ).all()
    columns = {r.column_name: (r.data_type, r.is_nullable) for r in rows}
    expected_columns = {
        "id",
        "tenant_id",
        "name",
        "connector_kind",
        "transport",
        "endpoint",
        "encrypted_auth_token",
        "allowed_tools",
        "enabled",
        "created_at",
        "updated_at",
    }
    assert expected_columns.issubset(columns.keys()), f"missing columns: {expected_columns - columns.keys()}"
    # The bytea column is nullable per Wave 1A (Wave 2D wires the
    # tenant-DEK encryption that populates it).
    assert columns["encrypted_auth_token"] == ("bytea", "YES")
    # ARRAY columns surface as USER-DEFINED on some PG versions; the
    # element type is exposed via element_types — assert it's not NOT
    # NULL because null = "all tools allowed".
    assert columns["allowed_tools"][1] == "YES"
    assert columns["enabled"][1] == "NO"


def test_tenant_mcp_configs_indexes_exist(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'tenant_mcp_configs'")
        ).all()
    names = {r.indexname for r in rows}
    # Hot-path lookup index + the unique constraint's backing index.
    assert {"idx_tenant_mcp_configs_tenant_id_enabled"}.issubset(names)
    assert {"uq_tenant_mcp_configs_tenant_id_name"}.issubset(names)


def test_connector_kind_check_rejects_unknown(postgres_engine: Engine) -> None:
    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as conn:
            _seed_tenant(conn, TENANT_A)
            conn.execute(
                text(
                    "INSERT INTO tenant_mcp_configs "
                    "(tenant_id, name, connector_kind, endpoint) "
                    "VALUES (:t, 'bad', 'bogus_connector', 'https://x')"
                ),
                {"t": str(TENANT_A)},
            )


def test_transport_check_rejects_unknown(postgres_engine: Engine) -> None:
    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as conn:
            _seed_tenant(conn, TENANT_A)
            conn.execute(
                text(
                    "INSERT INTO tenant_mcp_configs "
                    "(tenant_id, name, connector_kind, transport, endpoint) "
                    "VALUES (:t, 'bad', 'slack', 'carrier_pigeon', 'https://x')"
                ),
                {"t": str(TENANT_A)},
            )


def test_every_catalogued_connector_kind_accepted(postgres_engine: Engine) -> None:
    """Every entry in ``CONNECTOR_KINDS`` round-trips — guards against the
    ORM constant + the CHECK constraint drifting apart silently.
    """
    with postgres_engine.begin() as conn:
        _seed_tenant(conn, TENANT_A)
        for kind in CONNECTOR_KINDS:
            conn.execute(
                text(
                    "INSERT INTO tenant_mcp_configs "
                    "(tenant_id, name, connector_kind, endpoint) "
                    "VALUES (:t, :n, :k, 'https://example')"
                ),
                {"t": str(TENANT_A), "n": f"acme-{kind}", "k": kind},
            )

    with postgres_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM tenant_mcp_configs WHERE tenant_id = :t"),
            {"t": str(TENANT_A)},
        ).scalar_one()
    assert count == len(CONNECTOR_KINDS)


# ---------------------------------------------------------------------------
# AC2 — ORM insert + Pydantic round-trip
# ---------------------------------------------------------------------------


def test_orm_insert_round_trips_through_read_schema(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as conn:
        _seed_tenant(conn, TENANT_A)

    with Session(postgres_engine, expire_on_commit=False) as session:
        row = TenantMcpConfig(
            tenant_id=TENANT_A,
            name="Acme Slack",
            connector_kind="slack",
            endpoint="https://slack-mcp.example.com/sse",
            allowed_tools=["search_messages", "post_message"],
        )
        session.add(row)
        session.commit()
        session.refresh(row)

    read = TenantMcpConfigRead.from_orm_row(row)
    assert read.tenant_id == TENANT_A
    assert read.name == "Acme Slack"
    assert read.connector_kind == "slack"
    assert read.transport == "http_sse"  # server-side default
    assert read.endpoint == "https://slack-mcp.example.com/sse"
    assert read.has_auth_token is False  # not supplied
    assert read.allowed_tools == ["search_messages", "post_message"]
    assert read.enabled is True
    assert read.created_at is not None
    assert read.updated_at is not None


# ---------------------------------------------------------------------------
# AC3 — UNIQUE (tenant_id, name)
# ---------------------------------------------------------------------------


def test_unique_tenant_id_name_enforced(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as conn:
        _seed_tenant(conn, TENANT_A)
        conn.execute(
            text(
                "INSERT INTO tenant_mcp_configs "
                "(tenant_id, name, connector_kind, endpoint) "
                "VALUES (:t, 'Acme Slack', 'slack', 'https://x')"
            ),
            {"t": str(TENANT_A)},
        )

    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tenant_mcp_configs "
                    "(tenant_id, name, connector_kind, endpoint) "
                    "VALUES (:t, 'Acme Slack', 'linear', 'https://y')"
                ),
                {"t": str(TENANT_A)},
            )

    # Same name under a *different* tenant is fine — uniqueness is
    # scoped per tenant by design.
    with postgres_engine.begin() as conn:
        _seed_tenant(conn, TENANT_B, name="mcp-test-b")
        conn.execute(
            text(
                "INSERT INTO tenant_mcp_configs "
                "(tenant_id, name, connector_kind, endpoint) "
                "VALUES (:t, 'Acme Slack', 'slack', 'https://x')"
            ),
            {"t": str(TENANT_B)},
        )


# ---------------------------------------------------------------------------
# AC4 — ON DELETE CASCADE on app_tenants
# ---------------------------------------------------------------------------


def test_app_tenants_delete_cascades_to_mcp_configs(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as conn:
        _seed_tenant(conn, TENANT_A)
        conn.execute(
            text(
                "INSERT INTO tenant_mcp_configs "
                "(tenant_id, name, connector_kind, endpoint) "
                "VALUES (:t, 'Acme Slack', 'slack', 'https://x')"
            ),
            {"t": str(TENANT_A)},
        )

    with postgres_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM app_tenants WHERE id = :t"),
            {"t": str(TENANT_A)},
        )

    with postgres_engine.connect() as conn:
        remaining = conn.execute(
            text("SELECT count(*) FROM tenant_mcp_configs WHERE tenant_id = :t"),
            {"t": str(TENANT_A)},
        ).scalar_one()
    assert remaining == 0


# ---------------------------------------------------------------------------
# AC5 — RLS rejects cross-tenant reads under the deployai_app role
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _configure_app_role(postgres_engine: Engine) -> Generator[None]:
    """Flip ``deployai_app`` to LOGIN with a test password — mirrors the
    Story 1.9 ``test_tenant_isolation`` fixture.
    """
    with postgres_engine.begin() as conn:
        conn.execute(text(f"ALTER ROLE deployai_app WITH LOGIN PASSWORD '{_APP_PASSWORD}'"))
    yield


@pytest.fixture
def sync_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.render_as_string(hide_password=False)


def _async_url_for(sync_url: str, *, user: str, password: str) -> str:
    remainder = sync_url.split("@", 1)[1]
    return f"postgresql+psycopg://{user}:{password}@{remainder}"


@pytest_asyncio.fixture
async def app_engine(sync_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        _async_url_for(sync_url, user="deployai_app", password=_APP_PASSWORD),
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def _seed_two_tenant_rows(postgres_engine: Engine) -> None:
    """Insert one MCP config per tenant as superuser (bypasses RLS)."""
    with postgres_engine.begin() as conn:
        for tenant in (TENANT_A, TENANT_B):
            _seed_tenant(conn, tenant, name=f"mcp-test-{tenant}")
            conn.execute(
                text(
                    "INSERT INTO tenant_mcp_configs "
                    "(tenant_id, name, connector_kind, endpoint) "
                    "VALUES (:t, 'seed-mcp', 'slack', 'https://seed')"
                ),
                {"t": str(tenant)},
            )


async def test_rls_blocks_cross_tenant_read(app_engine: AsyncEngine, _seed_two_tenant_rows: None) -> None:
    """Scoped to tenant B, a tenant-A row must be invisible — same
    assertion shape as ``test_tenant_isolation.test_cross_tenant_read_filtered``.
    """
    async with TenantScopedSession(TENANT_B, app_engine) as session:
        result = await session.execute(
            text("SELECT tenant_id FROM tenant_mcp_configs WHERE tenant_id = :t"),
            {"t": str(TENANT_A)},
        )
        assert result.first() is None

    # And the same session sees its own row.
    async with TenantScopedSession(TENANT_B, app_engine) as session:
        result = await session.execute(text("SELECT count(*) FROM tenant_mcp_configs"))
        assert result.scalar_one() == 1


async def test_rls_blocks_cross_tenant_write(app_engine: AsyncEngine, _seed_two_tenant_rows: None) -> None:
    """Tenant B's scope cannot insert a row tagged for tenant A — the
    ``WITH CHECK`` clause of the policy fires as SQLSTATE 42501.
    """
    async with TenantScopedSession(TENANT_B, app_engine) as session:
        with pytest.raises(DBAPIError) as excinfo:
            await session.execute(
                text(
                    "INSERT INTO tenant_mcp_configs "
                    "(tenant_id, name, connector_kind, endpoint) "
                    "VALUES (:t, 'smuggled', 'slack', 'https://x')"
                ),
                {"t": str(TENANT_A)},
            )
        sqlstate = getattr(excinfo.value.orig, "sqlstate", None)
        assert sqlstate == "42501", f"expected SQLSTATE 42501; got {sqlstate!r}"


async def test_rls_fails_closed_without_scope(app_engine: AsyncEngine) -> None:
    """``deployai_app`` has no BYPASSRLS — no scope ⇒ zero rows visible."""
    async with app_engine.connect() as conn:
        result = await conn.execute(text("SELECT count(*) FROM tenant_mcp_configs"))
        assert result.scalar_one() == 0
