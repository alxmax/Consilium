# Changelog

All notable changes to Consilium are recorded here, following
[Keep a Changelog](https://keepachangelog.com/). This project is licensed under the
Apache License 2.0 (see `LICENSE`); versions up to 1.14.0 were published under the
Business Source License 1.1.

## [1.15.0] — 2026-10-13

### Changed
- License: Apache License 2.0 instead of the Business Source License 1.1, for the repository and the shipped plugin (`LICENSE`, `consilium/LICENSE`, `plugin.json`). Apache-2.0 was already the BSL's Change License; any organization may now use Consilium, commercially included. Versions up to 1.14.0 stay under BSL-1.1.

### Added
- `scripts/reqmap_engine/LICENSE`: the MIT license of the vendored requirement-map engine (from requirement-manager), kept next to the copied code.

## [1.14.0] — 2026-10-13

### Changed
- The plugin now lives in `consilium/` (manifest, `SKILL.md`, agents, prompts, modes, the 25 runtime scripts and the three docs they cite, a plugin README and `LICENSE`). An install receives only this folder: about 50 files instead of the whole repository, with no tests, repo tooling, hooks, generated HTML or contributor guidance. The marketplace at the repo root points at it (`source: ./consilium`), so `/plugin marketplace add alxmax/Consilium` keeps working; with APM, install `alxmax/Consilium/consilium`.
- Tests, gates and repo tooling stay in `scripts/` and reach the plugin through `scripts/plugin_paths.py`. `check_doc_drift.py` resolves each normative doc's references against its own location, so a repo-root doc that names a moved script fails instead of passing.
- `version.py --drift` lists changed prompt and mode files relative to the plugin folder (`git diff --relative`).
- Five runtime scripts wrote the byte-order mark they strip from stdin as a literal invisible character; it is now the escape `"﻿"` (same behaviour).

### Added
- `scripts/test_plugin_folder.py`: the plugin folder holds only allowed paths, no tests, no file over 256 KiB, no `git push`/`git commit`, no remote `<script src>`, and no invisible format characters.

## [1.13.1] — 2026-10-13

### Fixed
- Deliberation state (`runs/`, `FEEDBACK.html`, `preview/`) was resolved next to the installed scripts, not in the user's project. For a plugin install the journal lived in the versioned plugin cache, so every update started an empty journal and `priors.py` lost its history, while the orchestrator wrote reports to the project's `.consilium/runs/`. `scripts/utils.py` now resolves `DATA_DIR` to `$CONSILIUM_DATA_DIR` when set, otherwise `.consilium/` in the current working directory; `scripts/vote_degeneracy.py` uses the same rule. The development checkout is unchanged (its cwd is the repo root). Journals left in old plugin cache directories are not migrated: point `CONSILIUM_DATA_DIR` at one, or copy it into a project's `.consilium/`, to keep its history.

## [1.13.0] — 2026-10-13

### Changed
- Development now happens in this public repository, renamed from `Consilium_Demo` to `Consilium`. The former private development repository is archived; `homepage`, `repository`, the README install command, the explainer's repository link and `REQMAP_REPO` now name `alxmax/Consilium`, and the Pages site is at `https://alxmax.github.io/Consilium/`.
- `scripts/check_public_leak.py` now flags references to the archived dev repository by its own slug, instead of every `alxmax/Consilium` slug that is not the old `_Demo` name.

### Removed
- `benchmark/`: the mode-vs-baseline harness moved to its own repository, [Consilium-Benchmark](https://github.com/alxmax/Consilium-Benchmark), so installing the plugin no longer ships it. It loads this plugin from a sibling checkout (`--plugin-dir`); `scripts/fix_benchmark_pendings.py` stays here because the harness calls it.

## [1.12.4] — 2026-09-29

### Added
- `scripts/validate_implement_output.py`: a stdlib validator for the STRICT-JSON output of the implement Coder, Test Writer and the implement-subagent manifest (blocked/reason rules, disjoint paths, scope escapes, `fails_on_empty_impl`, red->green reporting). Exit 0 ok, 1 problems, 2 not JSON. The implement-subagent spec now runs it before trusting a role's output (same single retry as any schema-invalid output).
- Tests for it (`test_validate_implement_output.py`) tie Coder AC-1..3 and Test Writer AC-1..2 to real checks, and assert the validator's key sets match the JSON examples in the three spec files so they cannot drift apart.

### Changed
- Those five cases no longer carry `verifiable by: inspection`. Test Writer AC-3 stays inspection: no spec pins the shape of `uncoverable[]` or how a test refers to it, so "no test is emitted for it" has nothing to check against.

## [1.12.3] — 2026-09-29

### Changed
- Behavior-preserving refactor of the long functions, deep nesting, long parameter lists and module-state writes the design pass flagged (33 candidates -> 7): `aggregator.py`, `validate_report.py`, `log_feedback.py`, `mark_outcome.py`, `audit_feedback.py`, `feedback.py`, `check_doc_drift.py`, `check_versions.py`, `build_report.py`, `infer_pipeline.py`, `implement_pipeline.py`, `render_impl_preview.py`, `scope_gate.py`, `confidence_calibration.py` (now takes a `Thresholds` tuple), `memory.py`, `priors.py` and the run-consilium driver. Public names, CLI flags, exit codes and output are unchanged.
- Not addressed on purpose: the five files over 500 lines and the two function-name-prefix families; splitting them would break the stdlib-only stand-alone-script convention.

## [1.12.2] — 2026-09-28

### Fixed
- Acceptance-case traceability: every case of the implement pipeline, aggregator, validate-report, vocabulary-map and lens-ladder requirements is now tied to a `# verifies:` test (new tests for the pipeline CLI and gate edge cases, `team_vote`, `validate_report` exit codes and the lens_applied problem text). The Coder and Test Writer cases describe model output and are marked `verifiable by: inspection`.

### Changed
- Dropped four `test_exempt` exemptions that were stale (`feedback.py`, `check_public_leak.py`, `mark_outcome.py`, `memory.py`) by testing them; the other 17 stay because they cover model-run prompts, agent specs or integration harnesses.

## [1.12.1] — 2026-09-28

### Changed
- Benchmark harness now targets Claude Sonnet 5.5 (`claude-sonnet-5-5`) by default and for the `sonnet_bare` pin and verifier judge; the Opus 5.5 batch runs with `--model claude-opus-5-5`.
- Docs and the architecture explainer name Sonnet 5.5 for the voices and sub-agents (dispatch already tracks the `sonnet` alias).

## [1.12.0] — 2026-09-22

### Removed
- **Automatic Sequential → Dialectic re-run at confidence < 0.6.** It re-ran the whole pipeline in Dialectic with no confirmation, on a signal that does not predict outcomes: on `[confirmed]` FEEDBACK rows the OK-rate is 0.86 below 0.6 (n=21) against 0.93 / 0.92 above (n=30 / n=13) — about one or two extra failures, not significant — and no measurement showed the re-run improves results. Low confidence now gets the Step 5d retry and the Step 6 override prompt, which also suggests rerunning with `--mode dialectic` / `--skeptic-on-chosen`. `build_report.py` no longer passes `auto_escalated` through (historical runs keep the field; nothing requires or rejects it). SKILL.md, `modes/sequential.md`, README, the explainer and the poster no longer describe the re-run; the poster's confidence arrow is relabelled as the Step 5d retry it draws.

### Fixed
- README's worked example still said a low-confidence run auto-fires a Skeptic, which 1.11.0 removed.

## [1.11.0] — 2026-09-22

### Changed
- **Confidence is advisory; it no longer auto-dispatches the Skeptic.** Measured on the 64 `[confirmed]` FEEDBACK outcomes, confidence does not predict success: Brier 0.163 against 0.085 for simply predicting the base rate, and an OK-rate of 0.92 at confidence ≥ 0.7 against 0.90 below (`scripts/confidence_calibration.py` on all 273 labelled rows already returned `FALLBACK_A`). The `confidence < 0.70` trigger of `skeptic_on_chosen` is removed; the flag is opt-in (`--skeptic-on-chosen`) plus its non-confidence triggers — high Conservator concern (`trigger_reason: "high_concern"`, formerly gated on confidence > 0.7), a similar recent BAD, irreversibility. The Step 5d retry, the Step 6 override prompt, the mode floors and the `< 0.6` Dialectic escalation keep their thresholds as heuristics. The three explainer drift invariants that pinned the `[0.0, 0.70)` band now forbid it and require `--skeptic-on-chosen`.
- **Trias cost figure cited.** SKILL.md and `modes/trias.md` now state that the cost multipliers are sub-agent-count estimates and that Trias's 2.67× was token-checked only as a 4-vs-6 spawn ratio on n=2 problems (`experiments/trias-6to4-cost-2026-06-19.md`); its absolute cost against Sequential is unmeasured.

### Removed
- **`priors.py` outputs no consumer read:** `override_rate`, `conservator_veto_rate` (with `runs_seen` and the `_run_had_veto` / `_veto_rate` helpers) and `top_note_keywords` in the JSON. The Conservator's `--memory-summary` (counts, confirmed `bad_rate`, recurring keywords, prior match) is unchanged.

## [1.10.0] — 2026-09-22

### Changed
- **A run is OK only on evidence.** Step 6 now logs every run as PEND: confidence measures agreement between voices, not whether the choice worked, yet 281 of 297 rated FEEDBACK rows were OK assigned from `confidence >= 0.7` alone (78 carry `[confirmed]`). A row becomes OK or BAD through `mark_outcome.py` once the report's `verification` passes or reality refutes it; `log_feedback.py --outcome OK` now requires `--confirmed` and adds the marker.
- **`priors.py` rates only `[confirmed]` rows.** `override_rate` / `bad_rate` ignore self-assigned outcomes (`rated_count == confirmed_count`); a new `unconfirmed_count` reports how many were left out. `weighted_bad_rate` and its 2× weight are removed — with only confirmed rows counted, the weighting had nothing left to weigh.
- **Headless detection is explicit.** `priors.py` no longer treats a non-tty stdin as headless — under Claude Code's Bash tool stdin is never a tty, so every interactive session silently suppressed `stale_pendings` and `missing_feedback_runs`. Headless is now `--headless`, `CONSILIUM_HEADLESS=1` or `CLAUDE_HEADLESS=1`.

### Added
- **`CLOSED_UNVERIFIED` outcome** (`mark_outcome.py`): closes a stale PEND with no evidence either way; excluded from every rate and never marked `[confirmed]`.
- **`validate_report.py --all <runs_dir> [--quarantine]`**: sweeps every run (dot-files skipped), prints each failure and a `checked / ok / fail` summary; `--quarantine` moves failures to `<runs_dir>/_invalid/`, outside the glob `priors.py` reads.

### Fixed
- `feedback.parse_runs` read `.run_path_map.json` as if it were a run.

## [1.9.0] — 2026-09-22

### Changed
- **SKILL.md trimmed from 58,231 to 30,041 bytes** (Sequential load path — SKILL.md + `modes/sequential.md` + 3 voices — 13,082 → 9,450 words, −28%). The workflow and every runtime rule stay in SKILL.md; reference material the orchestrator does not need on every run (calibration caveats, the Step 6 interception contract, retroactive-outcome details, the Step 7 lookup table and pipeline benchmark, headless rationale, feedback storage details, skill maintenance, the script table) moved verbatim to the new `docs/skill-reference.md`, linked from the step that uses it. Per-mode sections collapsed into one Modes list under the mode table; the removed Parallel section is reduced to one line.

### Added
- **`skill_md_size` doc-drift invariant**: `check_doc_drift.py` fails when SKILL.md exceeds 32,000 bytes. Covered by `scripts/test_check_doc_drift.py`.

## [1.8.2] — 2026-09-22

### Fixed
- **Stale Trias lens names in SKILL.md Step 0.** It still told the orchestrator to read `pioneer_lens.md` / `architect_lens.md` / `steward_lens.md`, which were replaced by `essentialist_lens.md` / `verifier_lens.md` / `sentinel_lens.md` in PR #482. New `referenced_contract_exists` invariant in `check_doc_drift.py`: every `prompts/voices/`, `modes/` and `agents/` `.md` path (and bare `<name>_lens.md`) referenced by a normative doc must exist. Covered by `scripts/test_check_doc_drift.py`.

### Removed
- **Retired meta-critic step (Step 5c).** `scripts/deprecated/meta_critic.py` (retired 2026-05-25), its suite `test_meta_critic_trim.py`, its CI step and driver entry, and its 4 `evals/scenarios.json` cases (run_evals 65 → 61). `build_report.py` still passes a legacy `deliberation_quality` block through so older bundles round-trip.

## [1.8.1] — 2026-09-21

### Removed
- **`trias_split` legacy mode alias.** Its dated removal milestone (2026-08-21) had passed, which turned the `legacy_mode_milestone` doc-drift check red on `main`. `validate_report.py` no longer maps `trias_split` to `trias`; historical `trias_split` runs still validate, because `telemetry.mode` is an open string, but they skip the per-voice telemetry check. `vote_degeneracy.py` still counts them as Trias runs.

## [1.8.0] — 2026-07-07

### Added
- **Opt-in personality-lens ladder (`--lens <name>`, default OFF).** Sequential can prepend one lens (`--lens essentialist`) to Generator→Conservator→Control; Dialectic's rung (`--lens essentialist`) puts **Essentialist on the decider** and **tints the Skeptic with the Verifier lens** (complementary roles, not a vote — `decider != skeptic`). No new sub-agent dispatch; lens text costs ~18% per-voice prompt tokens, so it is **off by default**, keeping the default path's cost unchanged.
- **Verifier lens Skeptic carve-out** (`prompts/voices/verifier_lens.md`): the Verifier lens is now coherent when tinted onto the Skeptic voice (previously it only described Generator/Control/Conservator roles). This is the "tint, no new file" mechanism — no separate skeptic-lens prompt is added. Locked by a new keyword assertion in `scripts/test_lens_bias.py`.
- **`telemetry.lens_applied`** (`{decider, skeptic?}`), validated by `scripts/validate_report.py`: present only on an opt-in `--lens` run, absent on default runs; for Dialectic the decider and skeptic lenses must differ (runtime `decider != skeptic` enforcement).

**Provenance — shipped OFF-by-default over a MODIFY verdict, documented per the audit's own condition.** Two same-day internal design reviews (2026-07-07, MODIFY; and a pinned refinement, MODIFY) returned MODIFY, not GO. The dominant, twice-repeated condition — ship **opt-in / default OFF** rather than a mode default — is honored here (this satisfies the user's hard cost constraint literally: 0 token delta unless the flag is set). The A-vs-B fork for "Verifier as skeptic" was resolved to **B (tint)** with the required coherence carve-out; pure-A (a new prompt file) was rejected by the audit as violating "no new files / cost unchanged." **Lens value remains empirically unproven** (Trias is 0/6 vs baseline on the only valid instrument — a saturated corpus, i.e. an absent test, not a failed one; `experiments/trias-discriminating-tasks-design.md`). Default-on is therefore **not** shipped and is gated on a future discriminator pilot (n≥10–20 on a non-saturated, oracle-validated code-deliberation corpus). This entry is the deliberate, traceable record of that override, per the design review's own condition.

## [1.7.0] — 2026-07-07

### Changed
- **Sequential's deliberation now runs as one dispatched sub-agent** (`subagents: 0 → 1`), mirroring the atomic unit Trias already uses per personality: Generator → Conservator → Control still run in a single shared context (unchanged internally — `strip_context.py` and Generator's turn-1 blindness still apply), but that context is now the sub-agent's own, not the orchestrator's. The sub-agent returns the three raw voice outputs (`generator_out`, `control_out`, `conservator_out`) **unmodified** — `aggregate_sequential()` is untouched. Dialectic inherits this automatically (`subagents: 1 → 2`, its own definition — "Sequential + Skeptic" — unchanged).
- Real wall-clock instrumentation for Sequential's dispatch (`telemetry.voices.sequential_dispatch.latency_ms`), replacing the previously-hardcoded `0` for in-context voices.
- `docs/architecture/src/modes.jsx` data fields updated to match (subagent counts, isolation description); the animated walkthrough step-by-step diagram for Sequential still depicts the pre-dispatch layout and has not been reworked to show a separate sub-agent box — tracked as a follow-up, not blocking.

**Provenance — shipped over a same-day MODIFY verdict, by explicit user override.** An independent internal design review examined this exact change twice, same day, and returned MODIFY both times (DEEPLY_SPLIT in round 1, MODIFY in round 2 after focal cross-examination) — concerns: unmeasured benefit magnitude, a likely net cost increase from losing prompt-cache warmth in a freshly dispatched sub-agent, and an invalid citation of Trias's atomic-dispatch precedent (Trias isolates personalities to protect voting integrity; Sequential has no vote to protect). The user reviewed both verdicts and instructed an explicit override. Implementation then ran through Trias (3 personalities + post-vote Skeptic) for the *how*, not the *whether*: the Skeptic caught and this release fixes a real correctness gap the review had not named — an earlier draft would have had the sub-agent return only `{chosen_approach, rationale, confidence}`, which would have silently disabled `aggregate_sequential()`'s entire veto cascade (BLOCK/REWORK/SHORT-CIRCUIT/ESCALATE never firing for Sequential again). All accepted tradeoffs are documented in `modes/sequential.md` § Accepted tradeoffs, not silently absorbed.

## [1.6.0] — 2026-07-07

### Added
- Declared falsifier on the chosen approach, **consumer-first** (design review
  `2026-07-07_011914-consilium-falsifier-round2-control-voice`, MODIFY 0/8/1
  — implement-now rejected; this ships the review-revised trim instead of the
  original clause): (1) `build_report.py` now persists Control's
  `strongest_objection` + `no_blocking_defect_attested` into the run JSON's
  control step — previously emitted mid-deliberation but never persisted;
  (2) `mark_outcome.py --auto-suggest` reads the declared falsifier
  (`strongest_objection.reason`) from the run JSON as the default `--reason`
  when scoring an outcome (explicit `--reason` wins; degrades gracefully on
  pre-1.6.0 runs); (3) `prompts/voices/control.md` Q5 amendment: when
  `no_blocking_defect_attested: true`, `strongest_objection.reason` must
  carry a falsifiable exit-claim about the likely-chosen candidate — an
  observable external to the verdict; verdict-restatement invalid.
  Red→green tests in `test_build_report.py` and `test_feedback_html.py`.
  **Measurement protocol (declared before landing):** 1.5.0 + 1.6.0 are one
  bundled treatment for all benchmarking purposes; no separate attribution
  of effects to either round. **Unvalidated for quality** — same discipline
  as 1.5.0, no quality-improvement claim made.

## [1.5.0] — 2026-07-07

### Added
- Prompt-only discipline transplant from an internal design-review framework
  into the 3 core voices (`prompts/voices/generator.md`, `conservator.md`, `control.md`):
  a Conservator silent-failure question (Q6), a merged Control rule requiring
  `strongest_objection` to be a testable claim anchored to a declared
  `hidden_assumptions` premise, a materiality/polite-retreat discipline on all
  three voices, and a `## Limits` disjointness section per voice. No JSON
  schema change, no new dispatches, no `aggregator.py`/`validate_report.py`
  edits — purely additive prompt text. Per design review run
  `2026-07-06_093007` (GO_WITH_CONDITIONS) and the trimmed spec from its
  reviewers' cross-questioning (the final blocking condition). `test_lens_bias.py` (4/4), `test_vote_degeneracy.py` (4/4), and
  `run_evals.py` (65/0) are identical before and after — zero verdict
  inversions. Manually verified on one qualitative example (not part of the
  scored corpus) that the new clauses produce the intended behavior: Q6 names
  the silent-failure mode explicitly instead of it surfacing scattered/implicit
  elsewhere, and `strongest_objection` cites a numbered premise instead of a
  free-floating claim. **Unvalidated for quality** — n=1, manual, no claim of
  improved deliberation quality is made or implied by this change.

## [Unreleased]

- Aggregator gate: reject `generator.preferred` not among the candidate ids (#464).
- Implement-gate: stub all fan-out targets in the red→green gate + pin mode
  confidence floors in the drift gate (#465).
- Deprecated scripts and Pass-2 prompts deleted; normative doc references
  updated (#466).
- Green-gate section + measured benchmark results in the architecture explainer
  and README (#467).
- Architecture explainer: 7 content drifts vs the repo corrected + 5 new drift
  invariants pinned (#468).
- Script robustness: 8 audit fixes — BOM/encoding hardening, empty-candidates
  guard, 0.0-score routing, stub-gate header scan (+RED tests) (#469).
- Docs: strict skeptic-band notation, runs-schema overhaul, stale refs cleaned
  post-#454/#466 (#470).
- Gates/evals: revived the dead pre-commit reqmap gate, driver↔CI parity,
  enforced legacy-alias removal milestones, leak-gate RED tests, #464 eval pins,
  measured benchmark docs (#472).
- Skeptic-lever contract coherence: runner_up input, tiebreak mode,
  addressable-keyed demolish predicate, post-#416 subagent semantics (#473).
- Migrated Sonnet 4.6 references to Claude Sonnet 5 (#474).
- `render_impl_preview.py`: opt-in Step 7 static HTML review page bundling spec,
  rationale, and the multi-file diff (#475).
- Reqmap: version provenance retagged to `CONSILIUM-VERSION-001` + stale
  acceptance/wording reworded (review 2026-07-03 batch b/d/e) (#476).
- Install docs: `.consilium/` gitignore noted as recommended-but-preference
  (keep tracked if you want the trail versioned) (#477).

## [1.4.3] — 2026-07-06

### Fixed
- The "Code integration pipeline" explainer section (`docs/architecture/src/extras.jsx`
  `ImplementSection`) never stated its own sub-agent count (3) or cost multiplier
  (~1.1×) anywhere in its text, unlike every other mode/flag (Sequential,
  Dialectic, Trias, `skeptic_on_chosen`), which all state cost + sub-agent count
  explicitly. Added the missing stat to `GATE_ITEMS` and a new
  `check_doc_drift.py` invariant (`check_implement_pipeline_spec_alignment`)
  pinning it against `modes/implement_pipeline.md`'s frontmatter.

## [1.4.2] — 2026-07-06

### Fixed
- Architecture explainer, README, benchmark instructions, and the
  `consilium_full` poster generator still named the retired Trias personality
  team (Pioneer/Architect/Steward) after the v3 lens rename (PR
  #482) replaced it with Essentialist/Verifier/Sentinel. Renamed everywhere
  (with descriptions rewritten to match each personality's actual lens, not
  just the label), regenerated both derived HTML artifacts, and added a new
  `check_doc_drift.py` invariant (`check_trias_personality_name_parity`) so a
  future personality-team change can't silently miss the explainer again.

## [1.4.1] — 2026-07-06

### Fixed
- Architecture explainer: the "What the CI green-gate runs" section had silently
  fallen behind `ci.yml` — PR #485's `check_versions.py` + CHANGELOG-entry gate
  had no matching `CI_CHECKS` card. Added the missing card and a new
  `check_doc_drift.py` invariant (`check_ci_checks_completeness`) that fails CI
  if a future gate ships with no matching card or explicit allowlist entry.
  Found by a Trias self-audit (3-0, confidence 0.95); the post-vote Skeptic
  caught and fixed an under-specified matching rule before it shipped.

## [1.4.0] — 2026-07-06

### Added
- Plugin manifest version-coherence gate: `scripts/check_versions.py` asserts
  `plugin.json` and `marketplace.json` semver agree, and CI now requires that
  any `plugin.json` version bump ships with a matching CHANGELOG entry —
  mirroring `requirement-manager`'s check. `marketplace.json` gained a
  `version` field for the first time (previously absent, now tracking
  `plugin.json`).

## [1.1] — 2026-06

### Changed
- Sequential reordered **Generator-first** (anti-anchoring), with the
  irreversibility consent gate moved pre-dispatch (Step 1.6,
  `scope_gate.consent_required`, fail-safe) — #416, review 2026-06-13.
- Trias redesigned 6→4 sub-agents: the 3 per-personality pre-vote Skeptics
  replaced by **one post-vote `skeptic_on_chosen`** on the winner; cost
  3× → ~2.67× (skeptic-lever redesign, 2026-06-19).
- Fixed modes `parallel_skeptic` / `dialectic_skeptic` collapsed into the
  composable `skeptic_on_chosen` flag; `trias_split` deprecated (2026-05-17;
  legacy names remain accepted via `_LEGACY_MODE_ALIASES`).

### Removed
- **Parallel mode** and the silent 1-in-20 parallel audit
  (`scripts/audit_counter.py`) — #454, review GO_WITH_CONDITIONS, 0 divergences
  in 41 empirical runs. Historical `mode: "parallel"` runs stay readable.
- Dialectic Pass-2 merge (`dialectic_merge.py` and the `*_pass2.md` prompts).

### Added
- Implement pipeline (post-GO: Coder → Test Writer ∥ Reviewer) with a
  red→green stub gate (`scripts/implement_pipeline.py`).
- Version provenance: git-describe stamp + resolvable `consilium_ref` per run
  (`scripts/version.py`); prior-deliberation passthrough.

## [1.0.0] — 2026-05-16

Initial public release, after a public-readiness pass (2026-05): closed a
benchmark answer-leak, hardened `.gitignore`, fixed three core-script bugs,
corrected benchmark doc-drift, made the architecture explainer's Trias dispatch
claim honest (parallel by spec mandate, serial in practice), added a README
usage example, scrubbed personal paths/artifacts, and added a stdlib CI
green-gate. Each change deliberated via `/consilium`.

### Deliberation engine
- Three adversarial voices — **Conservator** (risk/reversibility), **Generator**
  (alternatives, incl. `do_nothing`), **Control** (correctness + acceptance tests)
  — merged by an 8-component veto cascade (`scripts/aggregator.py`) into one
  canonical, validated report.
- Confidence scoring with per-mode floors (`scripts/confidence.py`); soft priors
  from a file-based feedback loop (`scripts/priors.py` + `.consilium/`).
- Scope gate (`scripts/scope_gate.py`) auto-skips trivial diffs; silent parallel
  cross-check audit (`scripts/audit_counter.py`).

### Modes
- **Sequential** (default, 1×), **Dialectic** (1.33×), **Trias** (3×, three
  personality lenses + democratic vote), and the composable
  **`skeptic_on_chosen`** flag.

### Tooling & docs
- Benchmark harness (`benchmark/`) comparing each mode to bare-model baselines
  against an external hidden oracle.
- Interactive architecture explainer (`docs/architecture.html`; React source
  under `docs/architecture/`, built by `build.py`).
- `run-consilium` companion skill (build / test / smoke / screenshot).
- Deterministic regression suite (`evals/`), mode-doc drift gate
  (`scripts/check_doc_drift.py`), and a stdlib-only CI green-gate.

### License
- Business Source License 1.1 © 2026 Schipor Alexandru; converts to Apache-2.0
  on 2030-05-16.
