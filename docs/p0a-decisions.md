# Phase 0a: Core Governance & Privacy Decisions

Before writing any application code, these foundational governance decisions are locked in to ensure a safe, compliant, and commercially viable architecture.

## 1. Age Band & Consent Model
**Target Age:** 13–17 (Minors).
- **Under-13 is explicitly out of scope for v1** to avoid COPPA's strictest data isolation and verifiable-parental-consent engineering burdens.
- **Parent/Child Account Model:** The system uses a "Parent creates, Child uses" model. Parents sign up via OAuth, agree to the ToS/Privacy Policy on behalf of the minor, and create a linked sub-profile for the student.

## 2. Content Safety & Allowed Themes
**Restriction:** No violence, weapons, warfare, adult themes, or weapon-adjacent framing. OpenAI and Anthropic require age-appropriate safeguards for under-18 users.
- **Original Themes Replaced:** The previous wartime and weapon-physics content has been refactored into **Space Colony Logistics** and **Drone / Flight Motion**.
- **Gold-Set Gate:** `backend/content_pipeline/gold/linear_functions.json` must remain free of the banned lexicon listed in `backend/content_pipeline/safety.py`: wartime terms, weapon terms, firing-range language, and military operational framing. This is a deterministic CI check, not a manual promise.
- **Enforcement:** The offline Content Pipeline must reject violent/unsafe generative themes and must run both a banned-term scan and a semantic review prompt before adding a new theme to the gold set.

## 3. Data Retention & Redaction
- **LLM Provider Hygiene:** We use API keys exclusively. Current provider docs state that OpenAI API data is not used for training by default unless opted in, and Anthropic documents Zero Data Retention options for stricter API retention. P0b must pin the exact provider, account controls, retention mode, and source URL/date before any live LLM call.
- **Provider Sources to Re-check at P6:** OpenAI data controls (`https://platform.openai.com/docs/guides/your-data`), OpenAI under-18 API guidance (`https://platform.openai.com/docs/guides/safety-checks/under-18-api-guidance`), Anthropic API data retention (`https://platform.claude.com/docs/en/manage-claude/api-and-data-retention`), and Anthropic child-safety/usage-policy guidance.
- **Pinned Source File:** `docs/provider-policy-sources.md` records source URLs, checked dates, current facts, and the P6 re-check requirement.
- **Log Redaction:** Student inputs are scrubbed of PII (emails, phone numbers, real names) before being written to the database or sent to the LLM.
- **Opaque Identifiers:** The runtime LLM receives an opaque `student_id` (e.g., `student_abc123`), never a real name.
- **Retention:** Attempt logs are retained for mastery tracking but can be purged upon parent request.

## 4. The `PublicProblem` vs `PrivateProblem` Boundary
To prevent accidental answer serialization, the runtime system strictly separates DTOs:
- **`PrivateProblem`:** Lives only in the server's backend DB/memory. Contains `canonical_answer` and the full `solution_method` (with final math).
- **`PublicProblem`:** What the LLM receives in its prompt context. The `canonical_answer` is completely stripped. The `solution_method` is heavily redacted/sanitized (during the offline pipeline export step) so it explains the *steps* without revealing the final numeric answer or the immediate next computed value.
- **Threat Model Limit:** This boundary is defense-in-depth, not a mathematical guarantee. The model can re-derive simple answers from the public prompt, so runtime still requires Socratic prompting, output leak scanning, hint-ceiling enforcement, and live prompt evals.

## 5. Third-Party Frontend Dependencies
- **Desmos:** Desmos Graphing Calculator is not approved for commercial embedding until terms are reviewed and a commercial permission path is documented. Current Desmos terms (`https://www.desmos.com/terms`, last checked 2026-05-31) restrict Desmos Tools to personal non-commercial or school academic use unless there is a separate written commercial agreement. P0b may scaffold a local graph component abstraction, but must not hardwire a commercial dependence on Desmos without this decision.
- **Local Graph Fallback:** `docs/graphview-fallback.md` is the v1 requirement for graph rendering while Desmos remains gated.
