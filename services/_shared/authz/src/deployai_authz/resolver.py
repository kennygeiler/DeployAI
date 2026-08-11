from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Final, Literal, NotRequired, TypedDict, cast

V1Role = Literal[
    "platform_admin",
    "customer_admin",
    "deployment_strategist",
    "fde",
    "biz_dev",
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
    "admin:read",
    "internal:proxy",
    "foia:export",
    "canonical:read",
    "override:submit",
    "solidification:promote",
    "break_glass:invoke",
    "scim:manage",
]


# Every resource may carry the tenant it belongs to (``tenant_id``). ``can_access``
# blocks whenever the actor's tenant and the resource's tenant are both present and
# differ, regardless of kind. For ``kind == "tenant"`` the resource IS the tenant,
# so ``id`` doubles as the tenant id.


class ResourceIngestionRuns(TypedDict):
    kind: Literal["ingestion_runs"]
    tenant_id: NotRequired[str]


class ResourceSchemaProposals(TypedDict):
    kind: Literal["schema_proposals"]
    tenant_id: NotRequired[str]


class ResourceTenant(TypedDict):
    kind: Literal["tenant"]
    id: str


class ResourceCanonicalMemory(TypedDict):
    kind: Literal["canonical_memory"]
    tenant_id: NotRequired[str]


class ResourceOverride(TypedDict):
    kind: Literal["override"]
    tenant_id: NotRequired[str]


class ResourceFoiaExport(TypedDict):
    kind: Literal["foia_export"]
    tenant_id: NotRequired[str]


class ResourceBreakGlass(TypedDict):
    kind: Literal["break_glass"]
    tenant_id: NotRequired[str]


class ResourceScim(TypedDict):
    kind: Literal["scim"]
    tenant_id: NotRequired[str]


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
        ("platform_admin", "admin:read"),
        ("platform_admin", "internal:proxy"),
        ("platform_admin", "foia:export"),
        ("platform_admin", "canonical:read"),
        ("platform_admin", "override:submit"),
        ("platform_admin", "solidification:promote"),
        ("platform_admin", "break_glass:invoke"),
        ("platform_admin", "scim:manage"),
        ("customer_admin", "ingest:view_runs"),
        ("customer_admin", "admin:read"),
        ("customer_admin", "internal:proxy"),
        ("customer_admin", "canonical:read"),
        ("customer_admin", "override:submit"),
        ("customer_admin", "scim:manage"),
        ("customer_records_officer", "ingest:view_runs"),
        ("customer_records_officer", "canonical:read"),
        ("external_auditor", "foia:export"),
        ("deployment_strategist", "ingest:view_runs"),
        ("deployment_strategist", "ingest:sync"),
        ("deployment_strategist", "integration:kill_switch"),
        ("deployment_strategist", "internal:proxy"),
        ("deployment_strategist", "canonical:read"),
        ("deployment_strategist", "override:submit"),
        # fde — Forward Deployed Engineer; operationally equivalent to a
        # deployment strategist (both run the engagement).
        ("fde", "ingest:view_runs"),
        ("fde", "ingest:sync"),
        ("fde", "integration:kill_switch"),
        ("fde", "internal:proxy"),
        ("fde", "canonical:read"),
        ("fde", "override:submit"),
        # biz_dev — business development; reads the engagement memory.
        ("biz_dev", "canonical:read"),
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


# Resource kinds that are always tenant-owned. Calls for these kinds must carry
# ``tenant_id`` or the tenant comparison silently never runs (Wave 1 ticket A5).
_TENANT_SCOPED_KINDS: Final[frozenset[str]] = frozenset({"canonical_memory", "override", "foia_export"})

# Mirrors deployai_tenancy.envelope: anything outside {dev, test, ci} is production.
_DEV_ENVIRONMENTS: Final[frozenset[str]] = frozenset({"dev", "test", "ci"})


class TenantScopePolicyError(RuntimeError):
    """Raised outside production when a tenant-scoped resource lacks ``tenant_id``."""


def _is_production_runtime() -> bool:
    return os.environ.get("ENVIRONMENT", "dev") not in _DEV_ENVIRONMENTS


def _resource_tenant_id(resource: Resource) -> str | None:
    if resource["kind"] == "tenant":
        return resource["id"]
    if resource["kind"] == "global":
        return None
    return resource.get("tenant_id")


def _tenant_scope_policy_violation(resource: Resource) -> bool:
    return resource["kind"] in _TENANT_SCOPED_KINDS and _resource_tenant_id(resource) is None


def _cross_tenant_blocked(actor: AuthActor, resource: Resource) -> bool:
    """Cross-tenant rule for EVERY resource kind: block when both the actor tenant
    and the resource tenant are present and differ. ``kind == "tenant"`` keeps its
    stricter legacy rule: an actor without a tenant may not touch a tenant resource.
    """
    if actor.role == "platform_admin":
        return False
    tid = _resource_tenant_id(resource)
    if resource["kind"] == "tenant" and tid is not None and actor.tenant_id is None:
        return True
    if tid is not None and actor.tenant_id is not None and tid != actor.tenant_id:
        return True
    return False


def _matrix_allows(role: V1Role, action: Action) -> bool:
    return (role, action) in _ALLOWED


def can_access(actor: AuthActor, action: Action, resource: Resource, *, skip_audit: bool = False) -> Decision:
    """Primary Epic 2.1 entry; logs one JSON line per call unless ``skip_audit`` (tests).

    A tenant-scoped resource (canonical_memory / override / foia_export) passed without
    ``tenant_id`` is a caller bug: outside production (``ENVIRONMENT`` in dev/test/ci)
    this raises :class:`TenantScopePolicyError` so the broken call site is found
    immediately; in production it is denied fail-closed.
    """
    if _tenant_scope_policy_violation(resource):
        if not _is_production_runtime():
            raise TenantScopePolicyError(
                f"authz policy error: resource kind {resource['kind']!r} is tenant-scoped "
                "but no tenant_id was provided. Pass the tenant the request is about."
            )
        d = Decision(
            allow=False,
            reason="Tenant-scoped resource is missing tenant_id (denied fail-closed)",
            code="forbidden",
        )
    elif _cross_tenant_blocked(actor, resource):
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
            "resource_tenant_id": _resource_tenant_id(resource),
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

