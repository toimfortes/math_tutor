# Math Tutor

Deterministic linear-functions tutor prototype. The backend owns checking, mastery, XP, scheduling, and content verification; the LLM owns only runtime dialogue inside the contract in `docs/llm-contract.md`.

## Setup

```bash
python -m pip install -r requirements-dev.txt
cd frontend
npm ci
```

Optional runtime configuration starts from `.env.example`. Do not commit real API keys.

## Run Locally

Backend:

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`. The frontend proxies `/api/*` to the backend.

## Runtime LLM Providers

Default local mode uses the mock provider:

```bash
LLM_PROVIDER=mock python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Gemini API mode:

```bash
LLM_PROVIDER=gemini GEMINI_API_KEY=... python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Anthropic API mode:

```bash
LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=... python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

## Session Persistence

By default sessions live in memory and are lost on restart. Set `SESSION_DB_PATH`
to a file to persist them to SQLite (stdlib `sqlite3`, no migrations needed —
the table is created on startup). Each session is stored as one JSON aggregate
row with a `version` column for optimistic locking. With a db path set, every
graded turn is also written to an append-only `attempt_log` table (an immutable
analytics trail, separate from the mutable session aggregate).

```bash
SESSION_DB_PATH=./sessions.db LLM_PROVIDER=mock \
  python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

## Rate Limiting

Set `RATE_LIMIT_PER_MINUTE` to cap requests to `/session/start` (per student),
mutating session endpoints such as `/turn`, `/session/skip`, and `/assessment/*`
(per session), and the credential endpoints `/auth/login` and `/auth/register`
(per `{client-ip}:{student-id}`, enforced before the credential check so failed
password guesses count). Exceeding it returns HTTP 429. Unset disables it. The
limiter is per-process and in-memory — a shared backend (plus trusted client-IP /
`X-Forwarded-For` handling behind a proxy and a coarser per-IP cap to throttle
cross-account password spraying) would be needed for a hardened multi-instance
deploy.

## LLM Spend Cap

Set `DAILY_LLM_BUDGET` to cap LLM calls per student over a rolling 24h window.
When the budget is exhausted, turns degrade to deterministic fallback narration
instead of calling the provider — code-owned grading and scheduling keep working,
so the tutoring loop never breaks. Unset disables the cap.

## Generated API Types

`frontend/src/generated/apiSchema.ts` is generated from the backend OpenAPI
schema and used to type the API client's response parsing, catching contract
drift at compile time. Regenerate after changing response models:

```bash
cd frontend
npm run generate:api
```

Check the committed generated schema before pushing:

```bash
cd frontend
npm run check:api
```

## Verification

Backend:

```bash
pytest -q
python -m backend.app.evals.deterministic_guardrails
python -m backend.content_pipeline.verify
python -m backend.content_pipeline.safety
```

Frontend:

```bash
cd frontend
npm test -- --run
npm run build
```

Live model smoke/eval commands require API keys and are not part of deterministic CI:

```bash
LLM_PROVIDER=gemini GEMINI_API_KEY=... python -m backend.app.evals.live_llm_smoke
LLM_PROVIDER=gemini GEMINI_API_KEY=... python -m backend.app.evals.live_prompt_eval
LLM_PROVIDER=gemini GEMINI_API_KEY=... python -m backend.app.evals.live_turn_smoke
```

## Content Pipeline

The committed gold bank is `backend/content_pipeline/gold/linear_functions.json`.

Deterministic P8 verification recomputes all gold answers from `backend/content_pipeline/templates/linear_functions.py` and checks schema, semantic role metadata, safety terms, and answer-shaped public leaks:

```bash
python -m backend.content_pipeline.verify
```

Promotion provenance is represented by `backend.content_pipeline.provenance`. It creates a reviewable manifest with the artifact SHA-256 hash, verifier summary, and provider/model/prompt run metadata for any generated bank promoted later.

```bash
python -m backend.content_pipeline.provenance \
  --artifact backend/content_pipeline/gold/linear_functions.json \
  --output promotion-manifest.json \
  --provider-run provider=gemini,model=gemini-3.5-flash,role=narrator,prompt_version=narrator-v1,run_id=run-001
```

Live generation and cross-provider extraction remain offline promotion steps, not reproducible CI gates.

### Source ingestion → gated generation → practice pool

`backend/content_pipeline/ingest.py` builds a SQLite content substrate and a separate, gated path for generated content. The runtime gold assessment bank is never altered by this — `export-gold` only emits `curation_status='promoted'` (the frozen 16), and the frozen-bank verifier guards it.

```bash
python -m backend.content_pipeline.ingest gold --db content.sqlite3                 # gold -> DB
python -m backend.content_pipeline.ingest oer --db content.sqlite3                  # stage reviewed OER metadata
python -m backend.content_pipeline.ingest generate-candidates --db content.sqlite3  # gated parametric candidates
python -m backend.content_pipeline.ingest promote --db content.sqlite3              # re-verify -> 'approved'
python -m backend.content_pipeline.ingest export-practice --db content.sqlite3 --output practice.json
python -m backend.content_pipeline.ingest verify-practice --input practice.json     # re-derivation gate
```

Each generated candidate is validated through the same gates as runtime content (deterministic solver result, code-owned checker round-trip, safety scan, no answer leak). Approved content is exported as a **separate practice pool**, distinct from the frozen gold assessment bank. Set `PRACTICE_BANK_PATH` to serve it via the authenticated `/practice/*` endpoints and the frontend "Extra practice" mode; unset leaves the pool empty. Browser coverage: `cd frontend && npm run e2e`.
