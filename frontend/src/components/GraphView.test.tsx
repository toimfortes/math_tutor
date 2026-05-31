import type { ReactElement } from "react";
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { GraphView, GraphSpec } from "./GraphView";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const SLOPE_GRAPH: GraphSpec = {
  kind: "line",
  xMin: -1,
  xMax: 5,
  yMin: -1,
  yMax: 6,
  points: [
    [0, 0],
    [1, 2],
  ],
  showGrid: true,
};

const INTERCEPT_GRAPH: GraphSpec = {
  kind: "line",
  xMin: -1,
  xMax: 8,
  yMin: -1,
  yMax: 14,
  points: [
    [0, 12],
    [6, 0],
  ],
  showGrid: true,
};

describe("GraphView", () => {
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

  it("renders a local svg with a polyline through the data points", () => {
    const container = render(<GraphView graph={SLOPE_GRAPH} />);

    const svg = container.querySelector("svg.graph-view");
    expect(svg).not.toBeNull();
    const polyline = container.querySelector("polyline");
    expect(polyline).not.toBeNull();
    const pointPairs = polyline?.getAttribute("points")?.trim().split(/\s+/) ?? [];
    expect(pointPairs).toHaveLength(2);
  });

  it("draws grid lines when show_grid is enabled and omits them otherwise", () => {
    const withGrid = render(<GraphView graph={SLOPE_GRAPH} />);
    expect(withGrid.querySelectorAll("line.grid-line").length).toBeGreaterThan(0);

    act(() => root?.unmount());
    host?.remove();
    const withoutGrid = render(<GraphView graph={{ ...SLOPE_GRAPH, showGrid: false }} />);
    expect(withoutGrid.querySelectorAll("line.grid-line").length).toBe(0);
  });

  it("renders no third-party embed and no network resources", () => {
    const container = render(<GraphView graph={INTERCEPT_GRAPH} />);

    expect(container.querySelector("iframe")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });

  it("keeps grid density manageable for large coordinate ranges", () => {
    const largeGraph: GraphSpec = {
      kind: "line",
      xMin: -1,
      xMax: 8,
      yMin: -10,
      yMax: 100,
      points: [
        [0, 90],
        [6, 30],
      ],
      showGrid: true,
    };

    const container = render(<GraphView graph={largeGraph} />);

    const gridLines = container.querySelectorAll("line.grid-line").length;
    expect(gridLines).toBeGreaterThan(0);
    expect(gridLines).toBeLessThanOrEqual(28);
  });

  it("does not expose the answer in accessible labels or data attributes", () => {
    const container = render(<GraphView graph={SLOPE_GRAPH} />);

    const svg = container.querySelector("svg.graph-view");
    expect(svg?.getAttribute("aria-label")).toBe("Coordinate grid with a plotted line");
    expect(container.querySelector("[data-answer]")).toBeNull();
    expect(container.querySelector("[data-slope]")).toBeNull();
    expect(container.querySelector("[data-intercept]")).toBeNull();
  });
});
