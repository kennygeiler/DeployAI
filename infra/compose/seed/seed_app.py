#!/usr/bin/env python3
"""Phase 6.2c — repeatable app-schema seed for manual testing.

Populates one realistic engagement against the running compose stack:

  * 1 app_tenant + 3 app_users (deployment team)
  * 1 engagement (gov/policy domain: county permit-modernization rollout)
  * 3 engagement_members (one per team role)
  * ~20 canonical_memory_events (emails, meeting notes, field notes, memos)
  * Triggers Cartographer extraction per event so matrix proposals exist
    before you open the engagement detail page

Idempotent: rerunning with the same stable UUIDs is a no-op for tenant /
user / engagement rows, and ingest dedup_key keeps events from duplicating.
Extraction is also idempotent per (event, status=pending) — pass
``--force-extract`` to discard pending proposals and re-run the LLM.

Usage:
    python3 infra/compose/seed/seed_app.py [--force-extract]
or:
    make seed-app

Requires the compose stack already up (postgres + control-plane healthy)
and ``ANTHROPIC_API_KEY`` / ``DEPLOYAI_LLM_PROVIDER=anthropic`` set in
``infra/compose/.env`` to get real LLM proposals (otherwise the stub
provider runs and the proposals list will be empty).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO_ROOT / "infra" / "compose" / "docker-compose.yml"
ENV_FILE = REPO_ROOT / "infra" / "compose" / ".env"

# Stable UUIDs — re-running the seed targets the same rows.
TENANT_ID = "11111111-1111-1111-1111-111111111111"
ENGAGEMENT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
USER_STRATEGIST_ID = "aaaaaaa1-1111-4111-8111-111111111111"
USER_FDE_ID = "aaaaaaa2-2222-4222-8222-222222222222"
USER_BIZDEV_ID = "aaaaaaa3-3333-4333-8333-333333333333"

TENANT_NAME = "acme-county-pilot"
ENGAGEMENT_NAME = "Acme County permit-modernization rollout"
CUSTOMER_ACCOUNT = "Acme County, CA"
CURRENT_PHASE = "discovery"

CP_BASE_URL = os.environ.get("DEPLOYAI_CP_BASE_URL", "http://localhost:8000")
WEB_BASE_URL = os.environ.get("DEPLOYAI_WEB_BASE_URL", "http://localhost:3000")


def _load_env_file() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ENV_FILE.exists():
        return out
    for raw in ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


ENV = _load_env_file()
INTERNAL_KEY = (
    os.environ.get("DEPLOYAI_INTERNAL_API_KEY")
    or ENV.get("DEPLOYAI_INTERNAL_API_KEY")
    or "dev-internal-insecure"
)
POSTGRES_USER = ENV.get("POSTGRES_USER", "deployai")
POSTGRES_DB = ENV.get("POSTGRES_DB", "deployai")


@dataclass(frozen=True)
class SeedEvent:
    """One canonical_memory_events row to ingest."""

    dedup_key: str
    source: str  # manual_import | meeting_note | email | field_note
    occurred_at: datetime
    title: str  # for log output only
    text: str
    source_ref: str | None = None


def _dt(week: int, day: int = 1, hour: int = 9) -> datetime:
    """Anchor a date relative to a fixed start so reseeds are stable."""
    base = datetime(2026, 3, 2, tzinfo=UTC)
    return base + timedelta(weeks=week - 1, days=day - 1, hours=hour - 9)


SEED_EVENTS: list[SeedEvent] = [
    SeedEvent(
        dedup_key="seed-w1-bd-outreach",
        source="email",
        occurred_at=_dt(1, 1, 9),
        title="BD outreach — Sam Lee → Dana Carter",
        source_ref="email-1",
        text=(
            "From: Sam Lee <sam.lee@deployai.com>\n"
            "To: Dana Carter <dana.carter@acmecounty.gov>\n"
            "Subject: Re: County permit modernization — DeployAI follow-up\n\n"
            "Hi Dana,\n\n"
            "Thanks again for the intro at the NACo conference. Following up on our "
            "conversation about Acme County's paper-based permit intake. We've worked "
            "with three counties of similar size (Polk, Marion, and Travis) to replace "
            "their legacy permit systems with a unified intake + workflow platform.\n\n"
            "Would Priya have time next week for a 30-minute scoping call? We can walk "
            "through the typical 90-day pilot structure and where most counties see early "
            "wins. I'd suggest looping in your IT lead too if available.\n\n"
            "Best,\nSam\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w1-internal-forward",
        source="email",
        occurred_at=_dt(1, 2, 14),
        title="Internal forward — Dana → Priya",
        source_ref="email-2",
        text=(
            "From: Dana Carter <dana.carter@acmecounty.gov>\n"
            "To: Priya Raman <priya.raman@acmecounty.gov>\n"
            "Subject: Fwd: DeployAI permit-modernization pitch\n\n"
            "Priya,\n\n"
            "Forwarding the DeployAI follow-up below. I think it's worth taking the "
            "scoping call — we've been talking about replacing the paper intake for two "
            "budget cycles now and they have references at Polk and Marion counties.\n\n"
            "Heads up: Yuki will want to be in the room on anything that touches resident "
            "PII. And we should probably loop Marcus in on the policy side.\n\n"
            "Dana\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w1-internal-scoping",
        source="meeting_note",
        occurred_at=_dt(1, 3, 10),
        title="DeployAI internal scoping call",
        source_ref="notion://meetings/internal-scoping-2026-03-04",
        text=(
            "DeployAI internal scoping call — Acme County opportunity\n"
            "Attendees: Alex Chen (deployment strategist), Jordan Park (FDE), Sam Lee (biz dev)\n\n"
            "Sam Lee briefed the team on the Acme County conversation. Dana Carter (CoS) is "
            "champion, Priya Raman (Deputy Director) is the exec sponsor and budget owner. "
            "County has a paper-based permit intake — high pain, high political visibility.\n\n"
            "Plan for week 1:\n"
            "- Sam Lee: schedule discovery call w/ Dana + Priya within 7 days\n"
            "- Jordan: pull case studies from Polk and Marion deployments\n"
            "- Alex: draft 90-day pilot template, prep risk register skeleton\n\n"
            "Risks flagged: county has had two failed vendor engagements in last 5 years "
            "(per Sam Lee's contact at NACo). Yuki Tanaka in counsel is reportedly skeptical "
            "of cloud-hosted PII. We need a credible data-residency story before week 3.\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w2-discovery",
        source="meeting_note",
        occurred_at=_dt(2, 1, 14),
        title="Discovery call w/ Acme County",
        source_ref="notion://meetings/acme-discovery-2026-03-09",
        text=(
            "Discovery call — Acme County permit modernization\n"
            "Attendees: Dana Carter (Acme CoS), Priya Raman (Acme Deputy Director), "
            "Alex Chen (DeployAI strategist), Sam Lee (DeployAI biz dev)\n\n"
            "Priya opened by stating the goal: cut permit-intake-to-decision time from "
            "the current 6-week median down to 10 business days, without increasing "
            "headcount. Volume is ~850 permits/month, ~70% residential.\n\n"
            "Current state: paper applications filed at counter, manually keyed into a "
            "FileMaker database, routed to reviewers via interoffice mail. Two clerks "
            "(Maria + Joel) handle all intake.\n\n"
            "Constraints surfaced:\n"
            "- All PII must stay in US-based infrastructure (Yuki's requirement, county counsel)\n"
            "- Integration with the legacy GIS system (ArcGIS, on-prem) is mandatory\n"
            "- Pilot must not disrupt the current paper path — must run in parallel\n\n"
            "Next steps: Alex to schedule technical walkthrough w/ county IT (week 3), "
            "Sam Lee to share Polk County reference, Priya to brief Yuki by end of week.\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w2-onsite-visit",
        source="field_note",
        occurred_at=_dt(2, 3, 11),
        title="Alex on-site at Acme permit office",
        source_ref="field://alex-2026-03-11",
        text=(
            "Field note — Alex Chen on-site at Acme County permit office\n\n"
            "Spent the morning at the public counter. Observations:\n\n"
            "Maria (senior intake clerk, ~12 years on the job) is the de-facto subject-matter "
            "expert. Every reviewer eventually walks back to her desk to ask what a form "
            "means. She does not have a job description that reflects this. Major key-person "
            "risk — if Maria leaves, intake stops.\n\n"
            "Average resident wait time when I observed: 47 minutes for a routine permit. "
            "Two people gave up and left while I was watching. Spanish-speaking residents "
            "were routed to a different clerk who was not always available.\n\n"
            "FileMaker database is on a single workstation. No backup that I could see. "
            "When the workstation reboots (happens ~weekly per Maria), intake stops.\n\n"
            "Politically: a county supervisor walked through and asked Maria when the new "
            "system 'is finally happening.' This is a known sore subject up the chain.\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w2-counsel-privacy",
        source="email",
        occurred_at=_dt(2, 4, 16),
        title="Yuki Tanaka raises privacy concerns",
        source_ref="email-7",
        text=(
            "From: Yuki Tanaka <yuki.tanaka@acmecounty.gov>\n"
            "To: Alex Chen <alex.chen@deployai.com>\n"
            "Cc: Priya Raman, Dana Carter\n"
            "Subject: Data residency + retention questions before we go further\n\n"
            "Alex,\n\n"
            "Before we commit to a pilot I need clear answers on three items:\n\n"
            "1. Where, physically, are resident PII fields stored? County counsel position "
            "is that this data cannot leave US infrastructure under any circumstance.\n\n"
            "2. What is the data-retention default and can the county set it? Our records "
            "schedule requires permit application data be retained for 7 years from final "
            "decision, but deleted afterward unless there is active litigation.\n\n"
            "3. What is the contractual exit path? If we end the engagement, how do we get "
            "all county data back in a usable format, and how do you certify deletion on "
            "your side?\n\n"
            "Please respond in writing before the technical walkthrough next week.\n\n"
            "Yuki Tanaka, County Counsel\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w3-tech-walkthrough",
        source="meeting_note",
        occurred_at=_dt(3, 1, 10),
        title="Technical walkthrough w/ Acme IT",
        source_ref="notion://meetings/acme-tech-walkthrough-2026-03-16",
        text=(
            "Technical walkthrough — Acme County IT\n"
            "Attendees: Jordan Park (DeployAI FDE), Marcus Okafor (Acme policy lead), "
            "Tom Reyes (Acme IT director), Alex Chen (DeployAI)\n\n"
            "Jordan walked through DeployAI's intake → review → decision pipeline and the "
            "integration surface area. Tom confirmed the legacy GIS is ArcGIS Enterprise "
            "10.9 running on-prem with REST endpoints exposed internally only.\n\n"
            "Decision: the pilot will run as a parallel intake path. Paper continues. "
            "DeployAI's web intake submits to a staging table; reviewers see both feeds "
            "in one queue during the 90-day pilot.\n\n"
            "Integration plan: Jordan will write the ArcGIS adapter; Tom will open a "
            "read-only service account for parcel lookups by week 5.\n\n"
            "Yuki's privacy concerns: Alex committed to a written response by end of "
            "week. Tom noted that the county's existing cloud usage (Office 365) is in "
            "US-East Azure, so cloud-hosted is not categorically blocked — but US-based "
            "infra is firm.\n\n"
            "Open risk: county has no internal capacity to maintain the integration once "
            "DeployAI rolls off. Marcus suggested raising this with Priya — may need to "
            "scope a year of post-pilot support.\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w3-vendor-comparison",
        source="email",
        occurred_at=_dt(3, 3, 17),
        title="Marcus → Priya: vendor comparison",
        source_ref="email-10",
        text=(
            "From: Marcus Okafor <marcus.okafor@acmecounty.gov>\n"
            "To: Priya Raman\n"
            "Subject: Vendor comparison for permit modernization — three options\n\n"
            "Priya,\n\n"
            "Per your request, here is the short list. All three were contacted in the "
            "last 60 days.\n\n"
            "Option 1: DeployAI\n"
            "- 90-day pilot, parallel-run model, $180k pilot fee + post-pilot SaaS at $42k/yr\n"
            "- References at Polk County (live 18 months) and Marion County (live 9 months)\n"
            "- Counsel concerns about cloud PII — DeployAI is preparing written response\n\n"
            "Option 2: CivicTech Solutions\n"
            "- 6-month implementation, no pilot, $340k all-in + $60k/yr support\n"
            "- Three failed deployments in CA in last 3 years (per CSAC informal network)\n"
            "- Requires rip-and-replace of FileMaker; no parallel-run option\n\n"
            "Option 3: Tyler Technologies\n"
            "- Full modernization (permits + planning + code enforcement) for $1.4M\n"
            "- 18-month timeline, would require dedicated PM on our side\n"
            "- Scope is bigger than what we have budget approval for\n\n"
            "My read: DeployAI's pilot model is the only path that lets us validate "
            "before committing real money. CivicTech is too risky given the deployment "
            "track record. Tyler is the right product but wrong time given budget cycle.\n\n"
            "Recommending DeployAI subject to Yuki signing off on the data-residency "
            "response.\n\n"
            "Marcus\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w3-vendor-decision",
        source="manual_import",
        occurred_at=_dt(3, 5, 16),
        title="Decision memo — vendor selection",
        source_ref="memo://priya-vendor-decision-2026-03-20",
        text=(
            "Decision memo — Permit modernization vendor selection\n"
            "Author: Priya Raman, Deputy Director\n"
            "Date: 2026-03-20\n\n"
            "Decision: Acme County will engage DeployAI for a 90-day pilot of their "
            "permit intake + review platform, contingent on County Counsel's written "
            "approval of their data-residency commitments (expected within the week).\n\n"
            "Pilot scope: parallel intake path, ~850 permits/month covered, residential "
            "and commercial. No retirement of the paper path during the pilot.\n\n"
            "Budget: $180,000 from FY26 modernization fund (Sam Lindgren confirmed "
            "available 2026-03-19). Post-pilot SaaS commitment requires Board approval; "
            "not part of this decision.\n\n"
            "Success criteria for pilot extension to production:\n"
            "1. Median intake-to-decision time reduced from 6 weeks to ≤ 15 business days\n"
            "2. Zero resident PII data leaving US infrastructure (audit-confirmed)\n"
            "3. Maria + Joel both report the new system is faster than paper for them\n\n"
            "If two of three criteria are met, the pilot is extended for a further 90 "
            "days to allow Board approval cycle. If fewer than two, the pilot is closed "
            "and DeployAI is paid the agreed pilot fee with no further commitment.\n\n"
            "/s/ Priya Raman\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w4-kickoff",
        source="meeting_note",
        occurred_at=_dt(4, 1, 9),
        title="Pilot kickoff",
        source_ref="notion://meetings/acme-kickoff-2026-03-23",
        text=(
            "Pilot kickoff — Acme County × DeployAI permit modernization\n"
            "Attendees: Dana Carter, Priya Raman, Marcus Okafor, Yuki Tanaka, Tom Reyes, "
            "Maria Sandoval (intake clerk), Alex Chen, Jordan Park, Sam Lee\n\n"
            "Yuki confirmed her data-residency concerns are resolved — DeployAI's written "
            "response (delivered 2026-03-21) committed to US-East-1 only, with quarterly "
            "third-party attestation. She signed off in the meeting.\n\n"
            "Priya re-read the three pilot success criteria for the record and confirmed "
            "the budget commitment.\n\n"
            "Maria walked the group through her current daily intake routine. Two things "
            "that surprised the DeployAI team: (1) ~15% of applications arrive incomplete "
            "and require a phone call back, and (2) Spanish-language applications take ~3x "
            "as long because there is no bilingual form.\n\n"
            "Risks logged for tracking:\n"
            "- Risk: Maria is single point of failure on subject-matter knowledge (from "
            "Alex's onsite). Mitigation: pair Maria w/ Jordan for first 2 weeks to capture "
            "her tacit knowledge.\n"
            "- Risk: Community pushback on digital-only intake (Rita Alvarez raised). "
            "Mitigation: pilot keeps paper path open; no resident is forced to use new system.\n"
            "- Risk: Tom's IT team has no capacity to maintain the ArcGIS integration "
            "post-pilot. Mitigation: Priya to evaluate a 1-year support contract before "
            "pilot ends.\n\n"
            "Next checkpoint: 2026-04-13 (3 weeks in).\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w4-budget-caveat",
        source="email",
        occurred_at=_dt(4, 2, 11),
        title="Sam Lindgren on budget caveats",
        source_ref="email-15",
        text=(
            "From: Sam Lindgren <sam.lindgren@acmecounty.gov>\n"
            "To: Priya Raman\n"
            "Subject: FY26 mod fund — pilot encumbrance + caveats\n\n"
            "Priya,\n\n"
            "The $180k is encumbered against the FY26 modernization line as of today. Two "
            "things to flag before this goes to Board for any post-pilot commitment:\n\n"
            "1. The modernization line has $310k remaining after this encumbrance. If the "
            "pilot succeeds and we want to move to production SaaS plus the ArcGIS support "
            "scope Marcus mentioned, we'd be looking at ~$95k/yr ongoing. That is doable "
            "from this line but would foreclose the IT-helpdesk modernization Tom proposed "
            "in February.\n\n"
            "2. The Board's procurement policy requires a sole-source justification for "
            "any post-pilot contract over $50k. We should draft that justification in "
            "parallel with the pilot, not wait until the end.\n\n"
            "Happy to discuss.\n\n"
            "Sam\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w4-townhall",
        source="field_note",
        occurred_at=_dt(4, 4, 19),
        title="Rita observes town hall",
        source_ref="field://rita-townhall-2026-03-26",
        text=(
            "Field note — Rita Alvarez, community liaison, after Tuesday town hall\n\n"
            "Topic was unrelated (parks budget) but two residents brought up the permit "
            "modernization during open comment. Notable themes:\n\n"
            "Concern 1: Elderly residents (specifically named the senior center on Elm) "
            "do not have reliable internet access and are anxious about being forced into "
            "an online-only system. One resident said 'don't take Maria away from us.'\n\n"
            "Concern 2: A small contractor asked whether the new system would speed up his "
            "permits — he said his last permit took 9 weeks and cost him a job. He was the "
            "first person I've heard publicly say the current system is broken; usually it's "
            "us complaining about it internally.\n\n"
            "Both points support keeping the paper path during the pilot. We need a clear "
            "communications plan before we ever talk about retiring paper. Suggested to Dana "
            "we should make a phone-intake fallback explicit in the post-pilot scope.\n\n"
            "Rita\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w5-risk-review",
        source="meeting_note",
        occurred_at=_dt(5, 1, 10),
        title="Risk review w/ counsel",
        source_ref="notion://meetings/risk-review-2026-03-30",
        text=(
            "Risk review meeting — Yuki Tanaka + Alex Chen + Jordan Park\n\n"
            "Yuki walked through the DeployAI data-residency commitment line by line.\n\n"
            "Items closed:\n"
            "- US-East-1 only: confirmed, documented in MSA addendum\n"
            "- Quarterly third-party attestation: SOC2 Type 2 report acceptable\n"
            "- Contractual exit path: 90-day data return window, deletion certified by "
            "DeployAI's CISO\n\n"
            "Items still open:\n"
            "- Subprocessor list: DeployAI uses AWS, Anthropic, and a logging vendor. "
            "Yuki needs the logging vendor named before she'll sign the production MSA. "
            "Alex to follow up.\n"
            "- AI-assisted features: DeployAI's roadmap includes AI-assisted permit "
            "review. Yuki flagged this as a separate review requirement before any "
            "AI feature touches county data. Out of scope for pilot but needs to be "
            "tracked.\n\n"
            "Yuki: 'I'm comfortable with the pilot. The AI question we'll need to "
            "revisit before we go to production.'\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w5-scope-lock",
        source="email",
        occurred_at=_dt(5, 2, 15),
        title="90-day pilot scope locked",
        source_ref="email-19",
        text=(
            "From: Dana Carter\n"
            "To: Alex Chen\n"
            "Cc: Priya Raman, Marcus Okafor\n"
            "Subject: 90-day pilot scope — final\n\n"
            "Alex,\n\n"
            "Confirming the final pilot scope so we have it in writing:\n\n"
            "In scope:\n"
            "- Web intake for residential and commercial permits (all current permit types)\n"
            "- Reviewer queue UI for our 6 reviewers\n"
            "- ArcGIS parcel lookup integration (read-only)\n"
            "- Dashboard for Priya showing median intake-to-decision time\n\n"
            "Out of scope (post-pilot only):\n"
            "- Mobile app for residents\n"
            "- Spanish-language intake form (Rita raised — will pilot in v2)\n"
            "- Code enforcement workflow (separate program area)\n"
            "- Any AI-assisted review feature (per Yuki's requirement)\n\n"
            "Success criteria reaffirmed per Priya's memo of 2026-03-20.\n\n"
            "Looking forward to Monday's first reviewer-training session.\n\n"
            "Dana\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w5-integration-plan",
        source="email",
        occurred_at=_dt(5, 4, 14),
        title="Jordan on ArcGIS integration",
        source_ref="email-22",
        text=(
            "From: Jordan Park\n"
            "To: Marcus Okafor\n"
            "Cc: Tom Reyes\n"
            "Subject: ArcGIS integration — plan + open questions\n\n"
            "Marcus + Tom,\n\n"
            "Here's the integration plan for parcel lookups against your ArcGIS Enterprise "
            "instance. Targeting end of week 6 for first live lookup.\n\n"
            "Plan:\n"
            "1. Tom opens a read-only service account against the parcels feature service "
            "(this week)\n"
            "2. I write a thin adapter in our intake service that queries on APN + address\n"
            "3. We cache successful lookups for 24h to keep load off your ArcGIS box\n"
            "4. Reviewers see GIS-confirmed parcel data alongside the application\n\n"
            "Open questions:\n"
            "- What's the SLA on the on-prem ArcGIS box? If it's down for a day, do we "
            "block intake or let applications submit without parcel validation?\n"
            "- Are there parcels in the system that haven't been geocoded? If yes, what's "
            "the fallback?\n\n"
            "These don't block the integration but I need a call on them before reviewer "
            "training.\n\n"
            "Jordan\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w6-checkpoint",
        source="meeting_note",
        occurred_at=_dt(6, 1, 14),
        title="Mid-pilot checkpoint (week 6)",
        source_ref="notion://meetings/mid-pilot-2026-04-13",
        text=(
            "Mid-pilot checkpoint — Acme County × DeployAI\n"
            "Attendees: Dana, Priya, Marcus, Alex, Jordan, Maria\n\n"
            "Metrics through week 6:\n"
            "- 142 applications received through new intake (vs ~510 paper in same window)\n"
            "- Median intake-to-decision time, new path: 11 business days (target: ≤15) ✓\n"
            "- Median intake-to-decision time, paper path: 28 business days (baseline 30)\n"
            "- Zero PII incidents; SOC2 controls audit clean (DeployAI internal)\n\n"
            "Maria's report: the system is faster than paper for routine permits but slower "
            "for complex ones because the reviewer queue UI doesn't surface the conditional "
            "fields well. Jordan logged this as a P2 for week 7.\n\n"
            "Joel (the second clerk) has not yet used the new system — has been on PTO. "
            "Will pair with Jordan week 7.\n\n"
            "Priya's read: we are tracking toward criterion 1 (time) and criterion 2 (PII). "
            "Criterion 3 (clerk-reported satisfaction) is in progress. Currently on track to "
            "meet two of three.\n\n"
            "Dana: the IT-support post-pilot question (re: Sam Lindgren's budget memo and "
            "Tom's capacity concerns) needs a decision by week 9. Action: Marcus to draft a "
            "1-year support proposal for DeployAI to price.\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w6-jordan-onsite",
        source="field_note",
        occurred_at=_dt(6, 3, 14),
        title="Jordan onsite — intake clerk pain points",
        source_ref="field://jordan-2026-04-15",
        text=(
            "Field note — Jordan Park, sitting with Maria for the afternoon\n\n"
            "Maria walked me through a complex commercial permit application (a coffee shop "
            "with proposed outdoor seating in a B-2 zone). Things our UI gets wrong:\n\n"
            "1. The conditional 'is alcohol service planned' field appears 4 questions too "
            "late — Maria has to scroll back twice to answer correctly. She fixes this by "
            "muscle memory now but a new clerk would not.\n\n"
            "2. The reviewer queue groups by 'received date' but Maria thinks in 'urgency.' "
            "She wants a flag for 'business waiting on this to open.'\n\n"
            "3. When parcel lookup fails (ArcGIS returns empty for newly subdivided lots) "
            "the application sits in a limbo state — there's no clear next action. Today "
            "Maria handles this by calling the contractor; the system should at least show "
            "a 'manual parcel verification needed' status.\n\n"
            "These are all addressable. Logging as week-7 fast-follows.\n\n"
            "Also — I asked Maria if the new system was faster for her than paper. She "
            "said 'for the simple ones, yes. For the messy ones, you're saving the "
            "applicant time but not really mine. Yet.' Honest signal on criterion 3.\n\n"
            "Jordan\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w6-rita-community-feedback",
        source="email",
        occurred_at=_dt(6, 5, 10),
        title="Rita — community feedback summary",
        source_ref="email-31",
        text=(
            "From: Rita Alvarez\n"
            "To: Dana Carter\n"
            "Subject: Mid-pilot community feedback\n\n"
            "Dana,\n\n"
            "Six weeks in, the community signal is more positive than I expected. Three "
            "themes from the listening sessions and 1:1s:\n\n"
            "1. People who have used the new intake say it's a huge improvement. The "
            "contractor I mentioned at the town hall got his most recent permit in 9 days "
            "(vs 9 weeks before). He told me on his own initiative. That's a story we "
            "should be ready to tell.\n\n"
            "2. The senior center concern has not gone away. The fact that paper is still "
            "an option is reassuring people, but I am hearing variants of 'what happens "
            "after the pilot.' We need a publicly documented commitment that paper or "
            "phone intake stays available indefinitely.\n\n"
            "3. Spanish-speaking residents are still being routed to the one bilingual "
            "clerk and getting stuck when she's not in. The Spanish form is out of scope "
            "for the pilot per Alex's note, but this is a real equity issue that I want to "
            "make sure we address in v2.\n\n"
            "Recommend: post-pilot scope includes (a) explicit phone fallback commitment "
            "and (b) Spanish intake form as P0.\n\n"
            "Rita\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w7-extension-commit",
        source="manual_import",
        occurred_at=_dt(7, 2, 11),
        title="Priya commits to extension contingency",
        source_ref="memo://priya-extension-2026-04-21",
        text=(
            "Decision memo — Pilot extension contingency\n"
            "Author: Priya Raman, Deputy Director\n"
            "Date: 2026-04-21\n\n"
            "Per the mid-pilot checkpoint, the DeployAI pilot is currently tracking toward "
            "two of three success criteria (time-to-decision and PII-residency). Criterion "
            "3 (clerk satisfaction) is partially demonstrated but not yet confirmable until "
            "Joel returns from PTO and uses the system.\n\n"
            "Commitment: if the pilot ends meeting all three success criteria, the County "
            "will extend the engagement for a further 6 months at the previously scoped "
            "SaaS rate ($42k/yr) plus a separately scoped support arrangement (subject to "
            "Sam Lindgren's budget memo and Board sole-source justification).\n\n"
            "Public-facing commitment: regardless of pilot outcome, the County will keep "
            "paper and phone intake permanently available. Rita Alvarez to draft the public "
            "language for the next Board meeting.\n\n"
            "/s/ Priya Raman\n"
        ),
    ),
    SeedEvent(
        dedup_key="seed-w7-adjacent-opp",
        source="email",
        occurred_at=_dt(7, 4, 16),
        title="Adjacent opportunity — zoning module",
        source_ref="email-38",
        text=(
            "From: Alex Chen\n"
            "To: Sam Lee\n"
            "Subject: Acme County — adjacent opportunity (zoning)\n\n"
            "Sam,\n\n"
            "Coffee with Marcus today. He surfaced something worth tracking: the county "
            "has a parallel pain point in zoning variance applications, which currently "
            "live in an entirely separate Access database maintained by one person in "
            "Planning. Same shape as the permit-modernization problem we're solving now, "
            "but a different department.\n\n"
            "Marcus said he'd be supportive of bringing DeployAI back for a zoning module "
            "scoping if our permit pilot lands the three criteria. Budget would come from "
            "FY27 (so we're not competing with the post-pilot SaaS spend), and the "
            "decision-maker is Planning Director (not Priya — different chain of command).\n\n"
            "Logging this so we don't lose it. Suggest we wait until week 11 of the pilot "
            "to surface it formally — too early now would muddy the success-criteria "
            "conversation Priya is focused on.\n\n"
            "Alex\n"
        ),
    ),
]


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _psql(sql: str) -> None:
    """Pipe a SQL block into the postgres container via docker compose exec."""
    cmd = [
        "docker",
        "compose",
        "--env-file",
        str(ENV_FILE),
        "-f",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        "postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        POSTGRES_USER,
        "-d",
        POSTGRES_DB,
    ]
    r = subprocess.run(cmd, input=sql, text=True, capture_output=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout)
        sys.stderr.write(r.stderr)
        raise SystemExit(f"psql failed (rc={r.returncode})")


def _http(method: str, path: str, body: dict | None = None) -> dict | list | None:
    url = f"{CP_BASE_URL}{path}"
    data = None
    headers = {"X-DeployAI-Internal-Key": INTERNAL_KEY}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {e.code} {method} {url}\n{msg}") from e


def _wait_for_cp(deadline_s: float = 60.0) -> None:
    """Poll CP /health until ready (stack just came up)."""
    start = time.time()
    while time.time() - start < deadline_s:
        try:
            with urllib.request.urlopen(f"{CP_BASE_URL}/health", timeout=3) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError):
            pass
        time.sleep(2)
    raise SystemExit(f"control-plane did not become healthy at {CP_BASE_URL}/health within {deadline_s}s")


# ----------------------------------------------------------------------------
# Steps
# ----------------------------------------------------------------------------


def seed_tenant_and_users() -> None:
    """Insert the tenant + 3 deployment-team users (idempotent)."""
    sql = f"""
BEGIN;

INSERT INTO app_tenants (id, name)
VALUES ('{TENANT_ID}'::uuid, '{TENANT_NAME}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO app_users (id, tenant_id, user_name, email, given_name, family_name, active)
VALUES
  ('{USER_STRATEGIST_ID}'::uuid, '{TENANT_ID}'::uuid,
   'alex.chen', 'alex.chen@deployai.com', 'Alex', 'Chen', true),
  ('{USER_FDE_ID}'::uuid, '{TENANT_ID}'::uuid,
   'jordan.park', 'jordan.park@deployai.com', 'Jordan', 'Park', true),
  ('{USER_BIZDEV_ID}'::uuid, '{TENANT_ID}'::uuid,
   'sam.lee', 'sam.lee@deployai.com', 'Sam', 'Lee', true)
ON CONFLICT (id) DO NOTHING;

COMMIT;

SELECT 'app_tenants' AS table_name, count(*) FROM app_tenants WHERE id = '{TENANT_ID}'::uuid
UNION ALL
SELECT 'app_users (this tenant)', count(*) FROM app_users WHERE tenant_id = '{TENANT_ID}'::uuid;
"""
    print("seed: app_tenants + app_users (psql)…")
    _psql(sql)


def seed_engagement() -> None:
    """Create the engagement at a stable UUID. Idempotent by direct SQL upsert
    (CP create endpoint does not support a caller-supplied id)."""
    sql = f"""
BEGIN;
INSERT INTO engagements (id, tenant_id, name, customer_account, current_phase, status, created_at, updated_at)
VALUES (
  '{ENGAGEMENT_ID}'::uuid, '{TENANT_ID}'::uuid,
  '{ENGAGEMENT_NAME.replace("'", "''")}',
  '{CUSTOMER_ACCOUNT.replace("'", "''")}',
  '{CURRENT_PHASE}', 'active', now(), now()
)
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  customer_account = EXCLUDED.customer_account,
  current_phase = EXCLUDED.current_phase,
  status = EXCLUDED.status,
  updated_at = now();
COMMIT;
"""
    print("seed: engagement (psql upsert)…")
    _psql(sql)


def seed_members() -> None:
    """Add the three deployment-team members via CP API. 409 on rerun = already member, fine."""
    print("seed: engagement_members (CP API)…")
    members = [
        (USER_STRATEGIST_ID, "deployment_strategist"),
        (USER_FDE_ID, "fde"),
        (USER_BIZDEV_ID, "biz_dev"),
    ]
    for user_id, role in members:
        try:
            _http(
                "POST",
                f"/internal/v1/engagements/{ENGAGEMENT_ID}/members?tenant_id={TENANT_ID}",
                {"user_id": user_id, "role": role},
            )
            print(f"  added {role} ({user_id[:8]}…)")
        except SystemExit as e:
            # 409 already member is expected on rerun; surface anything else
            msg = str(e)
            if "409" in msg and "already a member" in msg:
                print(f"  member exists ({role})")
            else:
                raise


def ingest_and_extract(force_extract: bool) -> None:
    """Ingest each event (idempotent via dedup_key), then call /extract on it."""
    print(f"seed: ingesting + extracting {len(SEED_EVENTS)} events…")
    for i, e in enumerate(SEED_EVENTS, start=1):
        body = {
            "source": e.source,
            "occurred_at": e.occurred_at.isoformat(),
            "content": {"text": e.text},
            "source_ref": e.source_ref,
            "dedup_key": e.dedup_key,
        }
        ev = _http(
            "POST",
            f"/internal/v1/engagements/{ENGAGEMENT_ID}/ingest?tenant_id={TENANT_ID}",
            body,
        )
        assert isinstance(ev, dict)
        event_id = ev["id"]
        force_q = "&force=true" if force_extract else ""
        proposals = _http(
            "POST",
            f"/internal/v1/engagements/{ENGAGEMENT_ID}/extract?tenant_id={TENANT_ID}"
            f"&event_id={event_id}{force_q}",
        )
        n = len(proposals) if isinstance(proposals, list) else 0
        print(f"  [{i:>2}/{len(SEED_EVENTS)}] {e.source:<14} {e.title[:50]:<50} -> {n} proposals")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force-extract",
        action="store_true",
        help="Discard pending proposals and re-run the LLM for each event (costs $).",
    )
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="Ingest events only — do not call the extraction agent.",
    )
    args = parser.parse_args()

    print(f"seed: target tenant={TENANT_ID} engagement={ENGAGEMENT_ID}")
    print(f"seed: CP base url = {CP_BASE_URL}")
    _wait_for_cp()
    seed_tenant_and_users()
    seed_engagement()
    seed_members()
    if args.skip_extract:
        print("seed: --skip-extract, ingesting without extraction…")
        for i, e in enumerate(SEED_EVENTS, start=1):
            body = {
                "source": e.source,
                "occurred_at": e.occurred_at.isoformat(),
                "content": {"text": e.text},
                "source_ref": e.source_ref,
                "dedup_key": e.dedup_key,
            }
            _http(
                "POST",
                f"/internal/v1/engagements/{ENGAGEMENT_ID}/ingest?tenant_id={TENANT_ID}",
                body,
            )
            print(f"  [{i:>2}/{len(SEED_EVENTS)}] ingested {e.title[:60]}")
    else:
        ingest_and_extract(force_extract=args.force_extract)

    print()
    print("seed: done.")
    print(f"  Open: {WEB_BASE_URL}/engagements/{ENGAGEMENT_ID}")


if __name__ == "__main__":
    main()
