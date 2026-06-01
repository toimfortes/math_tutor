# Spaced Re-exposure — Plan (v2, post-MPR)

## MPR verdict on v1
v1 (insert reviews inside submit_turn via within-session intervening-item
counts) was rejected: core-loop invasive, idempotency/interleaving conflicts,
and a WEAK proxy for the real (cross-session) spacing effect. Codex's safer
recommendation: an **offline, timestamp-based review recommender outside the hot
path**. Adopted.

## Design (v2 — offline, real elapsed time, deterministic)
The append-only attempt_log already records `ts` per attempt. A pure recommender
uses real cross-session elapsed time (faithful to the spacing evidence) but runs
OFFLINE — no clock in the hot path, no submit_turn change, no scheduler/
interleaving interaction, no idempotency hazard. Mirrors the `calibrate` pattern.

`backend/content_pipeline/review.py` (current — strengthened to N-distinct mastery):
`due_from_mastery(mastery, now, *, interval_seconds, min_corrects=2) -> list[ReviewDue]`
(pure core, one student) and the multi-student adapter
`review_due(attempts, now, *, interval_seconds, min_corrects=2) -> dict[student_id, list[ReviewDue]]`
- attempts: (student_id, skill_id, problem_id, check_result, ts) from the log.
- For each (student, skill): a skill is MASTERED once the student has ≥ `min_corrects`
  DISTINCT correct problems in it (replaying one problem cannot qualify — counts
  distinct `problem_id`s, not attempts). A mastered skill is DUE if its most-recent
  CORRECT ts has lapsed (`now - last_correct_ts >= interval_seconds`); re-mastering it
  recently resets the clock. Skills not yet mastered are NOT due.
- `now` is an explicit parameter (deterministic; CLI passes wall-clock, tests
  pass fixed). seconds, not days, internally.
- ReviewDue = {skill_id, last_correct_ts, seconds_since}; per student sorted
  most-overdue first.

CLI `review-queue --session-db <db> --now <iso8601> --interval-days N
--output <json>`: read attempt_log, compute, emit JSON. Offline reporting only;
does NOT touch scheduling or write back.

## Self-harden checks
- Deterministic given (log, now): pure aggregation; no RNG; `now` injected.
- "Due" requires a prior CORRECT (mastered-then-lapsed), not just any attempt.
- A skill the student answered correctly again recently is NOT due (uses the
  LATEST correct ts).
- interval default 2 days (172800s), tunable/documented.
- No hot-path / scheduler / submit_turn change -> zero core-loop risk.
- Robust to None/unknown check_result (ignored) and missing ts.

## Tests
- a skill answered correct long ago (> interval) -> due; recently -> not due.
- never-correct skill -> not due.
- re-answered correct recently -> not due (latest-correct wins).
- per-student isolation; sorted most-overdue first.
- deterministic for fixed now; CLI smoke.

## Future (documented, not v1)
Feeding the review queue into session start (a review-first queue) is a later,
separate step; kept out of the hot path here.

## Gates
pytest green; content gates green; frontend unaffected.
