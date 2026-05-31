# P7 Scheduler And Assessment Evidence

Last verified: 2026-05-31

## Implemented Slice

- `POST /session/skip` marks the active problem as skipped/abandoned and schedules the next server-owned `PublicProblem`.
- `POST /assessment/transfer` records student-relative transfer credit for a skill and context.
- `POST /assessment/retention` records delayed-retention credit for a skill and context.
- `GET /student/{student_id}/state` returns skill-state summary fields, including transfer, retention, and computed mastery.
- `RoundRobinScheduler.transfer_ref(...)` and `retention_ref(...)` select skill-matched assessment candidates.
- `retention_is_due(...)` is pure and time-mockable for the 2-day retention rule.

## Verification

```bash
pytest -q
python -m backend.content_pipeline.safety
python -m backend.app.evals.deterministic_guardrails
npm test -- --run
npm run build
```

HTTP smoke against `http://127.0.0.1:8000`:

- `/health` returned `ok`.
- `/session/start` returned `lf_p01` for `space_logistics`.
- `/session/skip` returned next problem `lf_p02`.
- `/assessment/transfer` returned `transfer_passed=true`.
- `/assessment/retention` returned `retention_passed=true`.
- `/student/{id}/state` returned the expected `skill_id`.

## Residual Limits

- This remains an in-memory vertical slice. Durable scheduling, optimistic locking, notifications, and real re-engagement are still P9/commercial-hardening work.
- Transfer credit is represented as a server-recorded assessment event; the content bank is still the tiny gold slice, so broader transfer validity depends on P8 content expansion.
