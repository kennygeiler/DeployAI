import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// tailwind-merge only knows Tailwind's stock scale values, so a design-token
// radius like `rounded-card` doesn't dedupe against a base `rounded-full` —
// both classes land in the DOM and stylesheet order (not call order) wins.
// Register the token radii (packages/design-tokens: chip/control/card) so a
// caller's radius override actually replaces the component default.
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      rounded: [{ rounded: ["chip", "control", "card"] }],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
