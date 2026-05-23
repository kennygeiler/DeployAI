/**
 * Shared DTO shapes for the deployment matrix (BFF ↔ control-plane).
 * Mirror the control-plane `MatrixNodeRead` / `MatrixEdgeRead` models.
 * See `docs/product/deployment-matrix-model.md`.
 */

export type MatrixNode = {
  id: string;
  engagement_id: string;
  node_type: string;
  title: string;
  identity_node_id: string | null;
  attributes: Record<string, unknown>;
  status: string | null;
  evidence_event_ids: string[];
  created_at: string;
  updated_at: string;
};

export type MatrixEdge = {
  id: string;
  engagement_id: string;
  edge_type: string;
  from_node_id: string;
  to_node_id: string;
  attributes: Record<string, unknown>;
  evidence_event_ids: string[];
  created_at: string;
  updated_at: string;
};

/**
 * The human-review buffer between extraction (6.2b) and the committed
 * matrix. `payload` is shaped per `proposal_kind` (a node or edge ready to
 * insert); `source_event_id` cites the canonical event it was derived from.
 */
export type MatrixProposal = {
  id: string;
  engagement_id: string;
  source_event_id: string;
  proposal_kind: string;
  payload: Record<string, unknown>;
  rationale: string | null;
  status: string;
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
  result_node_id: string | null;
  result_edge_id: string | null;
};
