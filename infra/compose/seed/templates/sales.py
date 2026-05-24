"""Enterprise sales cycle with multi-stakeholder approval template."""

from __future__ import annotations

from . import Template

_CARTOGRAPHER_SUFFIX = (
    "The engagements you analyze are enterprise sales cycles with "
    "multi-stakeholder approval — typically six- or seven-figure ACV deals "
    "with a buying committee. Favor stakeholder nodes for the economic "
    "buyer, the executive sponsor, the technical evaluator, the legal / "
    "procurement contact, and any identified blocker; organization nodes "
    "for the buyer's finance, legal, security, and procurement functions; "
    "decision nodes for budget approval, vendor security review, MSA / "
    "redlines, and final committee sign-off; risk nodes for champion "
    "departure, competitive displacement, budget freeze, and "
    "fiscal-quarter slippage; commitment nodes for the agreed evaluation "
    "milestones, customer references, and pilot deliverables. Treat "
    "mentions of 'mutual close plan', 'metric', 'redline', 'BATNA', or "
    "named competitors as high-signal."
)

_ORACLE_SUFFIX = (
    "You are reviewing an enterprise sales engagement. Treat "
    "single-threaded coverage (only one champion, no exec sponsor) as a "
    "critical risk on any deal over a quarter old. Flag deals lacking "
    "a documented mutual close plan or written success criteria as a "
    "major risk. Surface insights where the buying committee includes "
    "a function (security, legal, finance) the sales team has not yet "
    "engaged. Favor dependency insights that trace a stalled stage back "
    "to a missing prerequisite — most slipped deals are blocked on a "
    "single approval, not on product fit."
)

_MASTER_STRATEGIST_SUFFIX = (
    "Across this team's enterprise-sales portfolio, look for patterns "
    "that scale: deals stalling at the same buying-committee stage, "
    "recurring competitive losses to the same vendor, fiscal-quarter "
    "concentration risk, and reference-account opportunities. "
    "Opportunity insights should prioritize multi-thread expansion in "
    "active deals (adding stakeholders, scheduling exec syncs) over "
    "net-new pipeline generation — won deals shorten the next deal's "
    "cycle far more than new leads do."
)

TEMPLATE = Template(
    name="sales",
    default_engagement_name="Enterprise sales cycle",
    default_customer_account="Sample Enterprise Prospect",
    default_phase="P1_pre_engagement",
    starter_nodes=[
        {
            "node_type": "stakeholder",
            "title": "Economic buyer (VP / SVP)",
            "attributes": {"role": "economic_buyer"},
        },
        {
            "node_type": "stakeholder",
            "title": "Technical evaluator",
            "attributes": {"role": "evaluator"},
        },
        {
            "node_type": "decision",
            "title": "Vendor security review + MSA redlines",
            "attributes": {"owner": "procurement"},
            "status": "pending",
        },
        {
            "node_type": "risk",
            "title": "Champion departure risk (single-threaded coverage)",
            "attributes": {"category": "coverage"},
            "status": "open",
        },
        {
            "node_type": "commitment",
            "title": "Mutual close plan + success criteria signed by buyer",
            "attributes": {"owner": "deal_team"},
            "status": "open",
        },
    ],
    agent_prompts={
        "cartographer": _CARTOGRAPHER_SUFFIX,
        "oracle": _ORACLE_SUFFIX,
        "master_strategist": _MASTER_STRATEGIST_SUFFIX,
    },
)
