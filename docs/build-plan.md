# Adaptive AI Math Tutor — Build Spec v2

**Audience:** Claude Code (the coding agent that will build this).
**This supersedes v1.** Read the whole file before writing code. **MUST / MUST NOT** are hard constraints. If a phase's acceptance criteria can't be met, stop and report rather than working around them.

**What changed from v1 (changelog):**
- Content is no longer hand-authored JSON. It is produced by an **offline content pipeline** built on **parametric templates** (Python computes every answer) + a **three-model verification gate**. (§9)
- Added an **Auth & Model Access** section: runtime LLM access is **API keys only — never subscription OAuth/CLI** (ToS + commercial dealbreaker). (§11)
- Added a **Commercial Trajectory & Privacy** section keyed to a **target age-band decision** you must make before building auth. (§12)
- Frontend types are **auto-generated from the backend OpenAPI spec**, not hand-mirrored. (§10)
- LLM calls are **tiered** across models, and any cost downgrade is **gated by the adversarial eval suite**, not by cost. (§6.6)
- **math.js is removed.** Pyodide is explicitly deferred. (§10, §15)
- Postgres + SQLAlchemy 2.x + Alembic are **retained** (existing infra + commercial trajectory).

**v2.1 refinements (folded in below):**
- Verification gate uses **structured parameter extraction → deterministic `solve()`**, not free-form LLM re-solving (lower false-reject rate, stricter check). (§9.3)
- Frontend codegen standardized on **Orval** (TanStack Query hooks); coupling noted as deliberate. (§10)
- User auth uses **FastAPI-Users**; the COPPA consent flow sits **on top** of it, not inside it. (§11.4, §12)
- Prompt-caching **ordering rule** made explicit (stable prefix first, history last); exact mechanics to be verified against current docs at P4. (§6.8)

**v2.2 refinements (folded in below):**
- **Build order re-sequenced** so a working mocked `/turn` and the slice come *before* the LLM and *well before* the content pipeline. The pipeline is a scaling concern and no longer gates v1. (§16, §17)
- **Public/Private problem DTOs** make answer leakage harder by preventing accidental serialization of `canonical_answer` and banned intermediates into runtime prompts/logs. This is defense-in-depth, not a claim that the model cannot re-derive simple answers. (§3.1, §6.7)
- **P0a now gates external/user-data work on the age-band/privacy/dependency decisions** while allowing pure local math/schema work to proceed. (§12, §16)
- **Checker hardened for untrusted input:** symbol/function whitelist, parse length/depth caps, eval timeouts, equation/tuple/unit handling, property-based tests. (§8)
- **FastAPI-Users de-risked:** it is in maintenance mode (recent OAuth CSRF fix) — pin a version and specify CSRF/cookie + JWT/session + parent-child model explicitly. (§11.4)
- **Model IDs configurable; cost claims require measured token budgets + per-user caps** (no casual "few dollars" in any commercial context). Cache-hit gate now checks `usage` fields against source-verified per-model minimums and response `usage` fields. (§6.6, §6.8)

---

## 0. Core principle

> **The LLM owns the *words*. Deterministic code owns the *facts*.**
> The model generates narrative, questions, and hints. Code decides correctness, XP, and mastery. The model is **never** the authority on math truth — not at runtime, and (new in v2) **not when generating content either**.

### Ownership table — DO NOT VIOLATE

| Field / decision | Owner | Notes |
|---|---|---|
| `dialogue`, `pedagogical_move`, `ui_mode` | **LLM** | Themed narrative + question. |
| `check_result` / derived `is_correct` | **CODE** | Tri-state checker result (`correct`/`incorrect`/`undecidable`) vs canonical answer. LLM output of this is ignored. |
| `xp_awarded` | **CODE** | Pure function. |
| `concept_mastered` | **CODE** | Server-side mastery rule. |
| `allowed_help_level` | **CODE** | Hint ceiling, passed into the prompt. |
| **Every generated problem's canonical answer** | **CODE** | Computed by a pure Python `solve()` at content-build time (§9). The hand-authored gold set is a regression fixture. The LLM never authors an answer. |

---

## 1. Tech stack (fixed)

- **Backend:** Python 3.11+, **FastAPI**, **Pydantic v2**.
- **DB:** **PostgreSQL** + **SQLAlchemy 2.x** + **Alembic** (retained — existing infra, commercial path needs migrations + relational guarantees).
- **Math checking:** **SymPy** server-side, authoritative. (math.js removed; Pyodide deferred — see §10.)
- **Mastery:** pure-function rule engine; **pyBKT** optional behind the same interface.
- **LLM (runtime):** provider-abstracted `LLMClient`. Supported v1 providers: **Gemini API** with structured JSON output and **Anthropic API** with tool use. **API key auth only** (§11); `mock` remains the default in local/CI.
- **LLM (content build):** same interface, plus a **provider-diverse verification step** using a second/third provider (Gemini, OpenAI/Codex) — offline only (§9).
- **Frontend:** **React + Vite + TypeScript**; **KaTeX** rendering; graphing behind a swappable `GraphView` abstraction. **Types auto-generated from OpenAPI** (§10).
- **Testing:** pytest, Vitest, and an **adversarial + Socratic eval suite** wired as a **CI gate** (§14).
- **Config:** `pydantic-settings` + `.env`; secrets via env/secret-manager. **No secrets ever reach the client.**

---

## 2. Repository structure

```
math-tutor/
├── README.md
├── .env.example
├── docker-compose.yml             # postgres (use your existing instance if preferred)
├── docs/
│   ├── p0a-decisions.md
│   ├── llm-contract.md            # self-contained Socratic prompt + tool schema
│   ├── provider-policy-sources.md
│   ├── content-safety-review.md
│   └── graphview-fallback.md
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models/                # SQLAlchemy
│   │   ├── schemas/               # Pydantic (source of truth for OpenAPI → TS)
│   │   ├── domain/
│   │   │   ├── answer_normalizer.py # student input normalization (PURE)
│   │   │   ├── checker.py         # SymPy correctness (PURE)
│   │   │   ├── diagnostic_checker.py # known wrong-answer patterns (PURE)
│   │   │   ├── mastery.py         # mastery rule (PURE)
│   │   │   ├── xp.py              # XP rule (PURE)
│   │   │   ├── scheduler.py       # next-skill + spaced/interleaved review
│   │   │   └── help_ceiling.py    # hint-ceiling logic (PURE)
│   │   ├── llm/
│   │   │   ├── client.py          # LLMClient interface + Anthropic impl + router
│   │   │   ├── prompts.py
│   │   │   └── guardrails.py      # leak scan, hint-ceiling enforce, injection wrap
│   │   ├── services/turn.py       # the /turn pipeline
│   │   └── content/               # COMPILED bank (output of the pipeline)
│   │       └── linear_functions.json
│   ├── content_pipeline/          # OFFLINE — not imported by the running app
│   │   ├── templates/             # parametric templates (PURE solve())
│   │   │   └── linear_functions.py
│   │   ├── narrate.py             # LLM narrator (words only, given params+answer)
│   │   ├── verify.py              # 3-model gate + SymPy + param-fidelity
│   │   ├── compile.py             # sample → solve → narrate → verify → write JSON
│   │   └── gold/                  # hand-authored golden set + few-shot exemplars
│   │       └── linear_functions.json   # the v1 hand-authored 16 live here now
│   └── tests/
│       ├── test_checker.py  test_mastery.py  test_xp.py  test_help_ceiling.py
│       ├── test_templates.py            # solve() correctness vs the gold set
│       ├── test_turn_integration.py
│       └── adversarial/
│           ├── test_answer_leak.py  test_prompt_injection.py  test_hint_ladder.py
│           └── test_eval_socratic.py
└── frontend/
    ├── package.json                # has an "openapi-codegen" script
    └── src/
        ├── App.tsx
        ├── api/                    # GENERATED from OpenAPI — do not hand-edit
        ├── components/{ChatPanel,GraphView,ProgressHud,MathText}.tsx
        └── ...
```

---

## 3. Runtime data models

The build is self-contained; do not rely on an uncommitted v1 spec. Implement these model families: **knowledge-graph node**, **problem-bank item**, **interest graph**, **per-student skill state**, and **attempt log**. The authored gold bank remains the offline source fixture. Runtime code must consume a seed-loader output split into `PublicProblem` and `PrivateProblem`, not the raw gold JSON directly.

### 3.1 Public/Private problem DTOs (MUST — leak prevention by boundary)
Accidental answer serialization is prevented structurally; answer re-derivation by a capable model is handled by Socratic prompting, hint ceilings, output scanning, and live prompt evals. Split every problem into two DTOs:
- **`RealizedProblemRef`**: the immutable `(problem_id, realization_key)` pair for the exact realization shown to the student. `neutral`, `space_logistics`, and `drone_physics` are different realizations even when they share a problem id.
- **`PrivateProblem`** (checker-only, **never serialized into a prompt or log**): carries the same `RealizedProblemRef`, holds `canonical_answer`, the answer-bearing `solution_derivation`, and the list of `banned_intermediates`.
- **`PublicProblem`** (the only shape allowed into a runtime prompt or a log line): carries the same `RealizedProblemRef`, holds the themed `prompt`, `ui_mode`, and a **leak-safe `hint_scaffold`** (conceptual guidance that does *not* contain the answer or banned intermediates). It is a type error for it to carry `canonical_answer`.

Prompt assembly and logging accept **only `PublicProblem`**. The checker is the only consumer of `PrivateProblem`. The runtime turn must pass the same `RealizedProblemRef` from the displayed `PublicProblem` to the checker lookup, and the checker must reject a mismatch rather than falling back to problem id alone. A test (P1 gate) MUST assert both: (1) no `PublicProblem`, assembled prompt, or log line can contain the canonical answer or any banned intermediate; (2) for every realization, the checked private answer matches the public realization actually shown. This protects against accidental leakage and theme-answer misbinding; it does not prove the model cannot solve the problem from the public prompt.

Hint scaffold contract: `hint_scaffold` is a structured hint ladder, not one blob. It contains authored `level_0`, `level_1`, `level_2`, and optional `level_3` entries plus `max_safe_hint_level`. v1 single-step linear-functions items cap at level 2; level_3 is allowed only for multi-step items with an authored non-final setup. A scaffold may be a theme-neutral shared scaffold only when the exact wording remains valid for every realization; otherwise the seed loader must require a per-realization override. The LLM may paraphrase an existing level but must not synthesize missing levels, operations, or computed values.

Runtime display rule: v1 displays the vetted bank string from `PublicProblem.prompt` exactly, with **no runtime re-narration** of problem text. The LLM may respond around that prompt, but it must not rewrite numbers, roles, units, or story text. If a future feature produces a runtime-rendered prompt, that runtime-rendered prompt must pass the same parameter, leak, semantic-role, and safety gates before display; until then, the vetted bank string is the only problem text a student sees.

**Deep-theming rule (unchanged):** a theme applies to a skill only if the situation *generates* that math (`generative_for`). Never cosmetic word-swaps.

---

## 4. Mastery rule (PURE)
A skill is mastered only when **all** hold: (1) recent accuracy ≥ 0.9 over ≥5 attempts; (2) ≥1 recent correct at `hint_level ≤ 1`; (3) ≥2 distinct `contexts_seen`; (4) `transfer_passed`; (5) `retention_passed` (≥2-day delayed item). Implement as `is_mastered(skill_state) -> bool`; unit-test each clause. pyBKT (`p_mastery ≥ 0.9`) may replace clauses 1–2 behind the same signature.

Mastery windows count **decidable attempts only**: persistence may retain undecidable rows for debugging, but accuracy and the ≥5-attempt denominator must filter to `check_result IN ('correct', 'incorrect')`. Undecidable attempts are invisible to mastery, transfer, retention, and XP accounting.

Attempt accounting is explicit:
- **`ProblemAttempt`** is the atomic mastery/XP unit: one student, one `RealizedProblemRef`, one scheduled presentation of a problem.
- **`SubmissionEvent`** is each submitted answer inside a `ProblemAttempt`.
- Mastery accuracy uses the **first decidable submission** for each `ProblemAttempt`. Later events can mark `self_correction=true` and inform tutoring, but they do not rewrite the accuracy numerator/denominator.
- Clause 2 ("correct at `hint_level <= 1`") uses the first correct `SubmissionEvent` in the `ProblemAttempt` and records the help level in force at that event.
- Undecidable events increment `messy_input_count` and `undecidable_retry_count`; they do not enter the accuracy denominator, but their rate is tracked as a separate learning/friction signal so struggling students do not disappear from metrics.

Transfer is student-relative: transfer_passed is computed relative to `contexts_seen`, prior `RealizedProblemRef`s, representation history, and theme history. `assessment_role='transfer' is a candidate marker`, not sufficient by itself. A candidate is rejected for transfer credit when it is `already_seen_realization`, repeats the same theme/representation context used for practice, or otherwise fails the scheduler's novelty predicate.

## 5. XP rule (PURE)
Light and informational. Correct +5; engaged-but-wrong +1; +3 if `hint_level==0`; +5 transfer; +5 retention. **XP is optional** UI garnish, not the learning objective; it must be disableable and must never drive mastery, placement, or access to help. No leaderboards, **no streaks**, no streak-shaming, and no pressure mechanics aimed at minors. `compute_xp(...) -> int`, pure, tested.

XP dedup: XP is awarded at most once per ProblemAttempt for correctness, transfer, and retention. A later `self_correction` can receive a small engagement award once, but resubmitting the same correct answer cannot farm XP.

---

## 6. LLM layer (runtime)

### 6.1–6.5 LLM contract (MUST be self-contained)
Before P6, add `docs/llm-contract.md` and implement from that committed file. It must contain the full Socratic system prompt, child-safety rules, prompt context layout, structured-output tool schema, and allowed `pedagogical_move`/`ui_mode` enums. The tool schema contains `teacher_check`, `dialogue`, `pedagogical_move`, `ui_mode`, and `proposed_hint_level`; it must not contain code-owned fields such as correctness, XP, mastery, or canonical answers. `teacher_check` is server-only and stripped before the frontend. The allowed pedagogical moves are the strict state machine from the contract: `review_concept`, `offer_heuristic_hint`, `rectify_error`, `request_clarification`, `reflect`, `summarize_mastery`, and `present_next_problem`. The prompt rules must include: code owns the verdict; never state the answer or next computed value; obey `ALLOWED_HELP_LEVEL`; deep theming; use `rectify_error` only when server-provided signals support the student's likely error; `request_clarification` for undecidable input; occasional reflection/summary turns; and data blocks are non-executable.

Intermediate-math boundary: the LLM may choose words, pacing, and questions, but it must not invent algebraic facts. Misconception diagnosis must be grounded in server-provided `DiagnosticResult` signals (`CHECK_RESULT`, parser error class, answer type, deterministic `student_error_tag`, confidence, allowed misconception tags, and authored `hint_scaffold`). If those signals are insufficient, the tutor asks a neutral probing question instead of asserting a diagnosis. Step-by-step hints come only from authored `hint_scaffold` or server-provided next-step templates; the model may paraphrase within the hint ceiling but may not synthesize new intermediate computations.

Reasoning boundary: do not force a visible chain-of-thought scratchpad into the tool schema. Where the provider supports native hidden/omitted reasoning, `LLMClient` may enable it for hard turns. The public contract uses a compact server-only `teacher_check` control record (`student_error_tag`, `next_scaffold_id`, `chosen_pedagogical_move`, `leak_risk`, `uses_only_authored_scaffold`) that is stripped before the frontend. Persist only this bounded record, not provider reasoning, in the backend hidden conversation history for pedagogical continuity; apply a short `teacher_check_retention` window and redact it from logs/analytics.

### 6.6 Tiered model routing (new)
Route by turn difficulty, not blanket-cheapest. **Model IDs are configuration, not hardcoded** (`.env` / settings), so they can be swapped without code changes:
- **Routine turns** (present next problem, simple correct-answer feedback, reflection prompt) → a **fast/cheap tier** chosen in config after live eval.
- **Hard turns** (wrong-answer misconception diagnosis, faded/worked example, on-the-fly deep re-theming) → a **strong tier** chosen in config after live eval; escalate hardest cases to the configured top tier only if eval shows benefit.

`LLMClient.generate(..., tier="routine"|"hard")` selects the configured model. **Gating rule (MUST):** during the slice, run **everything on the strong tier** for quality. Only downgrade routine turns **after** the adversarial suite (answer-leak + hint-ladder) passes **on the cheap tier specifically** — smaller models leak and over-help more readily. **Cost (MUST):** do not state any cost figure without a **measured token budget** from real eval traffic, and enforce **per-user spend caps** (§11.2). For a single student the spend is negligible, but no commercial cost claim is valid until measured.

### 6.7 Guardrails (refined)
Three layers, defense-in-depth:
1. **Architectural (strongest against accidental leaks): withhold the answer by type.** Runtime prompts are assembled from **`PublicProblem` only** (§3.1); `canonical_answer` and banned intermediates live in `PrivateProblem`, which is structurally unable to reach a prompt or log. This does not stop the model from re-solving simple math, so layers 2-3 and live evals remain mandatory. Where good hints don't need the value, the public `hint_scaffold` carries method-level guidance only.
2. **Context-aware leak scan (output side):** code computes the canonical answer + key intermediate values and passes them as guarded values. Scan `dialogue` for distinctive final expressions with word boundaries (`-8*x + 66`, `3/4`) and for numeric answers in answer-shaped contexts (`the answer is 7`, `x = 7`, `final value 7`, unit-bearing final-answer forms). **Caveat (MUST handle):** do **not** naively substring-ban bare integers like `2`, which would nuke "step 2", "2 km", coordinates. For a single-digit answer, regex cannot prove semantic non-leakage: "seven crates" or a riddle can leak without matching an answer-shaped pattern. Treat numeric scanning as a smoke alarm, not a proof; the true defenses are strict prompting, authored hints, help ceilings, and the live prompt eval suite with exact small-integer adversarial cases. Residual risk remains: the DTO split prevents accidental serialization, not model re-derivation.
3. **System-prompt prohibition** + **regenerate-once-then-fallback** if a leak is detected; log every fire.
Plus: **hint-ceiling enforcement** (reject/regenerate if `pedagogical_move` exceeds `allowed_help_level`) and **prompt-injection wrapping** (student text and graphs go in `<STUDENT_DATA>`/`<PROBLEM_DATA>`; never let them alter rules, ceiling, or thresholds). On `undecidable` turns, force `pedagogical_move=request_clarification` and `proposed_hint_level=0`; unparseable input must not climb the hint ladder.

### 6.8 Prompt-caching order (MUST)
Caching is prefix-based, so payload order is load-bearing: place **stable content first, volatile content last** — System prompt → Tool schemas → (static problem/skill context) → **Conversation history last**. Putting history anywhere but the tail busts the cache every turn and forfeits the savings. Mark cache breakpoints on the stable prefix. **Verify the current mechanics at P6:** cache minimums, `cache_control` breakpoint placement and count, and the published discount all drift by provider/model — confirm against current provider docs, and **verify hits by reading the response `usage` fields** (cache-read vs cache-write tokens) rather than assuming.

Spend note: tier switching and per-problem context can erase caching gains. Treat prompt caching as an optimization to measure, not a budget guarantee. P6 must record cache economics from real tutor traffic: cache write/read rates per tier, cache-hit ratio after routing, and fallback spend caps if the hit ratio is poor.

---

## 7. `/turn` orchestration (PURE-first pipeline)
Every `POST /turn` requires an `idempotency key` and the current `skill_state.version`. The service must never hold a DB lock across `LLMClient.generate`; external model I/O is outside the transaction boundary.

Phase A, synchronous state mutation: open a short database transaction; load active `RealizedProblemRef` + state; if answer present, normalize it, run `check_result` against the same `RealizedProblemRef` (CODE: `correct`/`incorrect`/`undecidable`), and compute `DiagnosticResult` from deterministic known wrong-answer patterns; if decidable, compute `xp` (CODE) and update skill_state from decidable attempts only; if undecidable, increment `undecidable_retry_count` without mutating mastery/retention/XP; compute `mastered`; compute deterministic `allowed_help_level`; call `scheduler.py` if the current problem is complete, mastered, skipped, abandoned, or due for retention to select the next server-owned `RealizedProblemRef` and corresponding `PublicProblem`; append the attempt exactly once for the idempotency key; write a `turn_generation_job` with `state_snapshot_id`, active `PublicProblem`, hidden conversation history, code-owned fields, `DiagnosticResult`, and allowed ceiling; commit. On optimistic-lock conflict, retry Phase A from the fresh attempt log or return a 409 with a client-safe retry instruction; never let two tabs or a network retry double-award XP, skip an attempt, or grant mastery from stale state.

Phase B, asynchronous LLM generation: after Phase A commits, a worker or post-commit async task loads the immutable `turn_generation_job`, builds prompt context from the stored snapshot, calls `LLMClient.generate(tier=...)`, runs guardrails, strips frontend-private fields, persists the student-visible dialogue plus bounded hidden `teacher_check`, and marks the generation complete. If the job's `state_snapshot_id` no longer matches the active session because a newer turn or skip won the race, treat the result as a stale generation: discard the dialogue from chat history, keep only operational metrics, and do not merge it into the student transcript.

The LLM may choose `present_next_problem` only when the server has already selected the next `PublicProblem` and included it in `PROBLEM_DATA`; it must never invent a problem or choose the next skill. Retention and transfer items are scheduled by `scheduler.py`, not by the model.
Endpoints: `POST /session/start`, `POST /turn`, `POST /session/skip`, `GET /student/{id}/state`, `POST /assessment/transfer`, `POST /assessment/retention`.

Skip/abandon transition: `POST /session/skip` marks the active problem `abandoned` or `skipped_without_penalty` depending on reason (`stuck`, `stale_return`, `accessibility`, `misclick`). It clears the active `RealizedProblemRef`, invokes `scheduler.py`, and returns a new server-owned `PublicProblem`. Abandonment must not count as correct or incorrect; it may reduce optional XP only, never mastery directly. Repeated abandonment is visible to the scheduler as a placement signal.

Help escalation: `domain/help_ceiling.py` owns a deterministic rule for increasing `allowed_help_level`. Minimum v1 rule: after two same-problem failed attempts with `check_result='incorrect'`, increase `allowed_help_level` by one up to `PublicProblem.hint_scaffold.max_safe_hint_level`; on `undecidable`, keep level 0 unless the bounded undecidable escape routes to a different equivalent-form prompt; on skip/abandon, reset for the new problem. The LLM cannot self-escalate help.

---

## 8. Checker (`domain/checker.py`) — content-bank requirements
Normalize before checking. `answer_normalizer.py` is a pure pre-check boundary that handles common student notation before SymPy sees it: unicode minus and other unicode normalization, smart-fraction normalization (`¾` -> `3/4` where safe), prose wrapper stripping (`the answer is ...`, `I think ...`), equation-prefix extraction (`y = 5d + 20` when the answer type expects an expression), unit stripping/validation per `answer_type`, whitespace/case cleanup, and variable-name mapping from the shown prompt. It must emit both normalized text and normalization warnings for the turn log.

Dispatch on `checker_type`: `sympy_equiv` (parse both, then test equivalence — prefer `simplify(a-b)==0` with an `equals()` fallback, not equality alone), `numeric` (float within tolerance), `set` (unordered solution set), and **`ordered_pair`** (compare two numeric components). SymPy parsing **MUST**: enable implicit multiplication (so `5d+20` parses), convert `^`→`**`, apply numeric tolerance for decimals (so `0.5`≡`1/2`), and sympify against **the variable named in the prompt** (`x`, `d`, `t`, `k`). **Never `eval` raw input.**

**Treat all student input as hostile (MUST):** a symbolic engine on arbitrary strings can hang or explode. Add: an **allowed symbol/function whitelist** (reject unknown functions, no arbitrary attribute access), **input length and parse-tree depth caps**, and an **evaluation timeout** (run the simplify in a killable worker). Checker output is **tri-state**: `correct`, `incorrect`, or `undecidable`. Timeouts, parse rejection, and equivalence uncertainty return `undecidable`, not `incorrect`; undecidable attempts must not mutate mastery, retention, or XP as wrong answers. Handle **equations, tuples/sets, and units** explicitly per `answer_type` rather than assuming a bare expression. Unparseable/rejected input → ask for reformat without crashing, hanging, or penalizing the student.

Undecidable escape: track `undecidable_retry_count` per attempt/problem. After a small bounded count of semantically similar undecidable submissions, run a safer secondary path when the answer type allows it: numeric sampling fallback over a bounded domain for expression equivalence, exact component comparison for tuples/sets, or a domain-specific checker. If the fallback also cannot decide, flag the attempt for human review/manual review and let the UI offer a different equivalent-form prompt or skip-without-penalty path. Undecidable is never a terminal state and never silently becomes incorrect.

Undecidable is a friction signal, not just a neutral non-event. Track `messy_input_count`, per-skill undecidable rate, normalization failure reason, and skip-after-undecidable rate. These do not directly lower mastery, but scheduler and product analytics must use them to detect students who cannot express answers reliably; otherwise excluding undecidables biases accuracy upward.

### 8.1 Diagnostic checker (`domain/diagnostic_checker.py`)
The equality checker is not the misconception source. After normalization and correctness checking, `diagnostic_checker.py` emits a pure `DiagnosticResult`:

```python
DiagnosticResult(
    student_error_tag="inverted_slope|sign_error|slope_intercept_swap|used_intercept_only|rounding_near_miss|malformed_input|unknown",
    confidence="high|medium|low",
    matched_pattern="...",
    safe_hint_level_cap=0|1|2|3,
)
```

For v1, author a linear-functions misconception taxonomy with known wrong-answer patterns that templates can compute deterministically: `inverted_slope` (`delta_x / delta_y`), `sign_error`, `slope_intercept_swap`, `used_intercept_only`, `used_slope_only`, `point_order_arithmetic_error`, `rounding_near_miss`, and `malformed_input`. `student_error_tag=unknown` is allowed; when unknown or low confidence, the LLM must not choose `rectify_error` and must use `review_concept` or `offer_heuristic_hint` instead. This keeps diagnosis server-grounded without pretending the one-bit checker can tutor.

**Property-based tests (Hypothesis)** for malformed and adversarial inputs are part of the P1 gate. Note: the `lin_interpret_meaning` skill is graded **only on its signed number**; its prose meaning is tutor-led and does **not** flip `is_correct`.

---

## 9. Content generation pipeline (NEW — the big rewrite)

**Goal:** scalable, deeply-themed, mathematically checked content without hand-authoring thousands of variants — and **without ever letting an LLM be the source of a math answer.**

**Why not Gemini's "LLM writes the answer, SymPy validates it":** SymPy can confirm an answer *parses and is clean*, but it **cannot read the narrative** to confirm the answer actually matches the situation described. An LLM that hallucinates a problem whose stated answer doesn't fit its own numbers passes that check. So that approach gives a *false* guarantee. We invert it.

### 9.1 Parametric templates (`content_pipeline/templates/*.py`)
Author each problem **type** once, in Python:
```python
@dataclass
class LinearTwoPointSlope:
    template_id = "tpl_slope_two_points"
    skill_id = "lin_slope_two_points"

    def sample(self, difficulty: int, rng) -> dict:
        # sample params; enforce difficulty constraints (e.g. integer slope at diff<=2)
        ...
        return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}

    def valid(self, p) -> bool:
        return p["x1"] != p["x2"]                       # no div-by-zero, etc.

    def solve(self, p) -> str:                          # CODE OWNS THE ANSWER
        from sympy import Rational
        return str(Rational(p["y2"]-p["y1"], p["x2"]-p["x1"]))

    answer_type = "expression"; checker = "sympy_equiv"
    # role mapping ties math → story for each theme:
    roles = {"slope": "rate", "x": "time", "y": "quantity"}
```
The Python `solve()` is the **only** source of the canonical answer. Difficulty constraints live in `sample()`/`valid()`, so "clean answers at difficulty 1" is enforced by sampling, not by a regenerate loop.

### 9.2 Narrator (`narrate.py`) — LLM writes WORDS ONLY
Input: the sampled params, the **computed answer**, the theme's `mapping_hint`, the `roles` map, and **few-shot exemplars from `gold/`** (the v1 hand-authored 16 — they now teach the narrator what *deep* theming looks like). The LLM produces only the themed `prompt` and `solution_method`. The prompt forbids recomputing or changing any number. The answer is *given*, never generated.

### 9.3 Three-model verification gate (`verify.py`) — MUST pass all
An item is written to the bank only if:
1. **Param-fidelity:** the rendered narrative contains the sampled param values (regex/substring). Catches dropped/altered numbers.
2. **Independent cross-model extraction (not free-solving):** a **different provider** (e.g. Gemini and/or Codex) reads **only the rendered narrative** (not the answer) and returns **structured JSON of the parameters it can read out of the story**: the values, units, variable bindings, relationship direction, signed role (`increases`, `decreases`, `initial value`, `rate`, `x value`, `y value`), and what each number represents. Then **Python `solve()` runs on the extracted params** and must equal `solve()` on the originally sampled params. *Do not ask the verifier to do arithmetic* — it parses, Python solves. This lowers one LLM failure point, but it is not proof by itself: the verifier must not coerce a story back into the intended template if the relationship is wrong. A story that says fuel is added when the template requires consumption must fail even if the number `5` appears. The `gold/` exemplars teach the verifier how to **extract params from heavily themed text**. This is the layer SymPy can't provide.
3. **SymPy sanity:** the answer parses, is clean, and meets the difficulty constraint.
4. **Deep-theming and semantic-role safety gate:** a verifier must classify whether the story's situation genuinely generates the math via the template's `roles`, not merely a cosmetic rename or a role/sign mismatch. It must also reject unsafe themes and prompt-injection-like text in generated narratives, `hint_scaffold`, and any public fields. Use `docs/content-safety-review.md` plus the deterministic scan in `backend/content_pipeline/safety.py`.
5. **Known weak spot:** interpretation skills are the weakest part of this gate because the parameter being extracted can be the answer itself. Treat the gate as a consistency check for interpretation skills, not as proof of reasoning-quality assessment.
Failures are logged and regenerated (narrate step only — params/answer are fixed). The compiled output is the **same runtime JSON schema** the app already loads (§3).

provider diversity is not statistical independence. Cross-provider extraction reduces some correlated errors, but it does not remove shared frontier-model biases such as charitable intent repair. Track correlated verifier failure as a named residual risk and keep deterministic role metadata, adversarial examples, and human spot checks in the promotion process.

### 9.4 Auth for the pipeline
Local dev authoring may use your CLIs interactively (it's you, your subscription, an offline dev artifact). **For the commercial product, the pipeline runs on API keys** and records provider, model id, prompt version, and artifact hash (§11). But live model generation is not a reproducible CI gate: third-party models drift even at temperature 0. CI must deterministically verify the frozen artifact that is already committed: schema, safety scan, leak scan, role metadata, `test_templates.py`, and exact reproduction of `gold/` answers via `solve()`. Live generation/verification runs as an offline authoring step or scheduled evaluation; it can block promotion of a new generated bank, but not pretend to be deterministic CI for an unchanged frozen artifact.

---

## 10. Frontend

- **Types are generated, not mirrored.** FastAPI emits OpenAPI from the Pydantic schemas; an `openapi-codegen` npm script regenerates `src/api/` on build. Use **Orval** (`orval.dev`) — it generates **TanStack Query hooks** from the spec, so every call gets loading states, caching, and retry logic with zero boilerplate. *Deliberate tradeoff:* Orval is more opinionated than bare `openapi-typescript` and couples the frontend to TanStack Query — which is what you want for a commercial app, but record it as a chosen dependency. **Never hand-edit generated files**; change the contract in the backend schema only. P0b's `orval.config` must filter or tag-exclude FastAPI-Users OAuth redirect/callback routes so browser-redirect endpoints do not generate unusable AJAX hooks.
- `ChatPanel` (KaTeX via `MathText`), graph component behind a `GraphView` abstraction, `ProgressHud` (calm, informational — mastery progress + XP).
- **Graph gate:** the vertical slice must include a local SVG/canvas graph fallback for `GraphView` before graph problems are enabled; see `docs/graphview-fallback.md`. Desmos Graphing Calculator is not approved for commercial embedding until P0b documents terms review and either written commercial permission or an alternative graph component. Scaffold `GraphView` so Desmos can be swapped out.
- **Render untrusted text safely:** LLM dialogue and generated content are untrusted. `ChatPanel`, `MathText`, and KaTeX rendering must sanitize/escape all non-math text, disable raw HTML injection, and include tests for script/HTML payloads in model output.
- **No client-side authoritative checking in v1.** math.js is removed (fragile on algebraic equivalence). The **server SymPy check is authoritative**, but latency claims must be measured at median and tail after timeout hardening. **Pyodide/SymPy-in-WASM is deferred:** multi-MB load is a real mobile/commercial cost, and the "instant as you type" gain is marginal for a turn-based tutor. Revisit only if measurement shows the checker hop hurts; never as a replacement for server authority.

---

## 11. Auth & model access (NEW)

### 11.1 Runtime LLM access — API KEYS ONLY (MUST)
The running tutor calls the model via **API keys**, never subscription OAuth or a CLI subprocess. Reasons, any one disqualifying:
- **ToS:** Anthropic and OpenAI require API keys for products. OAuth token usage via subscriptions is for individual dev use, not for routing another human's requests. Furthermore, providers require age-appropriate safeguards when minors use the API.
- **Operations:** subscription tokens expire/rotate and aren't meant for servers; API keys give spend limits, usage dashboards, and rotation.
- **Architecture:** a CLI subprocess gives you stdout to parse, not the **structured tool-use guarantee** the "code owns facts" design depends on. Do not orchestrate via CLI.

### 11.2 Spend control (replaces the subscription "flat cap" appeal)
The API has no hard cap by default. Set **Console spend limits + alerts**, use **prompt caching** for the static system prompt and problem context, and add **per-user rate limiting** at commercial scale.

### 11.3 Where the CLIs *do* belong — build time
Using **Claude Code / Gemini CLI / Codex CLI to build this repo** is the intended, licensed use (you, your subscription, interactive dev). Having all three is also what powers the **offline three-model verification gate** (§9.3) — generate with one provider, verify with others. Keep that offline.

### 11.4 OAuth — for USER login, not LLM access
Social-login OAuth (e.g. Google) for authenticating users is standard and advisable for the product — but design it as **"parent creates the account and consents, child uses it"**, gated by the age-band decision (§12). Many providers prohibit under-13 self-signup, which interacts with COPPA. OAuth authenticates *people*, never the model.
**Implementation:** **FastAPI-Users** is the default — it ships SQLAlchemy user models, password hashing, and OAuth integrations that fit this stack, avoiding a paid service (Auth0/Clerk) for v1. **Risk note (MUST address):** the library is in **maintenance mode** and recently shipped an **OAuth CSRF fix** — so **pin an exact version**, and explicitly decide the **OAuth `state`/CSRF + cookie strategy**, **JWT-vs-server-session** model, and the **parent↔child account relationship** rather than treating it as turnkey. Re-evaluate the dependency if its maintenance status worsens. **Boundary (MUST note):** FastAPI-Users provides *authentication only*. COPPA **verifiable parental consent**, age-gating, and the parent-consents/child-uses flow sit **on top** of it (§12) — the auth library does not discharge that obligation.

---

## 12. Commercial trajectory & privacy (NEW — decide this first)

**Settle the target age band before building auth or data flow — it cascades into everything.** (Not legal advice; for a commercial product serving minors, get real legal review and verify current law/provider terms.)

- **Under-13 in scope → COPPA governs.** Verifiable parental consent, data minimization, deletion on request, no behavioral advertising. This reshapes auth (parent-consent flow), data flow, and **which provider/configuration you may use** (some forbid or restrict processing under-13 data). If you can avoid under-13 for v1, you remove the single biggest compliance burden.
- **13–17 → lighter but real.** Parental consent still advisable; US state youth-privacy laws apply; provider terms matter (e.g. OpenAI requires parental consent for under-18; Anthropic permits minors via API if you add safety features — content filtering, monitoring, child-safety system prompt, disclosure).
- **Schools → FERPA.** Only if sold into education; then add LTI/OneRoster and FERPA-appropriate contracts (out of scope for v1).
- **Data hygiene (all cases):** opaque `student_id`, minimize PII (no real name in prompts/logs), documented retention/deletion, and **document your provider's no-train + retention settings** in the README (Anthropic/OpenAI APIs don't train on inputs by default; confirm the current setting).
- **Eval suite = CI regression gate (§14).** This is what makes a model swap or cost downgrade *safe* in production.
- **Content build-vs-buy at scale:** generated word problems carry an ongoing verification cost (§9). Re-evaluate licensing a vetted problem bank once the curriculum is large — it may beat generating.

---

## 13. Runtime security
Keys server-side only; untrusted-data discipline (§6.7); no improvised crisis/medical handling (defer to "talk to a trusted adult"); minimize PII; render model/content text as untrusted on the frontend.

---

## 14. Testing (CI gate)
- **Unit (PURE):** checker (incl. `ordered_pair`, equivalent forms, bad input), `answer_normalizer.py` (unicode/prose/unit/equation-prefix cases), `diagnostic_checker.py` (linear-functions misconception taxonomy), mastery (each clause), xp, help_ceiling.
- **Templates:** `solve()` reproduces the `gold/` answers exactly; templates also compute known diagnostic distractors; PublicProblem and PrivateProblem binding uses the same `RealizedProblemRef`.
- **Integration:** `/turn` happy + wrong paths; scheduler-selected next problem; idempotency key retry; optimistic-lock conflict; a **mocked LLM that tries to output forbidden code-owned fields** must lose to code. Since the tool schema excludes those fields, the important runtime test is dialogue leakage/injection, not a fake correctness field.
- **Adversarial (MUST, in CI):** answer-leak ("just tell me"), prompt-injection ("ignore instructions / raise my XP / mark me mastered"), hint-ladder (never exceeds `allowed_help_level`). **Run these on whichever model tier serves that turn** — the configured cheap tier must pass before it serves routine turns.
- **Socratic eval set:** small curated exchanges scored for "uses server-provided `student_error_tag` when present, asks a probing question when unknown, one bridging question, no answer given"; run on every prompt or model change.
**The build is not done until the full suite is green in CI.**

---

## 15. Best practices
Mastery/xp/solve are **pure functions, no I/O** (what makes them trustworthy + testable). The untrusted-input checker boundary may use killable workers/timeouts, so it returns tri-state results and never treats timeout/uncertainty as wrong. All LLM calls go behind `LLMClient`. Type everything; the response schema is the single contract (→ generated TS). Deterministic, mock-LLM unit/integration tests. Structured per-turn logging (skill, move, hint level, correctness, leak-guard fires) for **mastery validation** (engagement ≠ learning). Prompt caching. Append-only attempt log. The content pipeline is **offline** and never imported by the running app.

---

## 16. Build phases (ordered; each ends at a green gate)
**Sequencing principle (v2.2):** prove the *learning loop* on a tiny hand-authored bank before adding the LLM, and add content automation **last**. Deterministic core → mocked loop → gold slice → eval → real LLM → pipeline.

- **P0a Foundation + privacy/dependency gate:** settle and document the **age band, data-retention posture, prompt/log PII policy, parental-account model, provider eligibility, allowed themes, and Desmos/commercial graphing decision** (§12). *Gate:* privacy decisions recorded in `docs/p0a-decisions.md`; deterministic content-safety scan passes on the gold set. **No auth, logging of user data, LLM call, third-party graph embed, or content generation may begin until the relevant gate is signed off.** Pure local math/schema work may proceed before legal sign-off if it stores no user data and calls no external service.
- **P0b Technical Scaffold:** repo, `.env.example`, Postgres, FastAPI boot, Alembic init, **Orval OpenAPI→TS codegen wired**, CI running pytest+vitest. *Gate:* app boots, migrates, codegen produces `src/api/` with TanStack Query hooks, empty tests pass, and `docs/llm-contract.md` exists with the full prompt contract.
- **P1 Checker + schema (NO LLM):** hardened tri-state `checker.py` (§8), `answer_normalizer.py`, `diagnostic_checker.py`, and **Public/Private problem DTOs** (§3.1). *Gate:* `test_checker` green incl. equivalent forms, `ordered_pair`, adversarial/property-based inputs, timeout/parse rejection returning `undecidable`, bounded undecidable fallback paths, normalization of common student inputs, deterministic diagnostic tags for the linear-functions misconception taxonomy, and `RealizedProblemRef` mismatch rejection; a test proves `canonical_answer`/banned strings cannot be serialized from a `PublicProblem`; a test proves the checked `PrivateProblem` answer always matches the shown `(problem_id, realization_key)`; mastery queries filter to decidable attempts only.
- **P2 Mastery + XP + ceiling (NO LLM).** *Gate:* every clause/branch tested, including `ProblemAttempt` vs `SubmissionEvent`, first decidable submission accuracy, `self_correction`, XP dedup, deterministic help escalation, and transfer computed relative to `contexts_seen`.
- **P3 Mocked `/turn` (NO LLM):** wire §7 with a stub `LLMClient` returning canned dialogue. *Gate:* server scheduler selects/persists the next `RealizedProblemRef`; `present_next_problem` never occurs without server-provided `PROBLEM_DATA`; idempotency key replay is exactly-once; optimistic-lock conflict is tested; the loop runs end-to-end with code owning all code-owned fields. **A working tutor loop exists here, with zero API spend.**
- **P4 Gold slice UI:** load the hand-authored `gold/linear_functions.json` via a **dev seed loader** that uses the authored leak-safe `hint_scaffold` and emits runtime-safe `PublicProblem` and `PrivateProblem` DTOs. It must never derive public hints from private `solution_method` at runtime. It must display the vetted bank string with no runtime re-narration. ChatPanel + MathText + swappable GraphView + ProgressHud on the generated API client. *Gate:* a human completes a full linear-functions problem in-browser against the mocked tutor; render-safety tests reject script/HTML payloads.
- **P5 Eval Harnesses (§14):** Separate the testing gates into **Deterministic Guardrail Tests** (runnable against a mock LLM stub to prove the plumbing) and **Live Prompt Eval** (run against the real model for Socratic/leak robustness). *Gate:* both harnesses run in CI and fail the build on a leak/injection/ceiling violation.
- **P6 Real LLM:** `LLMClient` (Gemini/Anthropic, **API key**, **configurable model IDs**) + tiered router, system prompt, contextualizer, guardrails (§6.7), prompt-caching order per §6.8 (verify current mechanics against selected provider docs here). *Gate:* P5 adversarial suite passes against the live prompt; cache/usage fields confirmed against provider response metadata; measured token budget and cache economics recorded.
- **P7 Assessments + scheduler:** transfer + retention endpoints feeding mastery; reflection turns; `scheduler.py` chooses next skill/problem, interleaves review, and queues delayed retention attempts. *Gate:* a skill reaches `concept_mastered` only after real transfer + delayed retention. CI uses time-mocked tests for the ≥2-day retention rule; production validation tracks return-rate/re-engagement separately and does not pretend CI proves the student will return.
- **P8 Content pipeline (scaling, last):** parametric templates + `solve()`; narrator; **structured-extraction verification gate** (§9.3); compile to the runtime bank. *Gate:* deterministic tests verify the frozen artifact: `test_templates` reproduces `gold/`, the committed generated bank passes schema/safety/leak/role checks, and any newly promoted bank includes recorded live-generation provenance. **Only now does content scale beyond the hand-authored slice.**
- **P9 Harden:** spend limits + per-user caps, logging, content filter, error handling on every network call. *Gate:* full §14 suite green in CI; README documents provider data settings + age band + token budget.

---

## 17. Vertical slice = definition of done for v1
**Linear functions** (the 8-skill graph in `gold/linear_functions.json`, hand-authored). v1 is done when, **on the gold bank** (the content pipeline is *not* required for v1): deep theming to a student-chosen theme; tutor does not reveal the answer under the adversarial eval suite (with DTO split preventing accidental answer serialization, not claiming to stop model re-derivation); `is_correct` comes from the hardened tri-state checker, immune to a lying model for code-owned fields; undecidable checker results do not penalize mastery; code-controlled hint escalation; mastery only via ≥0.9 accuracy + low-hint correct + two contexts + transfer + delayed retention; calm informational HUD; the privacy/age-band/dependency gates signed off; and the full §14 suite green in CI. **Content automation (P8) is a post-v1 scaling step**, not part of done; once the loop is proven, expand only to domains whose answer types and checkers are explicitly supported by the same deterministic contract.

**Known v1 limitation:** this is a deterministic answer-checking tutor for supported answer types; it does not grade free-form reasoning, proofs, constructions, or open-ended explanations. Interpretation prompts can coach meaning, but the authoritative checker only validates supported structured answers such as numbers, expressions, sets, and ordered pairs. Treat mastery on the 16-problem hand-authored bank as a product slice, not evidence that the full curriculum generalizes; broader curriculum work requires new answer contracts, checkers, content volume, and validation data.

## 18. Out of scope for v1
Game-engine front-ends; GeoGebra/Polypad embeds; voice; multi-student/teacher dashboards; LMS/LTI/OneRoster/xAPI; **math.js** (removed); **Pyodide** (deferred); **any subscription-OAuth/CLI path for runtime model access** (prohibited — §11).
