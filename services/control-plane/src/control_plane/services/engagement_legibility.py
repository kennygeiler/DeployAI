"""Legibility helpers for the engagement summary / list surfaces (Wave 2.5, U2/U6/U7).

Pure functions and lookup tables shared by the engagement summary endpoint
(``api/routes/engagement_summary_internal.py``) and the engagement list
attention fields (``api/routes/engagements_internal.list_engagements``).
Kept free of DB and HTTP concerns so every convention chosen here is
unit-testable in isolation:

- ``SOURCE_KIND_BUCKETS`` — coarse ledger ``source_kind`` → display bucket map.
- ``humanize_event_title`` — strips boilerplate "kind:" prefixes from ledger
  summaries so the UI shows the human part.
- ``user_display_name`` / ``actor_display_name`` — display-name derivation for
  app_users rows and ledger actors.
- ``is_risk_open`` — the open/closed convention for risk matrix nodes.
- ``attention_score`` — the U7 needs-attention scoring formula.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

# Coarse display buckets for recent-change rows. The UI colors/icons key off
# these, so the vocabulary is closed — anything unmapped falls into "other".
RECENT_CHANGE_BUCKETS: tuple[str, ...] = (
    "decision",
    "risk",
    "stakeholder",
    "commitment",
    "proposal",
    "agent",
    "system",
    "other",
)

# Ledger ``source_kind`` → coarse bucket. Covers both the emitter-validated
# vocabulary (``control_plane.ledger.emitter.ALLOWED_SOURCE_KINDS``) and the
# raw-SQL seed kinds the BlueState scenarios write directly ("decision",
# "risk_opened", "risk_closed", "extractor_proposal"). Matrix node/edge CRUD
# kinds land in "other" deliberately: the node_type lives in the event detail,
# not the source_kind, and this map is source_kind-only by contract.
SOURCE_KIND_BUCKETS: dict[str, str] = {
    # decisions
    "decision": "decision",
    "engagement_phase_change": "decision",
    # risks — insight_* events are risk-flavored in this codebase (the
    # BlueState seeds and the risk_open_rate analyzer both treat
    # insight_opened/closed as risk lifecycle events).
    "risk_opened": "risk",
    "risk_closed": "risk",
    "insight_opened": "risk",
    "insight_closed": "risk",
    "insight_snoozed": "risk",
    # people
    "member_added": "stakeholder",
    "member_removed": "stakeholder",
    "user_provisioned": "stakeholder",
    # commitments
    "followup_task_created": "commitment",
    # extraction / review-loop proposals
    "llm_proposal_created": "proposal",
    "extractor_proposal": "proposal",
    "proposal_accepted": "proposal",
    "proposal_rejected": "proposal",
    "proposal_auto_accepted": "proposal",
    "proposals_bulk_accepted": "proposal",
    "audit_decision": "proposal",
    # agent activity (Kenny, oracle, synthesis, review inbox, approvals)
    "oracle_chat_turn": "agent",
    "oracle_conversation_started": "agent",
    "recommendation_emitted": "agent",
    "recommendation_actioned": "agent",
    "agent_synthesis_emitted": "agent",
    "synthesis_failed": "agent",
    "synthesis_validation_failed": "agent",
    "synthesis_stale_flagged": "agent",
    "agent_tool_invocation": "agent",
    "propose_action": "agent",
    "agent_audit_concern": "agent",
    "agent_concern_logged": "agent",
    "agent_hallucination_unresolved": "agent",
    "agent_cross_engagement_leak": "agent",
    "agent_approval_requested": "agent",
    "agent_approval_granted": "agent",
    "agent_approval_denied": "agent",
    "review_item_created": "agent",
    "review_item_resolved": "agent",
    "review_item_dismissed": "agent",
    "human_escalation_answer": "agent",
    # platform / ops
    "settings_change": "system",
    "tenant_api_key_minted": "system",
    "tenant_api_key_revoked": "system",
    "mcp_resource_read": "system",
    "mcp_tool_invocation": "system",
    "mcp_auth_failed": "system",
    "mcp_config_created": "system",
    "mcp_config_updated": "system",
    "mcp_config_deleted": "system",
    "mcp_oauth_token_rotated": "system",
    "mcp_outbound_killswitch_changed": "system",
    "mcp_outbound_call": "system",
    "mcp_outbound_blocked": "system",
    "mcp_outbound_rate_limited": "system",
    "mcp_outbound_denied": "system",
    "mcp_outbound_egress_blocked": "system",
    "killswitch_oauth_revoked": "system",
    "killswitch_oauth_revoke_failed": "system",
    "killswitch_queue_purged": "system",
    "killswitch_queue_purge_failed": "system",
    "killswitch_secrets_deleted": "system",
    "killswitch_secrets_delete_failed": "system",
    # raw activity / entity CRUD — no better bucket without reading detail
    "email_ingest": "other",
    "meeting_webhook": "other",
    "manual_capture": "other",
    "matrix_node_created": "other",
    "matrix_node_updated": "other",
    "matrix_node_deleted": "other",
    "matrix_edge_created": "other",
    "matrix_edge_deleted": "other",
    "audit_other": "other",
}


def bucket_for_source_kind(source_kind: str) -> str:
    """Map a ledger ``source_kind`` to its coarse display bucket ("other" when unknown)."""
    return SOURCE_KIND_BUCKETS.get(source_kind, "other")


# Boilerplate prefixes the ledger emit sites prepend to summaries (e.g.
# ``summary=f"node created: {row.title}"`` for source_kind
# ``matrix_node_created``). Keyed by source_kind; the generic
# ``source_kind.replace("_", " ")`` form is always tried as well.
_TITLE_PREFIX_ALIASES: dict[str, tuple[str, ...]] = {
    "matrix_node_created": ("node created",),
    "matrix_node_updated": ("node updated",),
    "matrix_node_deleted": ("node deleted",),
    "matrix_edge_created": ("edge created",),
    "matrix_edge_deleted": ("edge deleted",),
    "proposal_accepted": ("proposal accepted",),
    "proposal_auto_accepted": ("proposal accepted", "proposal auto accepted"),
    "proposal_rejected": ("proposal rejected",),
    "proposals_bulk_accepted": ("bulk accept",),
    "llm_proposal_created": ("proposal created",),
    "insight_opened": ("risk opened", "insight opened"),
    "insight_closed": ("risk closed", "insight closed"),
    "member_added": ("member added",),
    "member_removed": ("member removed",),
    "user_provisioned": ("user provisioned",),
}

# Remainders that carry no information on their own — when stripping a prefix
# would leave one of these, keep the full summary instead.
_DEGENERATE_TITLES: frozenset[str] = frozenset({"node", "edge"})


def humanize_event_title(source_kind: str, summary: str) -> str:
    """Return a human title for a ledger event: the summary minus boilerplate.

    Strips a leading ``"<kind words>: "`` prefix when it duplicates the
    source_kind (e.g. ``"node created: Pick vendor"`` → ``"Pick vendor"`` for
    ``matrix_node_created``). Falls back to the untouched summary when the
    stripped remainder would be empty or degenerate (``"proposal accepted:
    node"`` stays whole rather than becoming just ``"node"``).
    """
    cleaned = summary.strip()
    if not cleaned:
        return cleaned
    candidates = set(_TITLE_PREFIX_ALIASES.get(source_kind, ()))
    candidates.add(source_kind.replace("_", " "))
    lowered = cleaned.lower()
    for prefix in candidates:
        marker = f"{prefix}:"
        if lowered.startswith(marker):
            remainder = cleaned[len(marker) :].strip()
            if remainder and remainder.lower() not in _DEGENERATE_TITLES:
                return remainder
    return cleaned


def user_display_name(
    *,
    user_name: str | None,
    email: str | None,
    given_name: str | None,
    family_name: str | None,
) -> str:
    """Best display name derivable from an ``app_users`` row.

    ``app_users`` has no dedicated display-name column, so the convention is:
    ``given_name family_name`` when either is set, else the email local-part,
    else ``user_name`` (also reduced to its local-part when it is email-shaped,
    which is how JIT-provisioned members are stored).
    """
    parts = [p.strip() for p in (given_name, family_name) if p and p.strip()]
    if parts:
        return " ".join(parts)
    if email and "@" in email:
        return email.split("@", 1)[0]
    if user_name and user_name.strip():
        name = user_name.strip()
        return name.split("@", 1)[0] if "@" in name else name
    return "Unknown"


def actor_display_name(
    actor_kind: str,
    actor_id: str | None,
    display_names_by_user_id: Mapping[str, str],
) -> str:
    """Display name for a ledger event actor.

    Resolution order: system actors are always "System"; a UUID-shaped
    ``actor_id`` resolves against ``display_names_by_user_id`` (keyed by the
    stringified ``app_users.id``); an email-shaped ``actor_id`` reduces to its
    local-part; any other non-empty ``actor_id`` passes through; a missing
    ``actor_id`` (the common case for route-emitted events) shows as "System".
    """
    if actor_kind == "system":
        return "System"
    if not actor_id:
        return "System"
    try:
        key = str(uuid.UUID(actor_id))
    except ValueError:
        key = ""
    if key and key in display_names_by_user_id:
        return display_names_by_user_id[key]
    if "@" in actor_id:
        return actor_id.split("@", 1)[0]
    return actor_id


# Open/closed convention for risk matrix nodes. ``matrix_nodes.status`` is a
# nullable free-form column that nothing in the codebase writes with a fixed
# vocabulary today, so the convention chosen for ``counts.risks_open`` is:
# a risk node is OPEN unless its status (case-insensitive) is one of the
# terminal words below. NULL status counts as open.
RISK_CLOSED_STATUSES: frozenset[str] = frozenset({"closed", "resolved", "mitigated", "dismissed", "retired", "done"})


def is_risk_open(node_status: str | None) -> bool:
    """True when a risk matrix node counts as open (see ``RISK_CLOSED_STATUSES``)."""
    if node_status is None:
        return True
    return node_status.strip().lower() not in RISK_CLOSED_STATUSES


# U7 needs-attention scoring. An engagement with no ledger events at all
# (days_since_last_event is None) takes no staleness bonus — a brand-new
# engagement is not "stale".
ATTENTION_STALE_DAYS: int = 7
ATTENTION_STALE_BONUS: int = 3
ATTENTION_ESCALATION_WEIGHT: int = 2


def attention_score(
    *,
    proposals_pending: int,
    escalations_open: int,
    days_since_last_event: int | None,
) -> int:
    """U7 attention score: ``proposals + 2*escalations + (stale >= 7d ? 3 : 0)``."""
    score = proposals_pending + ATTENTION_ESCALATION_WEIGHT * escalations_open
    if days_since_last_event is not None and days_since_last_event >= ATTENTION_STALE_DAYS:
        score += ATTENTION_STALE_BONUS
    return score


__all__ = [
    "ATTENTION_ESCALATION_WEIGHT",
    "ATTENTION_STALE_BONUS",
    "ATTENTION_STALE_DAYS",
    "RECENT_CHANGE_BUCKETS",
    "RISK_CLOSED_STATUSES",
    "SOURCE_KIND_BUCKETS",
    "actor_display_name",
    "attention_score",
    "bucket_for_source_kind",
    "humanize_event_title",
    "is_risk_open",
    "user_display_name",
]
