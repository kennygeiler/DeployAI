"""Unit tests for the Wave 2.5 legibility helpers (tickets U2/U6/U7).

Covers the source_kind → bucket map, ledger title humanization, display-name
derivation, the risk open/closed convention, and the attention-score formula.
"""

from __future__ import annotations

import uuid

from control_plane.ledger.emitter import ALLOWED_SOURCE_KINDS
from control_plane.services.engagement_legibility import (
    ATTENTION_STALE_DAYS,
    RECENT_CHANGE_BUCKETS,
    SOURCE_KIND_BUCKETS,
    TELEMETRY_SOURCE_KINDS,
    actor_display_name,
    attention_score,
    bucket_for_source_kind,
    humanize_event_title,
    is_risk_open,
    user_display_name,
)


class TestSourceKindBuckets:
    def test_every_mapped_value_is_a_known_bucket(self) -> None:
        for source_kind, bucket in SOURCE_KIND_BUCKETS.items():
            assert bucket in RECENT_CHANGE_BUCKETS, f"{source_kind} -> {bucket}"

    def test_every_emitter_source_kind_is_mapped(self) -> None:
        """The bucket map covers the emitter's whole validated vocabulary."""
        missing = ALLOWED_SOURCE_KINDS - SOURCE_KIND_BUCKETS.keys()
        assert not missing, f"unmapped emitter source_kinds: {sorted(missing)}"

    def test_representative_mappings(self) -> None:
        assert bucket_for_source_kind("decision") == "decision"
        assert bucket_for_source_kind("risk_opened") == "risk"
        assert bucket_for_source_kind("insight_closed") == "risk"
        assert bucket_for_source_kind("member_added") == "stakeholder"
        assert bucket_for_source_kind("followup_task_created") == "commitment"
        assert bucket_for_source_kind("proposal_accepted") == "proposal"
        assert bucket_for_source_kind("llm_proposal_created") == "proposal"
        assert bucket_for_source_kind("oracle_chat_turn") == "agent"
        assert bucket_for_source_kind("agent_approval_requested") == "agent"
        assert bucket_for_source_kind("settings_change") == "system"
        assert bucket_for_source_kind("email_ingest") == "other"
        assert bucket_for_source_kind("matrix_node_created") == "other"

    def test_unknown_source_kind_falls_back_to_other(self) -> None:
        assert bucket_for_source_kind("something_never_seen") == "other"


class TestTelemetrySourceKinds:
    """The digest exclusion set — agent-run telemetry never reaches recent_changes."""

    def test_every_telemetry_kind_is_a_real_emitter_kind(self) -> None:
        """Guards against typos: the set must be a subset of the emitter vocabulary."""
        unknown = TELEMETRY_SOURCE_KINDS - ALLOWED_SOURCE_KINDS
        assert not unknown, f"telemetry kinds unknown to the emitter: {sorted(unknown)}"

    def test_agent_operation_kinds_are_telemetry(self) -> None:
        for kind in (
            "agent_tool_invocation",
            "oracle_chat_turn",
            "oracle_conversation_started",
            "propose_action",
            "agent_synthesis_emitted",
            "synthesis_failed",
            "agent_audit_concern",
            "agent_concern_logged",
            "agent_approval_requested",
            "agent_approval_granted",
            "agent_approval_denied",
            "review_item_created",
            "review_item_dismissed",
            "mcp_tool_invocation",
            "mcp_outbound_call",
            "mcp_outbound_rate_limited",
            "mcp_outbound_egress_blocked",
            "killswitch_queue_purged",
        ):
            assert kind in TELEMETRY_SOURCE_KINDS, kind

    def test_domain_kinds_are_not_telemetry(self) -> None:
        for kind in (
            "email_ingest",
            "meeting_webhook",
            "manual_capture",
            "llm_proposal_created",
            "proposal_accepted",
            "proposal_rejected",
            "proposal_auto_accepted",
            "matrix_node_created",
            "insight_opened",
            "insight_closed",
            "engagement_phase_change",
            "member_added",
            "member_removed",
            "followup_task_created",
            "human_escalation_answer",
            "recommendation_emitted",
            "recommendation_actioned",
            "settings_change",
            "mcp_outbound_killswitch_changed",
        ):
            assert kind not in TELEMETRY_SOURCE_KINDS, kind

    def test_agent_bucket_still_reachable_without_telemetry(self) -> None:
        """The "agent" bucket survives the exclusion via agent-loop outcomes
        surfaced to humans (recommendations, escalation answers)."""
        reachable = {kind for kind, bucket in SOURCE_KIND_BUCKETS.items() if bucket == "agent"}
        non_telemetry = reachable - TELEMETRY_SOURCE_KINDS
        assert non_telemetry, "every agent-bucketed kind is excluded as telemetry"
        assert "human_escalation_answer" in non_telemetry
        assert "recommendation_emitted" in non_telemetry


class TestHumanizeEventTitle:
    def test_strips_boilerplate_prefix(self) -> None:
        assert humanize_event_title("matrix_node_created", "node created: Pick vendor") == "Pick vendor"
        assert (
            humanize_event_title("insight_opened", "risk opened: claims-viewer p95 over SLA")
            == "claims-viewer p95 over SLA"
        )
        assert humanize_event_title("member_added", "member added: fde") == "fde"

    def test_strips_generic_source_kind_prefix(self) -> None:
        assert humanize_event_title("decision", "decision: adopt caching layer") == "adopt caching layer"

    def test_keeps_summary_when_remainder_degenerate(self) -> None:
        # "proposal accepted: node" would become just "node" — keep the whole line.
        assert humanize_event_title("proposal_accepted", "proposal accepted: node") == "proposal accepted: node"
        assert humanize_event_title("proposal_accepted", "proposal accepted: edge") == "proposal accepted: edge"

    def test_keeps_summary_without_prefix(self) -> None:
        assert humanize_event_title("email_ingest", "Sarah -> Patricia: weekly status W2") == (
            "Sarah -> Patricia: weekly status W2"
        )

    def test_prefix_match_is_case_insensitive(self) -> None:
        assert humanize_event_title("matrix_node_updated", "Node Updated: Cache layer") == "Cache layer"


class TestUserDisplayName:
    def test_given_family_name_wins(self) -> None:
        assert (
            user_display_name(
                user_name="alex.chen", email="alex.chen@deployai.com", given_name="Alex", family_name="Chen"
            )
            == "Alex Chen"
        )

    def test_partial_name_used(self) -> None:
        assert user_display_name(user_name="x", email=None, given_name="Alex", family_name=None) == "Alex"

    def test_email_local_part_fallback(self) -> None:
        assert (
            user_display_name(
                user_name="jordan.park@deployai.com",
                email="jordan.park@deployai.com",
                given_name=None,
                family_name=None,
            )
            == "jordan.park"
        )

    def test_user_name_fallback(self) -> None:
        assert user_display_name(user_name="sam.lee", email=None, given_name=None, family_name=None) == "sam.lee"

    def test_email_shaped_user_name_reduced_to_local_part(self) -> None:
        assert user_display_name(user_name="pat@example.com", email=None, given_name=None, family_name=None) == "pat"


class TestActorDisplayName:
    def test_system_actor_kind_is_system(self) -> None:
        assert actor_display_name("system", "auto_accept", {}) == "System"

    def test_missing_actor_id_is_system(self) -> None:
        assert actor_display_name("user", None, {}) == "System"

    def test_uuid_actor_resolves_against_map(self) -> None:
        uid = uuid.uuid4()
        assert actor_display_name("user", str(uid), {str(uid): "Alex Chen"}) == "Alex Chen"

    def test_unresolved_uuid_passes_through(self) -> None:
        uid = str(uuid.uuid4())
        assert actor_display_name("user", uid, {}) == uid

    def test_email_actor_reduced_to_local_part(self) -> None:
        assert actor_display_name("user", "marcus.rivera@deployai.com", {}) == "marcus.rivera"

    def test_plain_string_actor_passes_through(self) -> None:
        assert actor_display_name("agent", "kenny", {}) == "kenny"


class TestRiskOpenConvention:
    def test_null_status_is_open(self) -> None:
        assert is_risk_open(None) is True

    def test_free_form_status_is_open(self) -> None:
        assert is_risk_open("investigating") is True

    def test_terminal_statuses_are_closed(self) -> None:
        for terminal in ("closed", "resolved", "Mitigated", "DISMISSED", " retired ", "done"):
            assert is_risk_open(terminal) is False, terminal


class TestAttentionScore:
    def test_zero_inputs_zero_score(self) -> None:
        assert attention_score(proposals_pending=0, escalations_open=0, days_since_last_event=0) == 0

    def test_formula_weights(self) -> None:
        assert attention_score(proposals_pending=3, escalations_open=2, days_since_last_event=1) == 7

    def test_stale_bonus_applies_at_threshold(self) -> None:
        assert attention_score(proposals_pending=0, escalations_open=0, days_since_last_event=ATTENTION_STALE_DAYS) == 3
        assert (
            attention_score(proposals_pending=0, escalations_open=0, days_since_last_event=ATTENTION_STALE_DAYS - 1)
            == 0
        )

    def test_none_days_takes_no_stale_bonus(self) -> None:
        assert attention_score(proposals_pending=1, escalations_open=1, days_since_last_event=None) == 3

    def test_combined(self) -> None:
        assert attention_score(proposals_pending=2, escalations_open=3, days_since_last_event=30) == 11
