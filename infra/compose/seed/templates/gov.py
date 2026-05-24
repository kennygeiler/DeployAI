"""Government / municipality permit-modernization template."""

from __future__ import annotations

from . import Template

_CARTOGRAPHER_SUFFIX = (
    "The engagements you analyze are county and municipal government "
    "permit-modernization deployments. Favor stakeholder nodes for elected "
    "officials, agency directors, department heads, and union representatives; "
    "system nodes for legacy permitting platforms, GIS systems, and "
    "constituent-facing portals; decision nodes for procurement-board votes, "
    "council resolutions, and statutory deadlines; risk nodes for "
    "FOIA / open-records exposure, ADA accessibility findings, election-cycle "
    "schedule pressure, and union work-rule constraints. Flag commitments "
    "that imply a public records obligation. Treat anything mentioning "
    "'RFP', 'sole-source', 'sunshine law', or a specific statute as a "
    "high-signal extraction target. Government deployments move on "
    "fiscal-year boundaries — favor commitment nodes that pin a calendar date."
)

_ORACLE_SUFFIX = (
    "You are reviewing a government deployment. Treat absence of a named "
    "elected sponsor as a critical risk; procurements without a recorded "
    "sole-source justification or competitive-bid trail as a major risk; "
    "any commitment whose due date crosses a fiscal-year boundary as worth "
    "surfacing. Favor cross-department dependency insights (the permit "
    "office rarely owns its own data, IT, and legal review). Flag systems "
    "that touch constituent PII without a named data-owner."
)

_MASTER_STRATEGIST_SUFFIX = (
    "Across this team's portfolio of government engagements, look for "
    "patterns that scale: the same legacy vendor blocking modernization "
    "across multiple counties, the same elected-official archetype "
    "championing or stalling deployments, recurring statutory-deadline "
    "pressure, and consortium / cooperative-purchasing opportunities. "
    "Opportunity insights should prioritize repeatable wins inside a single "
    "state's procurement framework before suggesting cross-state expansion."
)

TEMPLATE = Template(
    name="gov",
    default_engagement_name="Permit modernization rollout",
    default_customer_account="Sample County, Sample State",
    default_phase="P2_discovery",
    starter_nodes=[
        {
            "node_type": "stakeholder",
            "title": "County Permitting Director (executive sponsor)",
            "attributes": {"role": "executive_sponsor", "agency": "permitting"},
        },
        {
            "node_type": "organization",
            "title": "County IT department",
            "attributes": {"function": "platform_owner"},
        },
        {
            "node_type": "system",
            "title": "Legacy permitting platform (on-prem)",
            "attributes": {"vendor": "incumbent", "hosting": "on_prem"},
        },
        {
            "node_type": "risk",
            "title": "Procurement board approval window closes at FY end",
            "attributes": {"category": "schedule"},
            "status": "open",
        },
        {
            "node_type": "decision",
            "title": "Sole-source vs. competitive RFP path",
            "attributes": {"owner": "procurement_board"},
            "status": "pending",
        },
    ],
    agent_prompts={
        "cartographer": _CARTOGRAPHER_SUFFIX,
        "oracle": _ORACLE_SUFFIX,
        "master_strategist": _MASTER_STRATEGIST_SUFFIX,
    },
)
