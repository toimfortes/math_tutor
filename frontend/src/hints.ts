import type { HintScaffold } from "./api";

/**
 * Pick the authored hint to show for a backend-proposed help level. The level
 * is clamped to the scaffold's safe ceiling, and missing rungs (e.g. a null
 * level_3) fall back to the nearest lower authored hint.
 */
export function hintForLevel(scaffold: HintScaffold, level: number): string {
  const capped = Math.max(0, Math.min(level, scaffold.maxSafeHintLevel));
  const ladder = [scaffold.level0, scaffold.level1, scaffold.level2, scaffold.level3];
  for (let index = capped; index >= 0; index -= 1) {
    const text = ladder[index];
    if (text) {
      return text;
    }
  }
  return scaffold.level0;
}
