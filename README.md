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

Set `RATE_LIMIT_PER_MINUTE` to cap requests to `/session/start` (per student)
and `/turn` (per session); exceeding it returns HTTP 429. Unset disables it.
The limiter is per-process and in-memory — a shared backend would be needed for
a multi-instance deploy.

## LLM Spend Cap

Set `DAILY_LLM_BUDGET` to cap LLM calls per student over a rolling 24h window.
When the budget is exhausted, turns degrade to deterministic fallback narration
instead of calling the provider — code-owned grading and scheduling keep working,
so the tutoring loop never breaks. Unset disables the cap.

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

Live generation and cross-provider extraction remain offline promotion steps, not reproducible CI gates.
