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

## Status: satisfied

The graph payload and local fallback are implemented:

- Gold problems `lf_p07`, `lf_p08`, `lf_p10` carry a public-safe `graph`
  payload (`kind`, bounds, `points`, `show_grid`) with no answer metadata.
- `backend/app/content/seed_loader.py` exposes it as `PublicProblem.graph`;
  the turn serializer in `backend/app/main.py` emits it.
- `backend/content_pipeline/verify.py` ties the `graph` representation to the
  payload, restricts payload keys, and rejects answer metadata. Covered by
  `backend/tests/test_p8_content_pipeline.py` and
  `backend/tests/test_p4_graph_payload.py`.
- `frontend/src/components/GraphView.tsx` renders axes, optional grid, integer
  tick labels, and the line as a pure client-side SVG — no Desmos, no network,
  no third-party embed. The SVG uses a generic aria-label and carries no
  answer-bearing data attributes.
- DOM tests: `frontend/src/components/GraphView.test.tsx` (graph modes) and
  the graph-representation case in `frontend/src/App.test.tsx`.

Verification:

```bash
pytest -q                                   # 80 passed
python -m backend.content_pipeline.verify   # 16 problems, 48 realizations, 48 template cases
python -m backend.content_pipeline.safety   # passed
cd frontend && npm test -- --run            # 5 files / 14 tests
npm run build                               # passed
```
