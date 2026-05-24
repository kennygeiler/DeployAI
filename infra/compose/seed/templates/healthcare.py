"""Healthcare / EHR-rollout template."""

from __future__ import annotations

from . import Template

_CARTOGRAPHER_SUFFIX = (
    "The engagements you analyze are health-system deployments — typically "
    "EHR module rollouts, payer-integration projects, or clinical-workflow "
    "automation. Favor stakeholder nodes for the CMIO, CNIO, service-line "
    "chief, compliance officer, and physician champions; organization nodes "
    "for clinical service lines, the IT department, and the privacy office; "
    "system nodes for the core EHR (Epic / Cerner / Meditech), HL7 / FHIR "
    "interfaces, lab systems, and patient portals; risk nodes for HIPAA / "
    "PHI exposure, clinician burnout / change-fatigue, and "
    "Joint-Commission audit overlap; decision nodes for IRB / safety-committee "
    "approvals and go-live cutover windows. Treat any mention of 'BAA', "
    "'PHI', 'minimum necessary', or a regulatory citation as high-signal."
)

_ORACLE_SUFFIX = (
    "You are reviewing a healthcare deployment. Treat absence of a named "
    "physician champion as a critical risk on any clinical-workflow "
    "change. Flag PHI-touching systems without a documented BAA or named "
    "compliance owner as a major risk. Surface insights where a planned "
    "go-live falls inside a high-census period (open enrollment, flu "
    "season, end-of-year reporting). Favor dependency insights that "
    "trace clinical decisions back to the upstream interface or data "
    "owner — clinical-workflow gaps usually have a system-integration root."
)

_MASTER_STRATEGIST_SUFFIX = (
    "Across this team's portfolio of health-system engagements, look for "
    "patterns that scale: the same EHR vendor or integration engine "
    "blocking change across multiple systems, recurring clinician-burnout "
    "signals, regulatory updates that trigger fleet-wide work, and IDN / "
    "GPO purchasing leverage. Opportunity insights should prioritize "
    "expansions within an existing health system (new service line, new "
    "site) before suggesting cross-system land-and-expand — switching "
    "costs are high and references compound slowly in this vertical."
)

TEMPLATE = Template(
    name="healthcare",
    default_engagement_name="EHR workflow rollout",
    default_customer_account="Sample Health System",
    default_phase="P2_discovery",
    starter_nodes=[
        {
            "node_type": "stakeholder",
            "title": "Chief Medical Information Officer (executive sponsor)",
            "attributes": {"role": "executive_sponsor", "function": "clinical_informatics"},
        },
        {
            "node_type": "stakeholder",
            "title": "Service-line physician champion",
            "attributes": {"role": "champion", "function": "clinical"},
        },
        {
            "node_type": "system",
            "title": "Core EHR (Epic / Cerner / Meditech)",
            "attributes": {"category": "ehr"},
        },
        {
            "node_type": "risk",
            "title": "PHI handling requires signed BAA before integration testing",
            "attributes": {"category": "compliance"},
            "status": "open",
        },
        {
            "node_type": "decision",
            "title": "Go-live cutover window (avoid high-census periods)",
            "attributes": {"owner": "clinical_operations"},
            "status": "pending",
        },
    ],
    agent_prompts={
        "cartographer": _CARTOGRAPHER_SUFFIX,
        "oracle": _ORACLE_SUFFIX,
        "master_strategist": _MASTER_STRATEGIST_SUFFIX,
    },
)
