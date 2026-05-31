# GraphView Fallback

The v1 vertical slice contains graph items for `lin_slope_from_graph` and `lin_y_intercept`, so graph rendering cannot depend on Desmos approval.

## Requirement

`GraphView` must have a local SVG/canvas graph fallback before graph problems are enabled.

Desmos is not required for v1. Desmos remains behind the commercial-use gate in `docs/p0a-decisions.md`.

## Local SVG/canvas behavior

The fallback must:
- Render coordinate axes, grid lines, labeled tick marks, and one line segment or line.
- Support graph data for `lin_slope_from_graph` and `lin_y_intercept`.
- Work with no network access and no third-party graph embed.
- Avoid placing the answer in accessible labels, DOM text, tooltips, or data attributes.
- Use deterministic props generated from `PublicProblem` graph metadata.
- Render safely on desktop and mobile.

## Data shape

P4 may use a minimal graph payload:

```json
{
  "kind": "line",
  "x_min": -1,
  "x_max": 8,
  "y_min": -1,
  "y_max": 12,
  "points": [[0, 0], [4, 3]],
  "show_grid": true
}
```

The payload must be public-safe. It may show the graph that the student sees, but it must not include `canonical_answer`, `solution_method`, or hidden answer metadata.

## P4 gate

The P4 gate is not satisfied unless:
- Graph problems render through the local fallback with no network.
- `GraphView` has screenshot or DOM tests for the graph modes in the gold set.
- Desmos can be absent without breaking the vertical slice.
