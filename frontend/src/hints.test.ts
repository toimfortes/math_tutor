import { describe, expect, it } from "vitest";
import type { HintScaffold } from "./api";
import { hintForLevel } from "./hints";

const scaffold: HintScaffold = {
  maxSafeHintLevel: 2,
  level0: "Think about the relationship.",
  level1: "Use the relevant representation.",
  level2: "Name the operation.",
  level3: null,
};

describe("hintForLevel", () => {
  it("returns the gentlest hint at level 0", () => {
    expect(hintForLevel(scaffold, 0)).toBe("Think about the relationship.");
  });

  it("returns the matching hint as the level rises", () => {
    expect(hintForLevel(scaffold, 1)).toBe("Use the relevant representation.");
    expect(hintForLevel(scaffold, 2)).toBe("Name the operation.");
  });

  it("never exceeds the safe hint ceiling", () => {
    expect(hintForLevel(scaffold, 3)).toBe("Name the operation.");
  });

  it("clamps a negative level to the gentlest hint", () => {
    expect(hintForLevel(scaffold, -1)).toBe("Think about the relationship.");
  });

  it("falls back past missing hint levels", () => {
    const gappy: HintScaffold = { ...scaffold, maxSafeHintLevel: 3, level2: "", level3: null };
    expect(hintForLevel(gappy, 3)).toBe("Use the relevant representation.");
  });
});
