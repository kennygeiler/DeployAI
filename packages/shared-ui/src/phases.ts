import type { LucideIcon } from "lucide-react";
import { CircleDashed, Rocket, Scale, Search, Spline, Target, Waypoints } from "lucide-react";

/**
 * Canon from Epic 5 Story 5.4 / `epics.md` — seven deployment phases for DeployAI.
 * IDs align with `services/control-plane` state machine when present; UI uses labels only.
 */
export const DEPLOYMENT_PHASE_IDS = [
  "P1_pre_engagement",
  "P2_discovery",
  "P3_ecosystem_mapping",
  "P4_design",
  "P5_pilot",
  "P6_scale",
  "P7_inheritance",
] as const;

export type DeploymentPhaseId = (typeof DEPLOYMENT_PHASE_IDS)[number];

export type DeploymentPhaseDefinition = {
  id: DeploymentPhaseId;
  shortLabel: string;
  label: string;
  /** Decorative icon (not a state indicator; color comes from text + borders). */
  icon: LucideIcon;
};

export const DEPLOYMENT_PHASES: readonly DeploymentPhaseDefinition[] = [
  { id: "P1_pre_engagement", shortLabel: "P1", label: "Pre-engagement", icon: CircleDashed },
  { id: "P2_discovery", shortLabel: "P2", label: "Discovery", icon: Search },
  { id: "P3_ecosystem_mapping", shortLabel: "P3", label: "Ecosystem mapping", icon: Waypoints },
  { id: "P4_design", shortLabel: "P4", label: "Design", icon: Spline },
  { id: "P5_pilot", shortLabel: "P5", label: "Pilot", icon: Target },
  { id: "P6_scale", shortLabel: "P6", label: "Scale", icon: Scale },
  { id: "P7_inheritance", shortLabel: "P7", label: "Inheritance", icon: Rocket },
];

export function phaseIndex(phaseId: DeploymentPhaseId): number {
  const i = DEPLOYMENT_PHASES.findIndex((p) => p.id === phaseId);
  return i;
}

export function isDeploymentPhaseId(v: string): v is DeploymentPhaseId {
  return (DEPLOYMENT_PHASE_IDS as readonly string[]).includes(v);
}
