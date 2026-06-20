# Difficulty Calibration — Implementation Plan (v2, post-MPR)

## Goal
Calibrate generated-item difficulty with a **heuristic prior → continuous
empirical blend** where the prior **washes out as responses accrue** (research
verdict: no hard heuristic→IRT switch). v1 MPR review flagged that naive joint
Elo (updating student θ and item b together) is statistically unsound here
(scale drift, no anchor, student-K freeze, cold-start θ noise, order-dependence).
**Revised design: empirical-Bayes shrinkage on first-attempt pass-rate**, which
keeps the research-endorsed "prior washes out with N" property while removing the
unsound joint-estimation machinery.

## Design (v2)

### 1. Heuristic prior (pure) — `backend/content_pipeline/difficulty.py`
`heuristic_difficulty(skill_id, kind, params) -> float`: a difficulty on the
**logit scale, hard-clamped to [-3, 3]** (prevents sigmoid saturation). Built
from item covariates: skill base offset, |coefficients|, fractional answer,
negatives, solution-step count.
`difficulty_band(score) -> int` maps to 1-5 for display ONLY (problem_item.difficulty).
`band_to_logit(band) -> float`: fixed, documented inverse (band centres) so gold
items (authored 1-5) and generated items share ONE logit scale.

### 2. Empirical-Bayes calibrator (pure, ORDER-INDEPENDENT) — `backend/content_pipeline/calibration.py`
For each item, from **first-attempt-per-(student,item)** outcomes:
- outcome = 1 if first submission "correct", 0 if "incorrect"; **skip
  "undecidable"** (format failure, not difficulty) and **count it separately**
  as `undecidable_rate` for visibility.
- prior expected pass-rate p0 = sigmoid(-prior_logit) (harder prior -> lower p0).
- posterior pass-rate via Beta shrinkage with pseudo-count M (PRIOR_STRENGTH):
  `p_hat = (corrects + M*p0) / (n + M)`  — prior dominates when n << M and
  **washes out continuously as n grows** (the endorsed continuous blend).
- calibrated difficulty = clamp(-logit(p_hat), [-3, 3]).
- `calibrate(first_attempts, priors, *, prior_strength=12) -> dict[item_id, Calibrated]`
  Calibrated = {difficulty, responses(n), prior, calibrated: bool (n>0)}.

Why this resolves the MPR findings: it is a count aggregate, so it is
**fully order-independent** (no Elo path artifact, true determinism); it has **no
student ratings**, so there is no decaying-student-K freeze, no cold-start θ
noise, and no scale-identifiability/anchor/drift problem (difficulty is anchored
to the prior, not a free latent); retries are removed by first-attempt dedupe.

### 3. Wiring (no change to live selection)
- `generate_candidates`: problem_item.difficulty = difficulty_band(heuristic);
  store the float prior in extra_json (display + prior, NOT the calibrated value).
- CLI `calibrate --session-db <db> [--content-db <db>] --output <json>`:
  read attempt_log, dedupe to first attempt per (student_id, problem_id), build
  priors per item (generated: extra_json float; gold: band_to_logit(difficulty);
  else 0.0), run the calibrator, emit a JSON report. **JSON is the single source
  of truth for calibrated difficulty**; it is NOT written back to the content DB
  and does NOT touch scheduling (cleanest decoupling).

### 4. Tests (TDD)
- heuristic: monotonic per feature; harder kinds > easier; output always in [-3,3].
- band <-> logit: round-trip ordering; clamps.
- calibrator: zero attempts -> equals prior + calibrated=False; many-wrong ->
  difficulty rises toward hard, bounded; many-correct -> falls; **prior washout**
  (large n moves p_hat from p0 toward empirical); **order-independence**
  (shuffled first-attempt list -> identical result); first-attempt dedupe drops
  retries; undecidable skipped and surfaced as undecidable_rate; clamp at extremes.
- integration: calibrate over a synthetic attempt log + CLI smoke.

## How v1 MPR findings are addressed
- Decaying student-K freeze / cold-start θ noise / anchor & scale drift / order-
  dependence: ELIMINATED by dropping the student/joint-Elo model entirely.
- Prior saturation: heuristic + calibrated both hard-clamped to [-3, 3].
- Retries as independent / outcome unit: first-attempt-per-(student,item),
  first-submission outcome only (hint-assisted later corrects don't count).
- Gold vs generated commensurability: single documented band_to_logit mapping.
- Undecidable downward bias: skipped for difficulty but reported as
  undecidable_rate so the bias is visible, not silent.
- Zero-data vs neutral confusion: output carries `responses` + `calibrated` flag.
- Persistence contradiction: JSON-only; band column is display-only, explicitly
  not the calibrated value.
- Washout speed: PRIOR_STRENGTH=12 (prior ~half-weight near n=12) — tunable, documented.

## Documented limitations (not blocking, v1)
- No student-ability / grade-cohort modeling: an item seen mostly by strong
  students reads easier. Acceptable as a difficulty PROXY for a practice pool
  whose exposure is NOT ability-adaptive; revisit with covariate/explanatory IRT
  if difficulty-adaptive selection is ever added (then also decouple via parallel
  rating chains / randomized calibration exposure).

## Acceptance gates
pytest green; content verifier/safety/guardrails green; frontend unchanged
(JSON, no API/schema change); new modules have NO RNG/clock and are
order-independent.
