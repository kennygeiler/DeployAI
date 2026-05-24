"""Internal API — tenants / portfolio insights (Phase 7 increment 7.4).

Mounted under ``/internal/v1``. Requires ``X-DeployAI-Internal-Key``; the
``{tenant_id}`` path segment scopes every query.

The per-engagement Oracle (7.2) lives in ``engagements_internal.py`` —
this module holds the *tenant-scoped* counterpart: the Master Strategist
cross-engagement insights, plus dismiss/resolve for tenant-scoped rows
(which can't share the engagement-scoped paths because their
``engagement_id`` is null).

See ``docs/product/synthesis-agents.md`` §4, §11.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llm_provider_py.types import LLMProvider
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.llm import get_llm_provider, resolve_tenant_llm_provider
from control_plane.agents.master_strategist import (
    MasterStrategistCandidate,
    PortfolioEdge,
    PortfolioEngagement,
    PortfolioNode,
    master_strategist_candidates,
    master_strategist_phrase,
)
from control_plane.agents.master_strategist import (
    default_system_prompt as master_strategist_default_prompt,
)
from control_plane.agents.matrix_extractor import (
    default_system_prompt as matrix_extractor_default_prompt,
)
from control_plane.agents.oracle import InsightDraft
from control_plane.agents.oracle import (
    default_system_prompt as oracle_default_prompt,
)
from control_plane.agents.prompts import resolve_tenant_prompt
from control_plane.api.routes.engagements_internal import require_internal
from control_plane.db import get_app_db_session
from control_plane.domain.app_identity.models import (
    AGENT_PROMPT_NAMES,
    LLM_PROVIDERS,
    AppTenant,
    AppUser,
    TenantAgentPrompt,
    TenantLlmConfig,
)
from control_plane.domain.canonical_memory.matrix import (
    INSIGHT_STATUSES,
    MatrixEdge,
    MatrixInsight,
    MatrixNode,
)
from control_plane.domain.engagement import Engagement, EngagementMember, TenantMemberRole
from control_plane.domain.member_roles import BUILTIN_MEMBER_ROLES, list_tenant_member_roles

_AGENT_DEFAULT_PROMPTS: dict[str, Callable[[], str]] = {
    "cartographer": matrix_extractor_default_prompt,
    "oracle": oracle_default_prompt,
    "master_strategist": master_strategist_default_prompt,
}

router = APIRouter(prefix="/tenants", tags=["internal-tenants"])


class TenantInsightRead(BaseModel):
    """Mirrors ``MatrixInsightRead`` from engagements_internal — re-declared
    here so this module is self-contained and the imports stay one-way."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    engagement_id: uuid.UUID | None
    agent: str
    insight_type: str
    severity: str
    title: str
    body: str
    citation_node_ids: list[uuid.UUID]
    citation_edge_ids: list[uuid.UUID]
    citation_event_ids: list[uuid.UUID]
    dedup_key: str
    status: str
    created_at: datetime
    decided_at: datetime | None
    decided_by: str | None


class TenantInsightDecision(BaseModel):
    actor_id: str | None = Field(default=None, max_length=200)


async def _require_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> AppTenant:
    row = await session.get(AppTenant, tenant_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    return row


@router.get(
    "/{tenant_id}/insights",
    response_model=list[TenantInsightRead],
    dependencies=[Depends(require_internal)],
)
async def list_tenant_insights(
    tenant_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    status_filter: Annotated[str | None, Query(alias="status")] = "open",
) -> list[MatrixInsight]:
    await _require_tenant(session, tenant_id)
    # Only tenant-scoped rows (Master Strategist output) — engagement_id IS NULL.
    stmt = select(MatrixInsight).where(
        MatrixInsight.tenant_id == tenant_id,
        MatrixInsight.engagement_id.is_(None),
    )
    if status_filter is not None:
        if status_filter not in INSIGHT_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"invalid status: {status_filter}",
            )
        stmt = stmt.where(MatrixInsight.status == status_filter)
    r = await session.execute(stmt.order_by(MatrixInsight.severity.desc(), MatrixInsight.created_at.desc()))
    return list(r.scalars().all())


async def _decide_tenant_insight(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    insight_id: uuid.UUID,
    new_status: str,
    actor_id: str | None,
) -> MatrixInsight:
    await _require_tenant(session, tenant_id)
    r = await session.execute(
        select(MatrixInsight).where(
            MatrixInsight.tenant_id == tenant_id,
            MatrixInsight.engagement_id.is_(None),
            MatrixInsight.id == insight_id,
        )
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="insight not found")
    if row.status != "open":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"insight is not open (status={row.status})",
        )
    row.status = new_status
    row.decided_at = datetime.now(UTC)
    row.decided_by = actor_id
    await session.commit()
    await session.refresh(row)
    return row


@router.post(
    "/{tenant_id}/insights/{insight_id}/dismiss",
    response_model=TenantInsightRead,
    dependencies=[Depends(require_internal)],
)
async def dismiss_tenant_insight(
    tenant_id: uuid.UUID,
    insight_id: uuid.UUID,
    body: TenantInsightDecision,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> MatrixInsight:
    return await _decide_tenant_insight(session, tenant_id, insight_id, "dismissed", body.actor_id)


@router.post(
    "/{tenant_id}/insights/{insight_id}/resolve",
    response_model=TenantInsightRead,
    dependencies=[Depends(require_internal)],
)
async def resolve_tenant_insight(
    tenant_id: uuid.UUID,
    insight_id: uuid.UUID,
    body: TenantInsightDecision,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> MatrixInsight:
    return await _decide_tenant_insight(session, tenant_id, insight_id, "resolved", body.actor_id)


@router.post(
    "/{tenant_id}/insights/refresh",
    response_model=list[TenantInsightRead],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_internal)],
)
async def refresh_tenant_insights(
    tenant_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> list[MatrixInsight]:
    """Run the Master Strategist over the tenant's portfolio.

    Tenant-scoped twin of ``refresh_matrix_insights`` (Oracle, engagements
    router). Same dedup_key upsert + auto-resolve semantics — see design §11.
    """
    tenant = await _require_tenant(session, tenant_id)
    llm = await resolve_tenant_llm_provider(session, tenant_id, llm)
    strategist_prompt = await resolve_tenant_prompt(
        session, tenant_id, "master_strategist", master_strategist_default_prompt()
    )

    # Snapshot: every engagement + its matrix + member roles.
    eng_q = await session.execute(select(Engagement).where(Engagement.tenant_id == tenant_id))
    engagements_rows = list(eng_q.scalars().all())

    portfolio: list[PortfolioEngagement] = []
    for eng in engagements_rows:
        members_q = await session.execute(select(EngagementMember).where(EngagementMember.engagement_id == eng.id))
        roles = tuple(m.role for m in members_q.scalars().all())
        nodes_q = await session.execute(select(MatrixNode).where(MatrixNode.engagement_id == eng.id))
        nodes = tuple(
            PortfolioNode(
                id=n.id,
                node_type=n.node_type,
                title=n.title,
                attributes=n.attributes or {},
            )
            for n in nodes_q.scalars().all()
        )
        edges_q = await session.execute(select(MatrixEdge).where(MatrixEdge.engagement_id == eng.id))
        edges = tuple(
            PortfolioEdge(
                id=e.id,
                edge_type=e.edge_type,
                from_node_id=e.from_node_id,
                to_node_id=e.to_node_id,
            )
            for e in edges_q.scalars().all()
        )
        portfolio.append(
            PortfolioEngagement(
                id=eng.id,
                name=eng.name,
                status=eng.status,
                current_phase=eng.current_phase,
                member_roles=roles,
                nodes=nodes,
                edges=edges,
            )
        )

    candidates = master_strategist_candidates(tenant_id=tenant_id, engagements=portfolio)

    existing_q = await session.execute(
        select(MatrixInsight).where(
            MatrixInsight.tenant_id == tenant_id,
            MatrixInsight.engagement_id.is_(None),
        )
    )
    existing: dict[str, MatrixInsight] = {row.dedup_key: row for row in existing_q.scalars().all()}

    to_phrase: list[MasterStrategistCandidate] = []
    for c in candidates:
        prev = existing.get(c.dedup_key)
        if prev is None:
            to_phrase.append(c)
            continue
        if prev.status == "dismissed":
            continue
        if prev.status == "open" and prev.input_hash == c.input_hash:
            continue
        to_phrase.append(c)

    drafts: list[InsightDraft] = []
    if to_phrase:
        drafts = master_strategist_phrase(
            tenant_name=tenant.name,
            engagements=portfolio,
            candidates=to_phrase,
            llm=llm,
            system_prompt=strategist_prompt,
        )

    drafts_by_key = {d.dedup_key: d for d in drafts}
    for c in to_phrase:
        d = drafts_by_key.get(c.dedup_key)
        if d is None:
            continue
        prev = existing.get(c.dedup_key)
        if prev is None:
            row = MatrixInsight(
                tenant_id=tenant_id,
                engagement_id=None,
                agent="master_strategist",
                insight_type=d.insight_type,
                severity=d.severity,
                title=d.title,
                body=d.body,
                citation_node_ids=list(d.citation_node_ids),
                citation_edge_ids=list(d.citation_edge_ids),
                citation_event_ids=list(d.citation_event_ids),
                dedup_key=d.dedup_key,
                input_hash=d.input_hash,
            )
            session.add(row)
        else:
            prev.severity = d.severity
            prev.title = d.title
            prev.body = d.body
            prev.citation_node_ids = list(d.citation_node_ids)
            prev.citation_edge_ids = list(d.citation_edge_ids)
            prev.input_hash = d.input_hash
            if prev.status == "resolved":
                prev.status = "open"
                prev.decided_at = None
                prev.decided_by = None

    candidate_keys = {c.dedup_key for c in candidates}
    for key, prev in existing.items():
        if prev.status == "open" and key not in candidate_keys:
            prev.status = "resolved"
            prev.decided_at = datetime.now(UTC)
            prev.decided_by = "auto"

    await session.commit()

    final_q = await session.execute(
        select(MatrixInsight)
        .where(
            MatrixInsight.tenant_id == tenant_id,
            MatrixInsight.engagement_id.is_(None),
            MatrixInsight.status == "open",
        )
        .order_by(MatrixInsight.severity.desc(), MatrixInsight.created_at.desc())
    )
    return list(final_q.scalars().all())


# --- Sprint 1 — per-tenant LLM provider configuration ----------------------
#
# Customers running DeployAI self-hosted set their provider + model + key
# at runtime instead of editing the compose env. One row per tenant; the
# agent factory (control_plane/agents/llm.py) reads this before falling
# back to env defaults. The API key is stored plaintext — acceptable for
# self-hosted single-team deployments where the customer owns the DB.


def _mask_api_key(value: str | None) -> str | None:
    """Return a UI-safe key fingerprint: last 4 chars, rest as asterisks."""
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


class TenantLlmConfigRead(BaseModel):
    """LLM config response. The full ``api_key`` is never returned to the
    client; only ``api_key_masked`` for UI confirmation."""

    tenant_id: uuid.UUID
    provider: str
    model_name: str | None
    api_key_masked: str | None
    has_api_key: bool
    updated_at: datetime


class TenantLlmConfigWrite(BaseModel):
    """Upsert payload. ``api_key`` is optional on PUT — omitting it on an
    existing row keeps the previously stored key (so the user can change
    only the model without re-pasting the key)."""

    provider: str = Field(min_length=1)
    model_name: str | None = Field(default=None, max_length=200)
    api_key: str | None = Field(default=None, max_length=500)


def _to_read(row: TenantLlmConfig) -> TenantLlmConfigRead:
    return TenantLlmConfigRead(
        tenant_id=row.tenant_id,
        provider=row.provider,
        model_name=row.model_name,
        api_key_masked=_mask_api_key(row.api_key),
        has_api_key=bool(row.api_key),
        updated_at=row.updated_at,
    )


@router.get(
    "/{tenant_id}/llm-config",
    response_model=TenantLlmConfigRead | None,
    dependencies=[Depends(require_internal)],
)
async def get_tenant_llm_config(
    tenant_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> TenantLlmConfigRead | None:
    """Return the tenant's saved config, or null if none has been set
    (in which case the agent factory falls back to env defaults)."""
    await _require_tenant(session, tenant_id)
    r = await session.execute(select(TenantLlmConfig).where(TenantLlmConfig.tenant_id == tenant_id))
    row = r.scalar_one_or_none()
    return _to_read(row) if row else None


@router.put(
    "/{tenant_id}/llm-config",
    response_model=TenantLlmConfigRead,
    dependencies=[Depends(require_internal)],
)
async def put_tenant_llm_config(
    tenant_id: uuid.UUID,
    body: TenantLlmConfigWrite,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> TenantLlmConfigRead:
    """Upsert the tenant's LLM provider configuration."""
    await _require_tenant(session, tenant_id)
    if body.provider not in LLM_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid provider: {body.provider}",
        )
    r = await session.execute(select(TenantLlmConfig).where(TenantLlmConfig.tenant_id == tenant_id))
    row = r.scalar_one_or_none()
    now = datetime.now(UTC)
    if row is None:
        row = TenantLlmConfig(
            tenant_id=tenant_id,
            provider=body.provider,
            model_name=body.model_name,
            api_key=body.api_key,
        )
        session.add(row)
    else:
        row.provider = body.provider
        row.model_name = body.model_name
        # Preserve the prior key when the caller omits one (so they can
        # update model without re-pasting the secret).
        if body.api_key is not None:
            row.api_key = body.api_key
        row.updated_at = now
    await session.commit()
    await session.refresh(row)
    return _to_read(row)


# --- Sprint 1 inc 2 — non-SCIM tenant user provisioning --------------------
#
# Self-hosted single-team deployments don't run a SCIM IdP; the first-run
# wizard needs a way to seed the first AppUser without a bearer token. SCIM
# (`/scim/v2/Users`) stays the supported path for production IdP-driven
# provisioning — this internal endpoint is a parallel admin-key seam for
# bootstrap. It does *not* set `scim_external_id`; SCIM bulk-load from an
# IdP later will not collide.


class AppUserCreate(BaseModel):
    user_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    given_name: str | None = Field(default=None, max_length=200)
    family_name: str | None = Field(default=None, max_length=200)


class AppUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_name: str
    email: str | None
    given_name: str | None
    family_name: str | None
    active: bool
    created_at: datetime


@router.post(
    "/{tenant_id}/users",
    response_model=AppUserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def create_tenant_user(
    tenant_id: uuid.UUID,
    body: AppUserCreate,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> AppUser:
    """Create an AppUser via the internal admin key (no SCIM token).

    Used by the first-run onboarding wizard so the team can seed itself
    without running an IdP. `user_name` must be unique-per-tenant — duplicate
    returns 409.
    """
    await _require_tenant(session, tenant_id)
    existing = await session.execute(
        select(AppUser).where(
            AppUser.tenant_id == tenant_id,
            AppUser.user_name == body.user_name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"user_name already exists for tenant: {body.user_name}",
        )
    row = AppUser(
        tenant_id=tenant_id,
        user_name=body.user_name,
        email=body.email,
        given_name=body.given_name,
        family_name=body.family_name,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


# --- Sprint 5 — per-tenant agent prompt overrides --------------------------
#
# Customers can edit the Cartographer / Oracle / Master Strategist system
# prompts for their tenant from the Settings UI. One row per (tenant,
# agent_name); when no row exists the agent uses the baked-in default
# (resolved via ``resolve_tenant_prompt`` in each refresh / extract route).


class AgentPromptEntry(BaseModel):
    """One agent's resolved prompt + whether it's the default."""

    value: str
    is_default: bool


class AgentPromptsRead(BaseModel):
    """Map of agent_name -> resolved prompt + default flag."""

    prompts: dict[str, AgentPromptEntry]


class AgentPromptWrite(BaseModel):
    prompt_text: str = Field(min_length=1)


def _check_agent_name(agent_name: str) -> None:
    if agent_name not in AGENT_PROMPT_NAMES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid agent_name: {agent_name}",
        )


@router.get(
    "/{tenant_id}/agent-prompts",
    response_model=AgentPromptsRead,
    dependencies=[Depends(require_internal)],
)
async def list_tenant_agent_prompts(
    tenant_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> AgentPromptsRead:
    """Return every supported agent's resolved prompt + default flag."""
    await _require_tenant(session, tenant_id)
    r = await session.execute(select(TenantAgentPrompt).where(TenantAgentPrompt.tenant_id == tenant_id))
    overrides: dict[str, str] = {row.agent_name: row.prompt_text for row in r.scalars().all()}
    entries: dict[str, AgentPromptEntry] = {}
    for name in AGENT_PROMPT_NAMES:
        default = _AGENT_DEFAULT_PROMPTS[name]()
        if name in overrides:
            entries[name] = AgentPromptEntry(value=overrides[name], is_default=False)
        else:
            entries[name] = AgentPromptEntry(value=default, is_default=True)
    return AgentPromptsRead(prompts=entries)


@router.put(
    "/{tenant_id}/agent-prompts/{agent_name}",
    response_model=AgentPromptEntry,
    dependencies=[Depends(require_internal)],
)
async def put_tenant_agent_prompt(
    tenant_id: uuid.UUID,
    agent_name: str,
    body: AgentPromptWrite,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> AgentPromptEntry:
    """Upsert the tenant's prompt override for one agent."""
    await _require_tenant(session, tenant_id)
    _check_agent_name(agent_name)
    r = await session.execute(
        select(TenantAgentPrompt).where(
            TenantAgentPrompt.tenant_id == tenant_id,
            TenantAgentPrompt.agent_name == agent_name,
        )
    )
    row = r.scalar_one_or_none()
    now = datetime.now(UTC)
    if row is None:
        row = TenantAgentPrompt(
            tenant_id=tenant_id,
            agent_name=agent_name,
            prompt_text=body.prompt_text,
        )
        session.add(row)
    else:
        row.prompt_text = body.prompt_text
        row.updated_at = now
    await session.commit()
    await session.refresh(row)
    return AgentPromptEntry(value=row.prompt_text, is_default=False)


@router.delete(
    "/{tenant_id}/agent-prompts/{agent_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_internal)],
)
async def delete_tenant_agent_prompt(
    tenant_id: uuid.UUID,
    agent_name: str,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> None:
    """Remove the tenant's override so the agent falls back to the default."""
    await _require_tenant(session, tenant_id)
    _check_agent_name(agent_name)
    r = await session.execute(
        select(TenantAgentPrompt).where(
            TenantAgentPrompt.tenant_id == tenant_id,
            TenantAgentPrompt.agent_name == agent_name,
        )
    )
    row = r.scalar_one_or_none()
    if row is None:
        return None
    await session.delete(row)
    await session.commit()
    return None


# --- Tenant-scoped custom engagement-member roles --------------------------
#
# Tenants extend the baked-in role trio (fde / deployment_strategist /
# biz_dev) with custom names — ``clinical_lead`` for a healthcare team,
# ``sales_engineer`` for a B2B SaaS team. The slug is immutable so existing
# memberships referencing it stay valid; label + description are mutable.

_BUILTIN_MEMBER_ROLE_LABELS: dict[str, str] = {
    "fde": "Forward-deployed engineer",
    "deployment_strategist": "Deployment strategist",
    "biz_dev": "Business development",
}

_MEMBER_ROLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")


class BuiltinMemberRoleRead(BaseModel):
    name: str
    label: str


class CustomMemberRoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    label: str
    description: str | None


class MemberRolesRead(BaseModel):
    builtin: list[BuiltinMemberRoleRead]
    custom: list[CustomMemberRoleRead]


class MemberRoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)


class MemberRoleUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)


def _validate_member_role_name(name: str) -> None:
    if not _MEMBER_ROLE_NAME_RE.match(name):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid name (lowercase letters, digits, underscores; must start with letter): {name}",
        )
    if name in BUILTIN_MEMBER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"name collides with a built-in role: {name}",
        )


@router.get(
    "/{tenant_id}/member-roles",
    response_model=MemberRolesRead,
    dependencies=[Depends(require_internal)],
)
async def list_member_roles(
    tenant_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> MemberRolesRead:
    await _require_tenant(session, tenant_id)
    custom_rows = await list_tenant_member_roles(session, tenant_id)
    builtin = [BuiltinMemberRoleRead(name=n, label=_BUILTIN_MEMBER_ROLE_LABELS[n]) for n in BUILTIN_MEMBER_ROLES]
    custom = [CustomMemberRoleRead.model_validate(row) for row in custom_rows]
    return MemberRolesRead(builtin=builtin, custom=custom)


@router.post(
    "/{tenant_id}/member-roles",
    response_model=CustomMemberRoleRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def create_member_role(
    tenant_id: uuid.UUID,
    body: MemberRoleCreate,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> CustomMemberRoleRead:
    await _require_tenant(session, tenant_id)
    _validate_member_role_name(body.name)
    existing = await session.execute(
        select(TenantMemberRole).where(
            TenantMemberRole.tenant_id == tenant_id,
            TenantMemberRole.name == body.name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"role already exists: {body.name}",
        )
    row = TenantMemberRole(
        tenant_id=tenant_id,
        name=body.name,
        label=body.label,
        description=body.description,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return CustomMemberRoleRead.model_validate(row)


async def _require_member_role(session: AsyncSession, tenant_id: uuid.UUID, role_id: uuid.UUID) -> TenantMemberRole:
    r = await session.execute(
        select(TenantMemberRole).where(
            TenantMemberRole.tenant_id == tenant_id,
            TenantMemberRole.id == role_id,
        )
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="member role not found")
    return row


@router.put(
    "/{tenant_id}/member-roles/{role_id}",
    response_model=CustomMemberRoleRead,
    dependencies=[Depends(require_internal)],
)
async def update_member_role(
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
    body: MemberRoleUpdate,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> CustomMemberRoleRead:
    await _require_tenant(session, tenant_id)
    row = await _require_member_role(session, tenant_id, role_id)
    data = body.model_dump(exclude_unset=True)
    if "label" in data and data["label"] is not None:
        row.label = data["label"]
    if "description" in data:
        row.description = data["description"]
    row.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(row)
    return CustomMemberRoleRead.model_validate(row)


@router.delete(
    "/{tenant_id}/member-roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_internal)],
)
async def delete_member_role(
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> None:
    await _require_tenant(session, tenant_id)
    row = await _require_member_role(session, tenant_id, role_id)
    in_use = await session.execute(
        select(EngagementMember.id)
        .where(EngagementMember.tenant_id == tenant_id, EngagementMember.role == row.name)
        .limit(1)
    )
    if in_use.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"role is in use by one or more engagement members: {row.name}",
        )
    await session.delete(row)
    await session.commit()
