/** 7-phase DeployAI framework × 3 stakeholder topologies = 21 cells (NFR53, Story 4-3/4-4). */

export const PHASES = [
  "discovery",
  "planning",
  "integration",
  "pilot",
  "scale",
  "steady_state",
  "sunset",
];

export const TOPOLOGIES = [
  "single_stakeholder",
  "cross_agency",
  "multi_jurisdictional",
];

export function cellKey(phase, topology) {
  return `${phase}::${topology}`;
}
