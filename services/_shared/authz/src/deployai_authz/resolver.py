from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

V1Role = Literal[
    "platform_admin",
    "customer_admin",
    "deployment_strategist",
    "successor_strategist",
    "customer_records_officer",
    "external_auditor",
]

Action = Literal[
    "ingest:view_runs",
    "ingest:configure",
    "admin:view_schema_proposals",
    "admin:promote_schema",
    "foia:export",
]

_ALLOWED: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("platform_admin", "ingest:view_runs"),
        ("platform_admin", "ingest:configure"),
        ("platform_admin", "admin:view_schema_proposals"),
        ("platform_admin", "admin:promote_schema"),
        ("platform_admin", "foia:export"),
        ("customer_admin", "ingest:view_runs"),
        ("customer_records_officer", "ingest:view_runs"),
        ("external_auditor", "foia:export"),
        ("deployment_strategist", "ingest:view_runs"),
        ("successor_strategist", "ingest:view_runs"),
    },
)


def matrix_allowed(role: V1Role, action: Action) -> bool:
    return (role, action) in _ALLOWED


@dataclass(frozen=True, slots=True)
class Decision:
    allow: bool
    reason: str = ""
    code: Literal["ok", "forbidden", "unauthenticated"] = "ok"


def is_allowed(role: V1Role, action: Action) -> Decision:
    if not matrix_allowed(role, action):
        return Decision(allow=False, reason="Not permitted for role", code="forbidden")
    return Decision(allow=True, code="ok")
