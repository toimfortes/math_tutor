# Band-targeted within-skill practice selection

Live adaptive ordering of the practice pool — the third rule of the research-backed
deterministic selection cascade (review-due-first and interleaving already exist;
difficulty stays frozen and offline-calibrated).

## What it does
`/practice/problems` reorders the returned list so that, **within each skill**,
problems nearest the student's target difficulty band come first. The target is a
desirable-difficulty success band (~70–85%, default ~75%) estimated **read-only**
from the student's own practice attempt log.

## Mechanism (`backend/app/domain/practice_selection.py`, pure & deterministic)
- `target_band(recent)` — staircase over one skill's deduped, decidable history:
  anchor = lower-median band over the last `WINDOW=5` attempts (order-independent
  within the window); movement only when the window is full; step `+1` if recent
  accuracy `>= 0.80`, `-1` if `<= 0.50`, else hold; clamp to `[1, 5]`. Seed band
  `2` only when a skill has no history.
- `order_for_student(problems, targets)` — **slot-preserving**: a targeted skill's
  problems are reordered by `(abs(difficulty - target), difficulty, id)` only within
  the global slots that skill already occupies; untouched skills are left
  byte-identical. Cross-skill layout is exactly preserved, so an untouched skill
  looks the same whether or not other skills have history (no fresh-vs-active jump).

## Wiring (`backend/app/main.py`)
`/practice/problems` reads `attempt_log.recent_decidable_by_problem(
f"practice:{student_id}", limit=200)`, groups the per-skill history, computes
targets, and returns `order_for_student`. Falls back to easiest-first when
persistence is off, there is no history, or all history is undecidable. The read
**dedups by `problem_id` in SQL before the limit** (`MAX(id) ... GROUP BY
problem_id`, latest decidable result wins), so the cap counts distinct problems —
re-attempting/farming one problem can neither inflate the staircase nor flush other
skills out of the window. No schema change.

## Safety invariants
- **No write path to item difficulty** — difficulty is read-only; calibration stays
  offline; the selection-bias feedback loop is structurally impossible.
- **No persisted per-student state** — the target is computed per request, discarded.
- **Exposure loop, not calibration loop** — bounded to ±1 per recompute, full-window
  gated; affects ordering only.
- **Deterministic** — no RNG, no clock; recency derives from log `id` order.
- **Practice-scoped** — derived only from exact `practice:{student_id}` rows.

## Hardening
Designed via the plan → self-harden → MPR (2 cycles) pipeline. Cycle 1 (Codex +
Gemini + Claude) confirmed the safety thesis and surfaced 8 selection-logic flaws
(global re-rank, seed whiplash, unreachable raise threshold, anchor volatility,
farming, yo-yo, determinism-claim contradiction, unbounded exposure) — all fixed.
Cycle 2 (Gemini + Claude) returned READY; its residuals (dedup move-to-end, shared
SELECT columns, even-count median test) are implemented and tested.

## Review-due-first tier
The research cascade's gating rule (review-due first, else band-targeted) is wired
live as a read-only reorder. `attempt_log.last_correct_ts_by_skill(student_id)`
(cross-session `MAX(ts) WHERE correct GROUP BY skill_id`) feeds the pure, tested
`review_due`; skills the student mastered anywhere but let lapse past the 2-day
interval are promoted to the front of `/practice/problems`. `order_for_student` gained
a `due_skills` tier: round-robin **interleaved** across due skills, **capped** at
`REVIEW_QUOTA=2` per skill (no massing, no monopolization), remainder in band-targeted
order. The wall-clock is read only via a `get_clock` FastAPI dependency (pure modules
get `now` injected; tests override it). Review scope is cross-session (mastery anywhere
counts); band-targeting stays practice-scoped (a deliberate asymmetry — retention timing
vs practice-pool difficulty).

## Calibration selection-bias guard
Because practice exposure is now adaptive, `calibrate_difficulty` excludes the practice
stream: `AND session_id NOT LIKE 'practice:%'` on the **outer** first-attempt query
(the `MIN(id)` subquery stays global, so an item first seen in practice is dropped
rather than counting a warmed-up assessment retry as a cold first attempt). The
calibration cohort is thus cold, non-practice first attempts — closing the
selection-bias loop on the offline-reader end.

## Deferred
Cross-skill interleaving of the non-due practice list; single next-item endpoint; an
A/B-validated band target for linear functions; per-skill forgetting curves / bandits;
stronger (N-corrects) mastery for review eligibility; random-exposure calibration
cohort; a "Review due" UI badge.
