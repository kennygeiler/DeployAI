/**
 * @deployai/design-tokens — single source of truth for DeployAI design tokens.
 *
 * Satisfies UX-DR1 (color/spacing/shadow/radius/elevation) and UX-DR2 (typography).
 * Every consumer surface — `apps/web`, `apps/edge-agent`, future `packages/shared-ui`
 * components, and Storybook stories — imports from this package.
 */

export { colors, ink, paper, stone, evidence, signal, nullState, destructive } from "./colors.js";
export type { Colors } from "./colors.js";

export { spacing } from "./spacing.js";
export type { Spacing, SpacingKey } from "./spacing.js";

export { typography, fontFamilies, typeScale, readingMeasure } from "./typography.js";
export type { Typography, TypeScaleStep } from "./typography.js";

export { shadows } from "./shadows.js";
export type { Shadows, ShadowKey } from "./shadows.js";

export { radii } from "./radii.js";
export type { Radii, RadiusKey } from "./radii.js";

export { elevation } from "./elevation.js";
export type { Elevation, ElevationKey } from "./elevation.js";

export { motion } from "./motion.js";
export type { Motion } from "./motion.js";

import { colors } from "./colors.js";
import { spacing } from "./spacing.js";
import { typography } from "./typography.js";
import { shadows } from "./shadows.js";
import { radii } from "./radii.js";
import { elevation } from "./elevation.js";
import { motion } from "./motion.js";

/** Aggregate of every token domain — useful for Storybook and visual audits. */
export const tokens = {
  colors,
  spacing,
  typography,
  shadows,
  radii,
  elevation,
  motion,
} as const;

export type Tokens = typeof tokens;
