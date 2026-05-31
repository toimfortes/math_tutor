export type GraphSpec = {
  kind: string;
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
  points: Array<[number, number]>;
  showGrid: boolean;
};

const PADDING = 28;

/**
 * Local SVG graph fallback for graph-representation problems.
 *
 * Renders coordinate axes, optional grid, integer tick labels, and the line
 * described by the public-safe graph payload — entirely client-side, with no
 * Desmos embed and no network access. The component receives only graph
 * geometry, never the canonical answer, so it cannot leak it; the SVG carries a
 * generic aria-label and no answer-bearing data attributes.
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
  const plotWidth = width - PADDING * 2;
  const plotHeight = height - PADDING * 2;

  const toX = (x: number) => PADDING + ((x - graph.xMin) / (graph.xMax - graph.xMin)) * plotWidth;
  const toY = (y: number) => PADDING + ((graph.yMax - y) / (graph.yMax - graph.yMin)) * plotHeight;

  const xTicks = ticks(graph.xMin, graph.xMax);
  const yTicks = ticks(graph.yMin, graph.yMax);
  const showXAxis = graph.yMin <= 0 && graph.yMax >= 0;
  const showYAxis = graph.xMin <= 0 && graph.xMax >= 0;
  const linePoints = graph.points.map(([x, y]) => `${toX(x)},${toY(y)}`).join(" ");

  return (
    <svg
      className="graph-view"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Coordinate grid with a plotted line"
    >
      {graph.showGrid &&
        xTicks.map((x) => (
          <line key={`grid-x-${x}`} className="grid-line" x1={toX(x)} y1={PADDING} x2={toX(x)} y2={height - PADDING} />
        ))}
      {graph.showGrid &&
        yTicks.map((y) => (
          <line key={`grid-y-${y}`} className="grid-line" x1={PADDING} y1={toY(y)} x2={width - PADDING} y2={toY(y)} />
        ))}

      {showXAxis && <line className="axis-line" x1={PADDING} y1={toY(0)} x2={width - PADDING} y2={toY(0)} />}
      {showYAxis && <line className="axis-line" x1={toX(0)} y1={PADDING} x2={toX(0)} y2={height - PADDING} />}

      {showXAxis &&
        xTicks
          .filter((x) => x !== 0)
          .map((x) => (
            <text key={`tick-x-${x}`} className="tick-label" x={toX(x)} y={toY(0) + 14} textAnchor="middle">
              {x}
            </text>
          ))}
      {showYAxis &&
        yTicks
          .filter((y) => y !== 0)
          .map((y) => (
            <text key={`tick-y-${y}`} className="tick-label" x={toX(0) - 8} y={toY(y) + 4} textAnchor="end">
              {y}
            </text>
          ))}

      <polyline className="graph-line" points={linePoints} fill="none" />
      {graph.points.map(([x, y], index) => (
        <circle key={`point-${index}`} className="graph-point" cx={toX(x)} cy={toY(y)} r={4} />
      ))}
    </svg>
  );
}

// Tick marks at a "nice" step (1/2/5 x 10^n) so that wide ranges stay readable
// (e.g. a 0..100 axis steps by 20 rather than drawing a line at every integer).
function ticks(min: number, max: number): number[] {
  const step = niceStep(max - min);
  const out: number[] = [];
  const start = Math.ceil(min / step) * step;
  for (let value = start; value <= max + 1e-9; value += step) {
    out.push(Number(value.toFixed(6)));
  }
  return out;
}

function niceStep(range: number): number {
  const target = range / 8;
  const magnitude = Math.pow(10, Math.floor(Math.log10(target)));
  const candidates = [1, 2, 5, 10].map((multiplier) => multiplier * magnitude);
  return candidates.find((candidate) => candidate >= target) ?? 10 * magnitude;
}
