# Math Resource Ingestion Plan

Date: 2026-05-31

## Goal

Build a licensed, auditable ingestion path for external math resources without weakening the tutor's existing invariant: deterministic code owns facts, runtime prompts only receive public-safe problem data, and every promoted item can be traced back to source, license, template, verifier result, and attribution.

Current deployment assumption: the product starts as **free and noncommercial**. The pipeline should therefore allow noncommercial Creative Commons material when its obligations can be satisfied, while preserving enough metadata to filter or replace that material if a future commercial mode is introduced. This is a database/content-pipeline plan, not a proposal to scrape proprietary tutoring platforms.

## Resource List

| Resource | Direct querying/use | License posture | Ingestion status | Intended use |
|---|---|---|---|---|
| Illustrative Mathematics K-12 Math 2019-2021 | Web/OER access through official OER distributors | CC BY 4.0 for the listed 2019-2021 K-12 Math curricula; trademarks excluded | Tier 1 | Highest-priority curriculum alignment source for skills, lesson goals, task shapes, and attribution-backed problem inspiration |
| Open Up Resources 6-8 Math first edition / IM-derived editions | Web access; edition-specific URLs | Some editions are CC BY; newer Open Up / IM variants may be CC BY-NC or otherwise restricted | Tier 1 after per-edition license capture | Middle-school linear functions, functions, ratios, expressions, equations; ingest CC BY and compatible NC editions in noncommercial mode |
| OER Commons | Discovery hub, not a single curriculum | Per-item license varies: public domain, CC BY, CC BY-SA, CC BY-NC, restricted, or unclear | Tier 1 discovery, item-by-item | Find candidate tasks and lesson materials; ingest items whose license gate passes for noncommercial deployment |
| OpenStax | Download/web textbook access | OpenStax now states textbooks are CC BY-NC-SA; commercial use needs permission | Tier 1 for noncommercial, permission-gated for commercial | Explanations, topic sequencing, worked-example inspiration, and source-backed remediation links |
| CK-12 | Web platform; no assumed open commercial API | CK-12 Curriculum Materials License / educational-use constraints | Tier 2 after license review | Reference or limited reuse if the specific license permits free noncommercial educational use |
| Desmos | Official embeddable calculator API | API/tool use, not a problem-bank license | Integration only | Graph renderer candidate, not a content source |
| GeoGebra | Materials/platform access | Software/materials generally non-commercial unless a commercial license is arranged; individual materials vary | Tier 2 for noncommercial embeds/materials, item-by-item | Interactive applet inspiration or approved noncommercial embeds only |
| Wolfram Alpha | Official computation API | Paid/commercial API; attribution required; API output generally cannot be cached | Computation/eval only | External solver/eval reference; never store generated content as bank material |
| Mathigon | GitHub source for textbooks is visible | Repository says content/source assets are copyright Mathigon / all rights reserved unless otherwise licensed | Reference only | Product and interaction inspiration; do not ingest content without permission |
| Khan Academy | No public API; internal GraphQL is not approved for arbitrary external use | Licensed educational content is personal/non-commercial unless alternate license or written permission applies | Supplemental link/video recommendations only | Link out or embed approved public videos with attribution/free-access framing; do not query private APIs or mirror the content bank |
| IXL | No public content API for our use | Proprietary | Excluded | Do not ingest, scrape, or mirror |
| DeltaMath | LMS/account integrations on paid tiers, not open content API | Proprietary | Excluded | Do not ingest, scrape, or mirror |
| ALEKS / McGraw Hill | LMS integrations, not open content API | Proprietary | Excluded | Do not ingest, scrape, or mirror |
| Carnegie Learning MATHia | Commercial platform | Proprietary | Excluded | Do not ingest, scrape, or mirror |
| Brilliant | Proprietary content; redistribution/adaptation restricted without written permission | Proprietary | Excluded | Do not ingest, scrape, or mirror |
| Art of Problem Solving / Beast Academy | Proprietary curriculum | Proprietary | Excluded | Do not ingest, scrape, or mirror |

## License Gate

Every candidate resource enters ingestion as `blocked` until a captured license record says otherwise. The importer should support these statuses:

- `commercial_ok`: public domain, CC0, CC BY 4.0, or another license reviewed as commercial-compatible.
- `commercial_ok_sharealike`: CC BY-SA or similar; allowed only if we are willing to satisfy share-alike obligations for the adapted material.
- `noncommercial_only`: CC BY-NC, CC BY-NC-SA, OpenStax current default, many school/OER variants; usable only in noncommercial deployments or with written permission.
- `permission_required`: ambiguous terms, trademark constraints, platform-specific license, or unclear provenance.
- `excluded`: proprietary platforms and any source whose terms forbid copying, adaptation, automated access, or commercial reuse.

Deployment modes:

- `free_noncommercial` (current): allow `commercial_ok`, `commercial_ok_sharealike`, and `noncommercial_only` when attribution, free-access, and share-alike obligations are satisfied. `permission_required` and `excluded` stay blocked.
- `commercial`: allow only `commercial_ok`, approved `commercial_ok_sharealike`, or items with explicit written permission. `noncommercial_only` stays blocked.

The pipeline must preserve license metadata per source item, not per provider. OER Commons, GeoGebra, and Open Up Resources can contain mixed-license material; a provider-level allowlist is not enough.

## Database Model

Add content tables in a separate content schema or prefix so runtime session state stays isolated from authoring/provenance data.

### Source and License Tables

- `content_source`
  - `id`
  - `provider` such as `illustrative_mathematics`, `open_up_resources`, `openstax`, `oer_commons`
  - `title`
  - `source_url`
  - `publisher`
  - `retrieved_at`
  - `retrieval_method` such as `manual_download`, `official_api`, `web_export`, `git_clone`
  - `source_sha256`

- `content_license`
  - `id`
  - `source_id`
  - `license_name`
  - `license_url`
  - `license_status`
  - `attribution_text`
  - `commercial_use_allowed`
  - `noncommercial_use_allowed`
  - `sharealike_required`
  - `free_access_required`
  - `trademark_restrictions`
  - `reviewed_by`
  - `reviewed_at`

- `source_item`
  - `id`
  - `source_id`
  - `external_id`
  - `item_type` such as `lesson`, `task`, `exercise`, `worked_example`, `standard`
  - `grade_band`
  - `domain`
  - `standard_tags`
  - `raw_title`
  - `raw_text`
  - `raw_json`
  - `license_id`
  - `ingestion_status`

### Curated Tutor Content Tables

These are the database equivalent of the current gold JSON plus template metadata.

- `skill`
  - `id`
  - `name`
  - `domain`
  - `standard_tags`
  - `prerequisite_skill_ids`
  - `description`

- `template`
  - `id`
  - `skill_id`
  - `domain`
  - `template_kind`
  - `answer_type`
  - `checker`
  - `param_schema`
  - `solve_function_ref`
  - `diagnostic_catalog_ref`

- `problem_item`
  - `id`
  - `template_id`
  - `difficulty`
  - `assessment_role`
  - `source_item_id`
  - `curation_status`

- `problem_realization`
  - `id`
  - `problem_item_id`
  - `realization_key`
  - `theme_id`
  - `prompt`
  - `canonical_answer`
  - `solution_method`
  - `param_values`
  - `semantic_roles`
  - `source_item_id`
  - `license_id`

- `hint_scaffold`
  - `problem_item_id`
  - `max_safe_hint_level`
  - `level_0`
  - `level_1`
  - `level_2`
  - `level_3`

- `representation_payload`
  - `problem_item_id`
  - `realization_key`
  - `kind` such as `graph`, `table`, `grid`
  - `payload_json`

- `diagnostic_distractor`
  - `template_id`
  - `error_tag`
  - `distractor_expression`
  - `confidence`

- `content_promotion`
  - `id`
  - `artifact_sha256`
  - `promoted_at`
  - `promoted_by`
  - `source_count`
  - `problem_count`
  - `realization_count`
  - `verifier_ok`
  - `verifier_report_json`
  - `provider_runs_json`

## Ingestion Pipeline

### Stage 1: Source Capture

Fetch or manually import the source artifact without transforming it. Store the exact raw artifact, URL, retrieval time, SHA-256, and license page URL. Do not parse educational meaning yet.

Allowed methods:

- Official downloadable files or web exports.
- Official APIs where available and licensed.
- Git clone only where the repository's content license allows reuse.
- Manual upload for PDFs/HTML exports when automatic access is not stable.

Forbidden methods:

- Scraping authenticated proprietary platforms.
- Calling internal/private APIs.
- Using learner or teacher accounts to bulk extract content.
- Caching Wolfram Alpha generated results as curriculum material.

### Stage 2: License Classification

Run a deterministic license classifier over each `source_item`, then require manual approval for anything except explicit public domain, CC0, CC BY, CC BY-SA, CC BY-NC, or CC BY-NC-SA from a trusted source page. Items with unclear, proprietary, or platform-specific terms remain unavailable until reviewed.

Promotion blocks if any candidate problem references a `source_item` whose license status is not allowed for the target deployment mode. In `free_noncommercial` mode, NC material may be promoted only if the app remains free, attribution is displayed or otherwise made available as the license requires, and any share-alike obligation is tracked. In `commercial` mode, NC material must be filtered out automatically.

### Stage 3: Educational Extraction

Parse source items into a neutral staging format:

```json
{
  "source_item_id": "...",
  "grade_band": "8",
  "domain": "linear_functions",
  "standard_tags": ["CCSS.8.F.B.4"],
  "learning_goal": "Interpret slope as a rate of change",
  "task_text": "...",
  "given_quantities": [],
  "unknown": "",
  "representations": ["table", "graph"],
  "candidate_skill_ids": []
}
```

This stage may use an LLM to summarize or classify, but it must not author canonical answers. It can propose a template match; deterministic code must validate the match.

### Stage 4: Template Binding

Map each staged item to an existing deterministic template or reject it into a template-authoring queue. For the current repo, that means binding to `backend/content_pipeline/templates/linear_functions.py` cases first.

Binding rules:

- Extracted quantities must map to named template params and semantic roles.
- The template `solve()` must compute the canonical answer.
- The generated `PublicProblem` and `PrivateProblem` must share the exact `RealizedProblemRef`.
- Public prompts, tables, graphs, grids, and hint scaffolds must contain no canonical answer or banned intermediate.
- If no template exists, do not promote the item. Create a proposed `template_kind` and author it separately with tests.

### Stage 5: Realization Authoring

For each accepted template-bound item:

- Keep one `neutral` realization.
- Add themed realizations only when the theme is genuinely generative for the skill.
- Write authored hint scaffolds per problem, not runtime-derived hints.
- Cap single-step items at `max_safe_hint_level <= 2`.
- Store graph/table/grid payloads as public-safe structured JSON.

The LLM can draft wording, but a verifier and human review must approve it before promotion.

### Stage 6: Verification and Promotion

Before a row becomes runtime-visible:

- Run schema verification equivalent to `python -m backend.content_pipeline.verify`.
- Run safety scan equivalent to `python -m backend.content_pipeline.safety`.
- Recompute every answer from template params and compare to `canonical_answer`.
- Check public/private leak boundaries.
- Check graph/table/grid payloads contain only public-safe keys.
- Check source license status is allowed for the deployment.
- Write a `content_promotion` record with artifact hash and provider-run provenance.

The runtime app should read only promoted content. Staging rows are never used by `/session/start` or `/turn`.

## Migration Path for This Repo

### Phase A: Keep Runtime Stable

Leave `backend/app/content/seed_loader.py` and the current gold JSON in place. Add DB ingestion tables and exporters behind the offline pipeline only.

First milestone: import the existing `backend/content_pipeline/gold/linear_functions.json` into the proposed tables, then export it back to byte-stable or semantically equivalent JSON and prove the current verifier still passes.

### Phase B: Add OER Source Staging

Start with one noncommercial-compatible source family:

1. Illustrative Mathematics / Open Up 6-8 content with explicit CC BY or CC BY-NC license.
2. OpenStax algebra/prealgebra content where the current CC BY-NC-SA license and attribution/share-alike obligations can be satisfied.
3. OER Commons items tagged public domain, CC BY, CC BY-SA, CC BY-NC, or CC BY-NC-SA and manually reviewed.

Do not start by copying Khan, CK-12, GeoGebra, or proprietary adaptive-platform content. Khan and YouTube-style resources belong in a supplemental recommendation catalog as outbound links/embeds, not in the canonical problem bank.

### Phase C: Expand Templates

Use ingested source items to identify gaps, but author deterministic templates in code. The template backlog should be ordered by reuse:

1. Linear functions: slope/rate/intercept/equation/evaluate.
2. Expressions and equations.
3. Ratios and proportional relationships.
4. Systems of equations.
5. Quadratics only after graph/checker support expands.

### Phase D: Runtime DB Loader

After the DB can round-trip the current gold bank and pass the verifier, add a `DbProblemBank` implementing the same interface as `ProblemBank`:

- `public_problem(ref)`
- `private_problem(ref)`
- `public_refs()`
- `realization_keys()`
- `skill_ids()`

Switch runtime behind a feature flag:

- `CONTENT_BANK_BACKEND=json` default
- `CONTENT_BANK_BACKEND=db` opt-in

## First Implementation Slice

The first code slice should be small and reversible:

1. Add SQL schema/models for `content_source`, `content_license`, `source_item`, `skill`, `template`, `problem_item`, `problem_realization`, `hint_scaffold`, `representation_payload`, and `content_promotion`.
2. Add an importer that loads the current gold JSON into those tables.
3. Add an exporter that writes the same current gold JSON shape from those tables.
4. Add tests proving import -> export -> `verify_frozen_gold_bank(exported_path)` passes.
5. Add a license gate test proving `noncommercial_only` can be promoted only under `free_noncommercial`, and `permission_required` / `excluded` cannot be promoted under any mode.

This gives us a database-backed content substrate without committing to any external source parser yet.

Implemented starter commands:

```bash
python -m backend.content_pipeline.ingest gold --db /tmp/content.sqlite3
python -m backend.content_pipeline.ingest oer --db /tmp/content.sqlite3
python -m backend.content_pipeline.ingest generate-candidates --db /tmp/content.sqlite3 --per-skill 5
python -m backend.content_pipeline.ingest promote --db /tmp/content.sqlite3 [--skill <id>] [--limit N]
python -m backend.content_pipeline.ingest export-gold --db /tmp/content.sqlite3 --output /tmp/linear_functions.json
```

The OER command stages reviewed metadata from `backend/content_pipeline/oer_sources/linear_functions_starter.json`. It appends `content_source`, `content_license`, and `source_item` rows with `ingestion_status='staged_oer'`; it does not create runtime `problem_item` or `problem_realization` rows. This preserves the boundary that OER material informs skill alignment and template authoring but is not shown to learners until it is converted into deterministic, verified tutor-native content.

`generate-candidates` implements Stage 4 (template binding) for skills that have a deterministic generator (`backend/content_pipeline/candidate_generation.py`). For each generatable skill a staged OER item aligns to, it produces parametric problems, validates each through the same gates as the runtime bank (deterministic solver result, code-owned checker round-trip, content safety scan, no answer leak), and stores the survivors as `problem_item` rows with `curation_status='candidate'`, provenance-linked to the staged source item. Candidates are **not** promoted: `export-gold` only emits `curation_status='promoted'` problems, so generated content never reaches the runtime bank until a deliberate, verifier-backed promotion step (Stage 6).

`promote` implements Stage 6 *approval* in the DB. It re-verifies each selected candidate through the same gates (deterministic solver result, checker round-trip, safety, no leak), moves passing ones `candidate` -> `approved`, and writes a `content_promotion` audit row; a tampered candidate is rejected and left as `candidate`. Crucially, `approved` is distinct from the authored gold's `promoted`: `export-gold` still emits only `promoted`, so the frozen-bank verifier is untouched and **approval changes nothing learners are served**. Making approved-generated content learner-facing is a further, separate step (Phase D, the runtime DB loader) and is intentionally not automated.

## Supplemental Video Recommendation Catalog

Videos are optional remediation/support resources, not canonical tutor content. The app may recommend a Khan Academy, YouTube, OpenStax, MIT OCW, TED-Ed, or other educational video by storing metadata and an outbound URL/embed reference. It must not download, transcribe, or mirror video content unless the source license and platform terms explicitly allow that.

Suggested tables:

- `video_item`
  - `id`
  - `source_provider`
  - `source_video_id`
  - `title`
  - `canonical_url`
  - `embed_url`
  - `channel_or_author`
  - `duration_seconds`
  - `thumbnail_url`
  - `license_id`
  - `last_checked_at`
  - `availability_status`

- `video_skill_alignment`
  - `video_id`
  - `skill_id`
  - `misconception_tag`
  - `grade_band`
  - `alignment_confidence`
  - `alignment_reason`

- `video_review`
  - `video_id`
  - `review_status`
  - `reviewer`
  - `math_quality_notes`
  - `child_safety_notes`
  - `reviewed_at`

Recommendation rules:

- Prefer exact `skill_id` and misconception-tag matches.
- Use videos after a deterministic trigger, such as two failed attempts, repeated `malformed_input`, or a low-confidence diagnostic result.
- Rank by curated quality first, then source trust, then recency/availability, then popularity. Popularity alone is never enough.
- Always open external videos as clearly labeled third-party content. Do not imply the video provider endorses the tutor.

## Open Decisions

- Commercial posture: current mode is `free_noncommercial`; if this tutor becomes commercial, NC sources become reference-only unless written permission is obtained.
- Share-alike posture: decide whether CC BY-SA / CC BY-NC-SA content is acceptable, because adaptations may need to be distributed under the same license.
- Attribution UI: decide where source attribution appears for student-visible content.
- Human review workflow: decide whether review happens through admin UI, checked-in manifests, or database status changes.
