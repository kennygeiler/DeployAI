/**
 * Mermaid diagram sources for tooling, Obsidian, or https://mermaid.live
 * Copy-paste `bmadAndRuntimeFlow` into any Mermaid renderer.
 */

/** BMAD skills in `.cursor/skills/` and how they feed implementation. */
export const bmadAgentFlow = String.raw`
flowchart TB
  subgraph entry["Entry"]
    U[Operator / engineer in Cursor]
    H[["bmad-help\n(SKILL)"]]
    U --> H
  end

  subgraph discovery["Discovery & specs"]
    PM[["bmad-agent-pm\nPRD / John"]]
    AN[["bmad-agent-analyst\nMary"]]
    AR[["bmad-agent-architect\nWinston"]]
    UX[["bmad-agent-ux-designer\nSally"]]
    TW[["bmad-agent-tech-writer\nPaige"]]
    H --> PM
    H --> AN
    H --> AR
    H --> UX
    H --> TW
  end

  subgraph planning["Planning artifacts"]
    PRD["_bmad-output/planning-artifacts/prd.md"]
    EP["_bmad-output/planning-artifacts/epics.md"]
    ARCH["_bmad-output/planning-artifacts/architecture.md"]
    PM --> PRD
    AN --> PRD
    AR --> ARCH
    UX --> EP
  end

  subgraph execution["Build & ship"]
    CS[["bmad-create-story\nstory file"]]
    DS[["bmad-dev-story\nAmelia"]]
    CR[["bmad-code-review"]]
    PRD --> CS
    EP --> CS
    CS --> DS
    DS --> CR
    CR --> MAIN[["main + CI gates"]]
  end

  subgraph optional["Optional orchestration"]
    PARTY[["bmad-party-mode\nmulti-agent"]]
    H -.-> PARTY
  end
`;

/** Strategist product path aligned with Epic 8–9 surfaces in `apps/web`. */
export const strategistRuntimeFlow = String.raw`
flowchart LR
  subgraph client["apps/web"]
    S[["StrategistShell\nactivity + demo URL merge"]]
    P[["/digest · /phase-tracking\n/evening · /in-meeting"]]
    Q[["/action-queue\n/validation-queue\n/solidification-review"]]
    S --> P
    S --> Q
  end

  subgraph bff["BFF mocks → CP later"]
    A[["GET/POST\n/api/bff/*"]]
    P --> A
    Q --> A
  end

  subgraph cp["services/control-plane"]
    HZ[["/healthz"]]
    ING[["/internal/v1/ingestion-runs"]]
    MP[["/internal/v1/strategist/meeting-presence\n(Epic 9.1 stub)"]]
  end

  subgraph future["Hardening"]
    OR[["Oracle / canonical memory\n(full ACs)"]]
  end

  S -->|"poll"| ACT[["/api/internal/strategist-activity"]]
  ACT --> HZ
  ACT --> ING
  ACT --> MP
  A -.-> OR
`;

/** Single canvas: BMAD loop + runtime (readme uses a subset or this full graph). */
export const bmadAndRuntimeFlow = String.raw`
flowchart TB
  subgraph bmad["BMAD in Cursor"]
    direction TB
    U[You] --> HELP[["bmad-help"]]
    HELP --> ROLES["PM · Analyst · Architect\nUX · Tech-writer skills"]
    ROLES --> ART["_bmad-output/\nprd · epics · architecture"]
    ART --> STORY[["bmad-create-story"]]
    STORY --> DEV[["bmad-dev-story / quick-dev"]]
    DEV --> REV[["bmad-code-review"]]
    REV --> MAIN[CI + merge to main]
  end

  subgraph rt["Strategist runtime Epics 8–9"]
    direction TB
    WEB["Next.js strategist routes"] --> SH[StrategistShell]
    SH --> SURF["Digest / phases / evening\n/in-meeting alert"]
    SH --> QUEUES["Action + validation +\nsolidification queues"]
    SH --> POLL["strategist-activity BFF"]
    POLL --> CP["control-plane\nhealthz · ingestion-runs\nmeeting-presence"]
    QUEUES --> BFF["/api/bff/*\nin-memory store"]
  end

  bmad -->|"ships code into"| rt
`;
