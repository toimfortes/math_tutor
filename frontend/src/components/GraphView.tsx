import { CoordinatePlane } from "./CoordinatePlane";

export type GraphSpec = {
  kind: string;
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
  points: Array<[number, number]>;
  showGrid: boolean;
};

/**
 * Local SVG graph for graph-representation and two-point problems.
 *
 * Renders the line described by the public-safe graph payload over a shared
 * CoordinatePlane — no Desmos embed, no network. The component receives only
 * graph geometry, never the canonical answer, and the SVG carries a generic
 * aria-label and no answer-bearing data attributes, so it cannot leak it.
 */
export function GraphView({
  graph,
  width = 320,
  height = 320,
}: {
  graph: GraphSpec;
  width?: number;
  height?: number;
}) {
  return (
    <CoordinatePlane
      bounds={graph}
      className="graph-view"
      ariaLabel="Coordinate grid with a plotted line"
      width={width}
      height={height}
    >
      {(toX, toY) => (
        <>
          <polyline className="graph-line" points={graph.points.map(([x, y]) => `${toX(x)},${toY(y)}`).join(" ")} fill="none" />
          {graph.points.map(([x, y], index) => (
            <circle key={`point-${index}`} className="graph-point" cx={toX(x)} cy={toY(y)} r={4} />
          ))}
        </>
      )}
    </CoordinatePlane>
  );
}
