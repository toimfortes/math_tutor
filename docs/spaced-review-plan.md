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

`backend/content_pipeline/review.py`:
`review_due(attempts, now, *, interval_seconds) -> dict[student_id, list[ReviewDue]]`
- attempts: (student_id, skill_id, check_result, ts) from the log.
- For each (student, skill): find the most-recent CORRECT ts. A skill is DUE if
  `now - last_correct_ts >= interval_seconds` AND the student has no MORE-RECENT
  correct attempt (by definition it's the latest correct) — i.e. they got it
  right, then let it lapse. Skills never answered correctly are NOT due (nothing
  mastered to review).
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
