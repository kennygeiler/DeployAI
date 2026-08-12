# Demo runbook — the 8-minute cold-start

The presenter's script for showing DeployAI to a startup that runs FDEs/deployment
strategists. Rehearse it out loud twice before any real audience. The guided tour
covers the same beats for self-serve visitors; this runbook is for when *you* drive.

**Link**: https://web-production-e4059.up.railway.app → **View live demo**
(read-only guest on the demo workspace; sessions last ~1 hour; the guided tour
auto-starts — hit **Skip** when you're presenting live).

## Before the meeting (2 minutes)

- Fresh/incognito window, click View live demo, confirm the portfolio renders.
- If you'll run the cold-start act: `make demo-reset` locally against prod
  (see the target's help) so Acme Robotics is empty, and have `demo/artifacts/`
  open in a text editor to copy from.
- Budget note: the demo tenant has a daily LLM token budget. A handful of turns
  is fine; don't burn it rehearsing an hour before.

## Act 1 — Feed it (2 min)

1. Open **Acme Robotics — Pilot Deployment** (empty Brief, honest empty states).
2. **Capture tab** → paste `demo/artifacts/kickoff-transcript.txt` → submit.
   Narrate the progress state: *"it's reading the transcript and proposing memory."*
3. When proposals land, accept two, reject one on camera.
   > "Nothing enters the deal record until a human accepts it. The system
   > proposes; your strategist decides."
4. Paste `email-thread.txt`. Point at the commitment it finds buried mid-thread.

## Act 2 — Ask it (3 min) — on BlueState (the seeded 26-week deal)

5. Ask (or use the suggested question):
   *"Who is the executive sponsor and what did we decide about the identity provider?"*
   Let the tool chips and streaming answer play. Then **click a citation chip** and
   say nothing while the evidence opens.
6. **The trap** — type exactly:
   *"What concerns were raised about the Active Directory migration?"*
   (Verified refusal: not in this corpus. Do **not** use legal/DPA questions —
   the corpus contains real BAA/HIPAA content and will legitimately answer.)
   > "It doesn't bluff. When the evidence is missing, it says so and shows the
   > nearest real items. That's the entire trust model."

## Act 3 — The flywheel + close (3 min)

7. **Review inbox**: show the pending queue (extraction proposals from Act 1).
   If empty: *"an empty queue means everything has been human-reviewed."*
8. **Graph tab** on BlueState-XL (the 5-year deal): the lens view — search a
   stakeholder, expand a hop. *"866 nodes; you never see a hairball."*
9. Close on **Overview** in the nav: *"this page is the self-guided version —
   everything you just watched, explorable."* Repo close, if technical audience:
   `docs/engineering-highlights.md` — *"every claim in this demo has a CI gate."*

## Recovery moves

| Symptom | Move |
|---|---|
| Turn slow / times out | "Live model call — let's look at the Review inbox while it thinks"; the turn keeps streaming |
| 429 budget message | Daily cap hit — switch to narrating the citation panel + provenance on existing answers |
| Session expired mid-demo | Click View live demo again (one click, ~5 seconds) |
| Extraction slow in Act 1 | Keep talking over the progress state; >30s, move to Act 2 and return |
| Anything hard-fails | The `/overview` walkthrough carries the pitch with screenshots — no live deps |

## The one-liner

> "DeployAI is deal memory that writes itself and proves every answer —
> extraction with a human gate, an agent that cites or declines, and an audit
> trail down to the source sentence."
