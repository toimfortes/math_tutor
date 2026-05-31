# P8 Content Pipeline Evidence

Date: 2026-05-31

## Implemented in this slice

- Added deterministic linear-functions template cases for every committed gold realization.
- Added `solve_case()` so Python recomputes every gold canonical answer from template params.
- Added deterministic diagnostic distractor generation for slope/rate templates.
- Added `python -m backend.content_pipeline.verify` as the frozen-bank promotion check.

## Gate Results

```text
$ pytest -q backend/tests/test_p8_content_pipeline.py
3 passed in 0.02s

$ python -m backend.content_pipeline.verify
frozen gold bank verified: 16 problems, 48 realizations, 48 template cases

$ python -m backend.content_pipeline.safety
gold theme safety scan passed

$ pytest -q
72 passed in 0.40s
```

## What This Proves

- Every runtime `RealizedProblemRef` in the gold bank has a corresponding deterministic template case.
- Template `solve()` reproduces the private canonical answer for the exact shown realization.
- The frozen artifact has required schema fields, authored hint scaffolds, semantic role metadata, deterministic safety scan coverage, and no answer-shaped public leak patterns.

## Residual Limits

- This is the deterministic CI side of P8 only.
- It does not yet generate new narrated items.
- It does not yet run live cross-provider extraction or deep-theming classification for a newly promoted generated bank.
- The verifier is a promotion gate for committed artifacts, not proof that live third-party model generation is reproducible.
