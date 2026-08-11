/**
 * Wave 2.5 U1 — shared human labels for ledger/event kinds and people.
 *
 * Every surface that shows a `source_kind` (timeline rows, activity cards,
 * delta digest, drawers) goes through these helpers so raw enum values never
 * reach the screen. Unknown kinds degrade to a de-snake-cased sentence-case
 * label rather than the raw enum.
 */

/** Buckets mirror the backend summary grouping for recent changes. */
export type SourceKindBucket =
  | "decision"
  | "risk"
  | "stakeholder"
  | "commitment"
  | "proposal"
  | "agent"
  | "system"
  | "other";

const SOURCE_KIND_LABEL: Record<string, string> = {
  email_ingest: "Email imported",
  meeting_webhook: "Meeting captured",
  manual_capture: "Manual note",
  llm_proposal_created: "Extraction proposed",
  proposal_accepted: "Proposal accepted",
  proposal_rejected: "Proposal rejected",
  matrix_node_created: "Matrix entry added",
  matrix_node_updated: "Matrix entry updated",
  matrix_node_deleted: "Matrix entry removed",
  matrix_edge_created: "Relationship added",
  matrix_edge_deleted: "Relationship removed",
  insight_opened: "Insight opened",
  insight_closed: "Insight closed",
  insight_snoozed: "Insight snoozed",
  followup_task_created: "Follow-up created",
  recommendation_emitted: "Recommendation issued",
  recommendation_actioned: "Recommendation actioned",
  engagement_phase_change: "Phase changed",
  member_added: "Member added",
  member_removed: "Member removed",
  settings_change: "Settings changed",
  audit_other: "Audit entry",
  audit_decision: "Audit decision",
  user_provisioned: "User provisioned",
  oracle_chat_turn: "Agent answer",
  human_escalation_answer: "Human answer recorded",
  agent_approval_requested: "Approval requested",
  agent_approval_granted: "Approval granted",
  agent_approval_denied: "Approval denied",
  mcp_outbound_call: "External call",
  mcp_outbound_blocked: "External call blocked",
  mcp_outbound_rate_limited: "External call rate-limited",
  mcp_outbound_denied: "External call denied",
  mcp_outbound_killswitch_changed: "Kill switch changed",
  mcp_config_created: "Connector added",
  mcp_config_updated: "Connector updated",
  mcp_config_deleted: "Connector removed",
  mcp_oauth_token_rotated: "Connector token rotated",
  // Insight / delta kinds that arrive via summary recent_changes.
  risk_opened: "Risk opened",
  risk_closed: "Risk closed",
  decision_accepted: "Decision accepted",
  decision_recorded: "Decision recorded",
  stakeholder_added: "Stakeholder added",
  commitment_recorded: "Commitment recorded",
  commitment_overdue: "Commitment overdue",
};

/** De-snake a kind into sentence case: "risk_closed" → "Risk closed". */
export function deSnakeKind(kind: string): string {
  const spaced = kind.replace(/[_-]+/g, " ").trim();
  if (spaced.length === 0) return spaced;
  return spaced.charAt(0).toUpperCase() + spaced.slice(1).toLowerCase();
}

/** Short human label for a source kind ("Risk closed", "Agent answer", …). */
export function humanSourceKindLabel(kind: string): string {
  const k = kind.trim();
  if (k.length === 0) return "Event";
  return SOURCE_KIND_LABEL[k] ?? deSnakeKind(k);
}

const BUCKET_RULES: ReadonlyArray<[RegExp, SourceKindBucket]> = [
  [/decision/, "decision"],
  [/risk/, "risk"],
  [/stakeholder|member|user/, "stakeholder"],
  [/commitment|followup|follow_up/, "commitment"],
  [/proposal/, "proposal"],
  [/oracle|agent|escalation|approval/, "agent"],
  [/mcp|settings|audit|phase|config|killswitch|kill_switch|webhook_delivery/, "system"],
];

/** Bucket a source kind the way the backend summary endpoint groups it. */
export function sourceKindBucket(kind: string): SourceKindBucket {
  const k = kind.trim().toLowerCase();
  for (const [re, bucket] of BUCKET_RULES) {
    if (re.test(k)) return bucket;
  }
  return "other";
}

export const BUCKET_LABEL: Record<SourceKindBucket, string> = {
  decision: "Decisions",
  risk: "Risks",
  stakeholder: "People",
  commitment: "Commitments",
  proposal: "Proposals",
  agent: "Agent activity",
  system: "System",
  other: "Other",
};

/**
 * Icon name per source kind. Names are abstract (not tied to a React icon
 * library) so this module stays render-free; components map them to lucide
 * icons locally.
 */
export type SourceKindIconName =
  | "mail"
  | "calendar"
  | "clipboard"
  | "sparkles"
  | "graph"
  | "lightbulb"
  | "shield"
  | "person"
  | "chat"
  | "cable"
  | "document";

const SOURCE_KIND_ICON: Record<string, SourceKindIconName> = {
  email_ingest: "mail",
  meeting_webhook: "calendar",
  manual_capture: "clipboard",
  llm_proposal_created: "sparkles",
  proposal_accepted: "sparkles",
  proposal_rejected: "sparkles",
  matrix_node_created: "graph",
  matrix_node_updated: "graph",
  matrix_node_deleted: "graph",
  matrix_edge_created: "graph",
  matrix_edge_deleted: "graph",
  insight_opened: "lightbulb",
  insight_closed: "lightbulb",
  insight_snoozed: "lightbulb",
  followup_task_created: "clipboard",
  recommendation_emitted: "lightbulb",
  recommendation_actioned: "lightbulb",
  engagement_phase_change: "shield",
  member_added: "person",
  member_removed: "person",
  settings_change: "shield",
  audit_other: "shield",
  audit_decision: "shield",
  user_provisioned: "person",
  oracle_chat_turn: "chat",
  human_escalation_answer: "chat",
  agent_approval_requested: "shield",
  agent_approval_granted: "shield",
  agent_approval_denied: "shield",
  mcp_outbound_call: "cable",
  mcp_outbound_blocked: "cable",
  mcp_outbound_rate_limited: "cable",
  mcp_outbound_denied: "cable",
  mcp_outbound_killswitch_changed: "cable",
  mcp_config_created: "cable",
  mcp_config_updated: "cable",
  mcp_config_deleted: "cable",
  mcp_oauth_token_rotated: "cable",
};

export function sourceKindIconName(kind: string): SourceKindIconName {
  return SOURCE_KIND_ICON[kind.trim()] ?? "document";
}

/**
 * U1 defect fix — strip a redundant kind prefix from a title/summary.
 *
 * Backends sometimes emit summaries that already start with the kind label
 * ("Risk closed: stakeholder spec-gap"); rendering the kind chip next to the
 * raw summary produced "risk closed: Risk closed: stakeholder spec-gap".
 * If the title starts with the kind's human label or its de-snaked form
 * (case-insensitive, followed by ":", "—", or "-"), the prefix is dropped.
 */
export function stripRedundantKindPrefix(title: string, kind: string): string {
  const t = title.trim();
  if (t.length === 0) return t;
  const candidates = [humanSourceKindLabel(kind), deSnakeKind(kind), kind.trim()]
    .filter((c) => c.length > 0)
    .map((c) => c.toLowerCase());
  const lower = t.toLowerCase();
  for (const prefix of candidates) {
    if (!lower.startsWith(prefix)) continue;
    const rest = t.slice(prefix.length).replace(/^\s*[:—–-]\s*/, "");
    if (rest.trim().length > 0) return rest.trim();
    // Title was exactly the kind label — keep the human label.
    return humanSourceKindLabel(kind);
  }
  return t;
}

// ---------------------------------------------------------------------------
// U2 — people are people. Display-name / initials helpers shared by every
// surface that renders a member or actor.
// ---------------------------------------------------------------------------

export type PersonLike = {
  display_name?: string | null;
  email?: string | null;
  user_id?: string | null;
};

/** Shorten an opaque id for display: first 8 chars + ellipsis. */
export function shortId(id: string): string {
  const trimmed = id.trim();
  return trimmed.length > 8 ? `${trimmed.slice(0, 8)}…` : trimmed;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Actor ids are sometimes opaque UUIDs and sometimes readable handles
 * ("agent-kenny", "on-call-sre"). Shorten only the opaque ones.
 */
export function formatActorId(id: string): string {
  const trimmed = id.trim();
  return UUID_RE.test(trimmed) ? shortId(trimmed) : trimmed;
}

/**
 * Best human name for a person: display_name, then email, then a shortened
 * id — never a raw UUID.
 */
export function displayNameForPerson(person: PersonLike): string {
  const name = person.display_name?.trim();
  if (name) return name;
  const email = person.email?.trim();
  if (email) return email;
  const id = person.user_id?.trim();
  if (id) return shortId(id);
  return "Unknown";
}

/** Avatar initials from a display name ("Ada Lovelace" → "AL"). */
export function initialsFor(name: string): string {
  const parts = name
    .trim()
    .split(/[\s@._-]+/)
    .filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]!.charAt(0) + parts[parts.length - 1]!.charAt(0)).toUpperCase();
}
