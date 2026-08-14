# Demo runbook — the 8-minute cold-start

The presenter's script for showing DeployAI to a startup that runs FDEs/deployment
strategists. Rehearse it out loud twice before any real audience. The guided tour
covers the same beats for self-serve visitors; this runbook is for when *you* drive.

**Link**: https://web-production-e4059.up.railway.app → **View live demo**
(read-only guest on the demo workspace; sessions last ~1 hour; the guided tour
auto-starts — hit **Skip** when you're presenting live).

**Tour navigation (tour-ux)**: in the guided tour, **Next always advances** —
when the next beat lives on another page or Brief tab, Next itself navigates
there (and capture beats auto-open the Capture tab and scroll it into view).
Performing the highlighted action still advances too; it's an alternative,
never a requirement. If a visitor says they're "stuck", Next is always the
answer.

**Sandbox-per-visitor**: every View-live-demo click mints its own cold-start
"Acme Robotics — Pilot Deployment" engagement (a private sandbox — visitors
never see each other's, and each one's slip act starts empty). Guests see
exactly ONE Acme row — their own sandbox; the presenter's stable Acme
(`acacacac-…`) is hidden from demo sessions so the portfolio never shows two
identical rows. Agent Kenny chat history is also private per guest session:
each View-live-demo click gets its own conversation thread on every
engagement (including the seeded BlueState fixture), and stale guest threads
are cleaned up automatically after 24h alongside the sandboxes. **No manual
reset is needed for the public link**; sandboxes older than 24h are cleaned
up automatically on later visits. `make demo-reset` still exists, but only
for the *presenter* flow below — it recycles the stable Acme engagement
(`acacacac-…`) and never touches live visitor sandboxes. If a guest session
expires mid-tour, clicking View live demo again simply starts a fresh
sandbox.

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

## The catch-the-slip act (3 turns, ~6 min)

One week of the Acme deal, played by the audience (or a volunteer): Monday
builds trust, midweek a commitment quietly moves, Friday the record answers
for it. The guided tour runs this act self-serve (steps `slip-week-intro` …
`slip-friday-answer`, after the graph-tab step); this section is the
presenter version. **Run `make demo-reset` first** — the act needs the
cold-start Acme engagement, and the reset guarantees the stable id
(`acacacac-…`). (Guest sessions via **View live demo** don't need this: the
tour targets each visitor's own freshly minted sandbox instead of the stable
engagement; the reset is for presenter-driven, non-guest sessions.)

### Turn 1 — Monday, the trust beat (~2 min)

1. Open **Acme Robotics — Pilot Deployment** → **Capture tab**.
2. Load `demo/artifacts/kickoff-transcript.txt` (tour button does this;
   presenters paste it) → source **Meeting note** → **Capture**.
3. Narrate the honest progress states: Saving → Extracting (**25–30s
   measured**) → **~20 proposals ready**.
   > "Forty-five minutes of kickoff just became proposed memory — decisions,
   > risks, commitments, owners. Proposed, not written: nothing enters the
   > record without a human."
4. Accept a few in **Needs you** on camera — including the commitment
   *"safety certification package submitted by October"* (it matters later) —
   then hit **Accept all pending** to let the rest of the batch in. Narrate:
   per-item review is the real workflow; the batch accept is demo speed AND
   what makes Friday's answer rich (partial accepts leave the record thin
   and the payoff hedged). The guided tour directs self-serve visitors to
   the same batch accept at this step and again before the Friday ask.
   Point at the **Kenny asks** cards: *"the record already knows what it's
   missing — it asks for the artifact, you don't guess."*

### Turn 2 — midweek, the slip (~2 min)

5. Capture `demo/artifacts/slip-email.txt` as **Email**. Before submitting,
   dare the room: *"Routine end-of-day ops roundup. Read it. Would anything
   stop you?"* (The date change is one clause, mid-paragraph, sentence four.)
6. Extraction (**8–11s measured**) surfaces the catch — a commitment
   proposal titled *"Safety certification package by October 17 (was
   October 3)"* right next to the original commitment it contradicts.
   Accept it.
   > "One buried sentence just moved a committed date by two weeks. The
   > record caught it on a Wednesday afternoon. Would you have?"
7. Second beat: download/open `demo/artifacts/acme-standup.vtt` and **drag
   the file into the Capture box** (the drop is the demo moment — raw
   meeting exhaust, straight in). Self-serve tour visitors get a one-click
   **"Attach the standup notes"** button instead — same parser, same clean
   text — with the download link kept as the secondary path for anyone who
   wants the raw file. Extraction (**7–10s measured**) proposes
   the risk *"e-stop faults blocking safety certification test logs"* —
   a blocker aimed at the very milestone that just slipped. Accept.
8. **Accept all pending** once more so Thursday's standup findings are on
   the record (the tour directs this too), then scroll to **Since you last
   looked**: the week replayed — new memory, a slipped date, a new blocker,
   each entry traceable to an artifact.

### Turn 3 — Friday, the payoff (~2 min)

9. Ask bar: *"Are we on track for the safety certification?"* Let the tool
   chips and stream play (**42–55s measured** — narrate the trace, don't
   fill silence with apology).
10. The answer weaves all three sources with verified citation chips
    (5–14 chips across measured runs): original October commitment
    (kickoff) → moved October 3 → 17 (the buried email sentence) → blocked
    by e-stop firmware faults (the standup file). Click a chip.
    > "That answer exists because *you* fed the record this week. Cited,
    > grounded, and it will say 'I can't confirm' rather than guess."
11. Optional coda: the refusal trap from Act 2 (*Active Directory
    migration*) — same bar, opposite behavior — if the room needs the
    trust proof.

### Which beats are model-dependent (measured 2026-08-13, 3 full runs)

- **Stable across all runs**: kickoff → ~20 proposals; slip email → a
  commitment proposal carrying "October 17 (was October 3)" in the title
  (3/3); standup → a risk proposal tying e-stop faults to the safety
  certification test logs (3/3); final answer citing all three sources with
  both dates (3/3, 42–53s).
- **Varies between runs**: exact proposal counts on the slip email (3–5)
  and standup (2–4); citation-chip counts (5–14); occasional extra edges.
  Near-duplicate commitments (the October original beside the October 17
  revision) are **by design** — the record is append-only; say so.
- **Known failure mode**: the Friday ask has a 60s hard turn budget; a
  wandering run can end with "turn_timeout" (~1 in 6 pre-tuning runs, none
  after). Recovery: ask again — the retry re-runs retrieval and has always
  completed in our runs.

## Recovery moves

| Symptom | Move |
|---|---|
| Turn slow / times out | "Live model call — let's look at the Review inbox while it thinks"; the turn keeps streaming |
| 429 budget message | Daily cap hit — switch to narrating the citation panel + provenance on existing answers |
| Session expired mid-demo | Click View live demo again (one click, ~5 seconds) |
| Extraction slow in Act 1 | Keep talking over the progress state; >30s, move to Act 2 and return |
| Slip-act extraction slow | The kickoff is the long pole (~30s) — narrate the human gate while it runs; the email/vtt beats are <12s |
| Friday ask hits turn_timeout | Ask the same question again — retries completed every time in rehearsal; meanwhile show the accepted Oct 17 proposal as the manual proof |
| Slip proposal wording drifts | The date is always in the proposal (title or rationale, 3/3 runs titled) — read it aloud from whichever field carries it |
| Anything hard-fails | The `/overview` walkthrough carries the pitch with screenshots — no live deps |

## The one-liner

> "DeployAI is deal memory that writes itself and proves every answer —
> extraction with a human gate, an agent that cites or declines, and an audit
> trail down to the source sentence."
