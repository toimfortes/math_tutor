# Graduated Practice Ordering — Plan

## Goal
Make the heuristic/calibrated difficulty reach learners: serve the practice pool
**easiest-first** (graduated progression — scaffolding/mastery evidence) with a
difficulty indicator, instead of insertion order. Low-risk, deterministic.

## Design
1. export-practice: include each item's `difficulty` (problem_item.difficulty
   band, 1-5) in the practice JSON.
2. practice_loader: PracticeProblem gains `difficulty: int`; PracticeBank
   .public_problems() returns items sorted by (difficulty asc, id) — backend owns
   the order so any client is correct.
3. /practice/problems already returns public_problems() -> now ordered + carries
   difficulty. No new endpoint, no schema-model change (plain dict).
4. Frontend: PracticeProblem type gains difficulty; PracticePanel shows a small
   "Level N" badge; order comes from the backend (no client sort needed).

## Self-harden checks
- Deterministic tiebreak: sort by (difficulty, id) so equal-difficulty order is
  stable (no RNG).
- Missing difficulty in JSON (older artifact): default to band 3 so load never
  crashes; document.
- Backend is source of truth for order; frontend must NOT re-sort (avoid
  divergence).
- No API schema change (practice endpoints return plain dict) -> no apiSchema
  regen / drift gate impact.

## Tests
- loader: public_problems() sorted ascending by difficulty; stable tiebreak.
- export: difficulty present per problem.
- /practice/problems: returned order is non-decreasing in difficulty.
- frontend: PracticePanel renders the level badge; api parses difficulty.

## Gates
pytest green; content gates green; frontend vitest+build green; e2e green.
