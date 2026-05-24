"""B2B SaaS pilot + feature-flag rollout template."""

from __future__ import annotations

from . import Template

_CARTOGRAPHER_SUFFIX = (
    "The engagements you analyze are B2B SaaS pilots and phased "
    "feature-flag rollouts inside a single customer account. Favor "
    "stakeholder nodes for the economic buyer, the technical champion, the "
    "evaluation lead, and the security reviewer; organization nodes for the "
    "buyer's engineering, IT-security, and procurement teams; system nodes "
    "for the customer's identity provider (Okta / Azure AD), their data "
    "warehouse, their CI/CD platform, and any incumbent tool being "
    "displaced; risk nodes for security-review blockers (SOC2 / SIG / "
    "vendor questionnaire), pricing pushback, and champion-departure risk; "
    "decision nodes for pilot-to-production conversion, seat expansion, "
    "and renewal terms. Treat mentions of 'POC criteria', 'success "
    "metrics', 'security review', or 'MSA' as high-signal."
)

_ORACLE_SUFFIX = (
    "You are reviewing a SaaS pilot or rollout engagement. Treat "
    "absence of written pilot success criteria as a critical risk — "
    "without them, pilots renew indefinitely instead of converting. "
    "Flag any commitment to engineering work from the customer side "
    "as a major risk (their roadmap rarely makes room). Surface "
    "insights where a single champion holds all relationship gravity. "
    "Favor dependency insights that trace adoption back to feature-flag "
    "or SSO/SCIM gating — most stalled rollouts are blocked on "
    "provisioning, not product fit."
)

_MASTER_STRATEGIST_SUFFIX = (
    "Across this team's SaaS portfolio, look for patterns that scale: "
    "the same security-questionnaire blocker repeating across accounts, "
    "the same pricing-model objection, common usage-pattern wedges that "
    "predict expansion, and integration-partner co-sell opportunities. "
    "Opportunity insights should prioritize expansion inside accounts "
    "already past the security-review gate over new logos — the "
    "marginal cost of a second team at an existing customer is "
    "dramatically lower than landing a net-new account."
)

TEMPLATE = Template(
    name="saas",
    default_engagement_name="Pilot to production rollout",
    default_customer_account="Sample SaaS Customer",
    default_phase="P2_discovery",
    starter_nodes=[
        {
            "node_type": "stakeholder",
            "title": "Economic buyer (VP / Director)",
            "attributes": {"role": "economic_buyer"},
        },
        {
            "node_type": "stakeholder",
            "title": "Technical champion / evaluation lead",
            "attributes": {"role": "champion"},
        },
        {
            "node_type": "system",
            "title": "Customer identity provider (SSO / SCIM)",
            "attributes": {"category": "identity"},
        },
        {
            "node_type": "risk",
            "title": "Security review (SOC2 / vendor questionnaire) gates pilot expansion",
            "attributes": {"category": "security_review"},
            "status": "open",
        },
        {
            "node_type": "decision",
            "title": "Pilot success criteria + conversion threshold",
            "attributes": {"owner": "economic_buyer"},
            "status": "pending",
        },
    ],
    agent_prompts={
        "cartographer": _CARTOGRAPHER_SUFFIX,
        "oracle": _ORACLE_SUFFIX,
        "master_strategist": _MASTER_STRATEGIST_SUFFIX,
    },
)
