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
