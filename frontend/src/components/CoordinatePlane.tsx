import { ReactNode } from "react";

export type PlaneBounds = {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
  showGrid: boolean;
};

const PADDING = 28;

/**
 * Shared local SVG coordinate plane: axes, optional grid, and integer-nice tick
 * labels. Overlay content (a line, points, etc.) is supplied via a render-prop
 * that receives the math->pixel mappers, so callers like GraphView draw on top
 * while GridView renders the bare plane. Pure client-side; no network.
 */
export function CoordinatePlane({
  bounds,
  className,
  ariaLabel,
  width = 320,
  height = 320,
  children,
}: {
  bounds: PlaneBounds;
  className: string;
  ariaLabel: string;
  width?: number;
  height?: number;
  children?: (toX: (x: number) => number, toY: (y: number) => number) => ReactNode;
}) {
  const plotWidth = width - PADDING * 2;
  const plotHeight = height - PADDING * 2;

  const toX = (x: number) => PADDING + ((x - bounds.xMin) / (bounds.xMax - bounds.xMin)) * plotWidth;
  const toY = (y: number) => PADDING + ((bounds.yMax - y) / (bounds.yMax - bounds.yMin)) * plotHeight;

  const xTicks = ticks(bounds.xMin, bounds.xMax);
  const yTicks = ticks(bounds.yMin, bounds.yMax);
  const showXAxis = bounds.yMin <= 0 && bounds.yMax >= 0;
  const showYAxis = bounds.xMin <= 0 && bounds.xMax >= 0;

  return (
    <svg
      className={className}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={ariaLabel}
    >
      {bounds.showGrid &&
        xTicks.map((x) => (
          <line key={`grid-x-${x}`} className="grid-line" x1={toX(x)} y1={PADDING} x2={toX(x)} y2={height - PADDING} />
        ))}
      {bounds.showGrid &&
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

      {children?.(toX, toY)}
    </svg>
  );
}

// Tick marks at a "nice" step (1/2/5 x 10^n) so wide ranges stay readable
// (e.g. a 0..100 axis steps by 20 rather than drawing a line at every integer).
export function ticks(min: number, max: number): number[] {
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
