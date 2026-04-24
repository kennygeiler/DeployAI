from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Final, Literal, TypedDict, cast

V1Role = Literal[
    "platform_admin",
    "customer_admin",
    "deployment_strategist",
    "successor_strategist",
    "customer_records_officer",
    "external_auditor",
    "pending_assignment",  # SSO: no matrix capabilities until tenant/role bound (Story 2-2)
]

Action = Literal[
    "ingest:view_runs",
    "ingest:configure",
    "ingest:sync",
    "integration:kill_switch",
    "admin:view_schema_proposals",
    "admin:promote_schema",
    "foia:export",
    "canonical:read",
    "override:submit",
    "solidification:promote",
    "break_glass:invoke",
    "scim:manage",
]


class ResourceIngestionRuns(TypedDict):
    kind: Literal["ingestion_runs"]


class ResourceSchemaProposals(TypedDict):
    kind: Literal["schema_proposals"]


class ResourceTenant(TypedDict):
    kind: Literal["tenant"]
    id: str


class ResourceCanonicalMemory(TypedDict):
    kind: Literal["canonical_memory"]


class ResourceOverride(TypedDict):
    kind: Literal["override"]


class ResourceFoiaExport(TypedDict):
    kind: Literal["foia_export"]


class ResourceBreakGlass(TypedDict):
    kind: Literal["break_glass"]


class ResourceScim(TypedDict):
    kind: Literal["scim"]


class ResourceGlobal(TypedDict):
    kind: Literal["global"]


Resource = (
    ResourceIngestionRuns
    | ResourceSchemaProposals
    | ResourceTenant
    | ResourceCanonicalMemory
    | ResourceOverride
    | ResourceFoiaExport
    | ResourceBreakGlass
    | ResourceScim
    | ResourceGlobal
)

_AUTH_LOG = logging.getLogger("deployai.authz")

_ALLOWED: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("platform_admin", "ingest:view_runs"),
        ("platform_admin", "ingest:configure"),
        ("platform_admin", "ingest:sync"),
        ("platform_admin", "integration:kill_switch"),
        ("platform_admin", "admin:view_schema_proposals"),
        ("platform_admin", "admin:promote_schema"),
        ("platform_admin", "foia:export"),
        ("platform_admin", "canonical:read"),
        ("platform_admin", "override:submit"),
        ("platform_admin", "solidification:promote"),
        ("platform_admin", "break_glass:invoke"),
        ("platform_admin", "scim:manage"),
        ("customer_admin", "ingest:view_runs"),
        ("customer_admin", "canonical:read"),
        ("customer_admin", "override:submit"),
        ("customer_admin", "scim:manage"),
        ("customer_records_officer", "ingest:view_runs"),
        ("customer_records_officer", "canonical:read"),
        ("external_auditor", "foia:export"),
        ("external_auditor", "canonical:read"),
        ("deployment_strategist", "ingest:view_runs"),
        ("deployment_strategist", "ingest:sync"),
        ("deployment_strategist", "integration:kill_switch"),
        ("deployment_strategist", "canonical:read"),
        ("deployment_strategist", "override:submit"),
        ("successor_strategist", "ingest:view_runs"),
        ("successor_strategist", "canonical:read"),
        ("successor_strategist", "override:submit"),
    },
)


@dataclass(frozen=True, slots=True)
class Decision:
    allow: bool
    reason: str = ""
    code: Literal["ok", "forbidden", "unauthenticated"] = "ok"


class AuthActor:
    __slots__ = ("role", "tenant_id")

    def __init__(self, *, role: V1Role, tenant_id: str | None = None) -> None:
        self.role = role
        self.tenant_id = tenant_id


def _resource_tenant_id(resource: Resource) -> str | None:
    if resource["kind"] == "tenant":
        return resource["id"]
    return None


def _cross_tenant_blocked(actor: AuthActor, resource: Resource) -> bool:
    if actor.role == "platform_admin":
        return False
    if resource["kind"] == "tenant":
        tid = _resource_tenant_id(resource)
        if tid is not None and actor.tenant_id is None:
            return True
        if tid is not None and actor.tenant_id is not None and tid != actor.tenant_id:
            return True
    return False


def _matrix_allows(role: V1Role, action: Action) -> bool:
    return (role, action) in _ALLOWED


def can_access(actor: AuthActor, action: Action, resource: Resource, *, skip_audit: bool = False) -> Decision:
    """Primary Epic 2.1 entry; logs one JSON line per call unless ``skip_audit`` (tests)."""
    if _cross_tenant_blocked(actor, resource):
        d = Decision(allow=False, reason="Cross-tenant access is not allowed for this role", code="forbidden")
    elif not _matrix_allows(actor.role, action):
        d = Decision(allow=False, reason="Role cannot perform this action in the V1 matrix", code="forbidden")
    else:
        d = Decision(allow=True, code="ok")

    if not skip_audit:
        kind = resource["kind"]
        if kind == "tenant":
            res_kind = f"tenant:{cast(ResourceTenant, resource)['id']}"
        else:
            res_kind = kind
        payload = {
            "event": "authz_decision",
            "allow": d.allow,
            "actor_role": actor.role,
            "action": action,
            "resource_kind": res_kind,
            "tenant_id": actor.tenant_id,
            "resource_tenant_id": _resource_tenant_id(resource) if kind == "tenant" else None,
            "code": d.code,
            "reason": None if d.allow else d.reason,
        }
        _AUTH_LOG.info(json.dumps(payload))

    return d


def matrix_allowed(role: V1Role, action: Action) -> bool:
    return _matrix_allows(role, action)


def is_allowed(role: V1Role, action: Action) -> Decision:
    """Legacy: decision against ``{kind: 'global'}`` resource (no tenant restriction)."""
    return can_access(AuthActor(role=role), action, {"kind": "global"}, skip_audit=True)

