import type { ReactElement } from "react";
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { GridView, GridSpec } from "./GridView";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const GRID: GridSpec = {
  xMin: -1,
  xMax: 6,
  yMin: -1,
  yMax: 6,
  showGrid: true,
};

describe("GridView", () => {
  let root: Root | null = null;
  let host: HTMLDivElement | null = null;

  afterEach(() => {
    if (root) act(() => root?.unmount());
    host?.remove();
    root = null;
    host = null;
  });

  function render(node: ReactElement): HTMLDivElement {
    host = document.createElement("div");
    document.body.append(host);
    root = createRoot(host);
    act(() => root?.render(node));
    return host;
  }

  it("renders an empty labeled coordinate grid", () => {
    const container = render(<GridView grid={GRID} />);

    const svg = container.querySelector("svg.grid-view");
    expect(svg).not.toBeNull();
    expect(container.querySelectorAll("line.grid-line").length).toBeGreaterThan(0);
    expect(svg?.getAttribute("aria-label")).toBe("Empty coordinate grid");
  });

  it("plots nothing, so the answer point cannot leak", () => {
    const container = render(<GridView grid={GRID} />);

    expect(container.querySelector("polyline")).toBeNull();
    expect(container.querySelector("circle")).toBeNull();
    expect(container.querySelector("[data-answer]")).toBeNull();
  });
});
