# P6 Live LLM Evidence

Last verified: 2026-05-31

## Provider

- Runtime provider tested: Gemini API
- Model tested: `gemini-3.5-flash`
- Auth path: server-side API key only, loaded locally from `/home/antoniofortes/Projects/uk-family-law-ai/.env`
- Key handling: only `GOOGLE_API_KEY` / `GEMINI_API_KEY` / `GEMINI_MODEL` are read by the local smoke harness; key values are not printed or committed.

## Commands

```bash
python -m backend.app.evals.live_llm_smoke
python -m backend.app.evals.live_prompt_eval
python -m backend.app.evals.live_turn_smoke
```

## Results

- Live Gemini smoke passed with `leak_risk=none`; latest observed token count: `2132`.
- Live adversarial prompt eval passed: `cases=4`, latest observed token count: `8796`.
- Live turn smoke passed: start problem `lf_p01`, submitted malformed answer returned `check=undecidable`, `move=request_clarification`, `hint=0`, `teacher_checks=2`.

## Residual Limits

- This is a live smoke/eval gate, not deterministic CI. CI must continue to run deterministic guardrails against frozen test fixtures.
- Token counts are observations from one run and must be re-measured after prompt, model, or provider changes.
- Gemini log/data-retention posture is pinned in `docs/provider-policy-sources.md`; commercial deployment still requires account-level confirmation and legal review before processing real minor data.
