import { CoordinatePlane } from "./CoordinatePlane";

export type GridSpec = {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
  showGrid: boolean;
};

/**
 * Empty labeled coordinate grid for plot-a-point problems. It renders only the
 * plane (axes, grid, ticks) and never plots anything, so the answer point can
 * never appear in the DOM — the grid payload carries no points to begin with.
 */
export function GridView({
  grid,
  width = 320,
  height = 320,
}: {
  grid: GridSpec;
  width?: number;
  height?: number;
}) {
  return (
    <CoordinatePlane bounds={grid} className="grid-view" ariaLabel="Empty coordinate grid" width={width} height={height} />
  );
}
