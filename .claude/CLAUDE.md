# Contributing to Consilium

This repo is the source of the `consilium` skill. To **use** it, invoke `/consilium` in a Claude Code session. This file covers only **editing** the skill.

## Contract

`SKILL.md` is the public contract. Read it before any change — the Constitution (4 principles) and the 8-step workflow govern the skill, not just its users.

For behavioral guidelines (Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution, Question Everything), see the global `~/.claude/CLAUDE.md` — they apply here too.

## Commands

Stdlib-only, no test runner. Smoke tests run manually via CLI:

- `python scripts/test_round2.py` — sequential architecture (skeptic_on_chosen, MODE enum, validate_report extras)
- `python scripts/test_feedback_html.py` — `render_feedback_html` + parser round-trip
- `python scripts/test_lens_bias.py`, `test_vote_degeneracy.py`, `test_implement_mode.py`, `test_implement_pipeline.py` — the remaining unit suites. Every `scripts/test_*.py` is gated in CI (`.github/workflows/ci.yml`) and the run-consilium `driver.py smoke` (enforced by `check_doc_drift.py`).
- `python scripts/run_evals.py` — regression scenarios from `evals/scenarios.json` (subprocess-based, deterministic; all scenarios run, non-zero exit if any fails)
- `python scripts/validate_report.py < .consilium/runs/<file>.json` — Constitution Principle #4 gate; minimum required before any commit touching `prompts/voices/` or `aggregator.py`
- `python scripts/check_doc_drift.py` — enforces parity between `modes/*.md`, `docs/architecture/src/*.jsx`, and `scripts/confidence.py` (invariants: Trias parallel dispatch, Trias 2-1/2-0 confidence values, sequential scale_down behavior) + dated removal milestones for legacy MODE aliases + test-suite coverage (every `scripts/test_*.py` must be gated in both `ci.yml` and the run-consilium driver — prevents the test-drift that hid a RED suite). Run before any commit touching `modes/`, `docs/architecture/src/`, `scripts/confidence.py`, or `scripts/test_*.py`. Origin: design audit `an internal design audit`.

Type-check: `pyright` (config: `pyrightconfig.json`, `typeCheckingMode: basic`, Python 3.11, `scripts/` in `extraPaths`).

## Pipeline

Canonical flow of a deliberation:

1. Voices read `prompts/voices/<name>.md`, emit JSON per Constitution
2. `scripts/aggregator.py` merges voice outputs → canonical report
3. `scripts/confidence.py` computes the score; `scripts/priors.py` applies priors
4. `scripts/validate_report.py` is the final gate before writing to `.consilium/runs/<ts>_<slug>.json`

Mode-specific scripts:
- `personalities.py` — Trias lens injection (Essentialist/Verifier/Sentinel)

Sub-agent dispatch (Trias, Skeptic): see `agents/consilium-subagent.md`. Sub-agents use `model: "sonnet"` by default — do not inherit Opus. **Trias**: each personality uses the `model` from `scripts/personalities.py` (all three → `sonnet`).

Architecture visualization: `docs/architecture.html` (open locally). Benchmarks on real problems: `experiments/` (benchmarking discipline: `experiments/oracle-discipline.md`).

## Python conventions

- **Stdlib-only.** No script introduces external dependencies. If it seems necessary, it likely means the feature exceeds the skill's scope.
- **Small, stand-alone scripts.** Each `scripts/*.py` has a CLI docstring, `argparse`, JSON I/O. Reuse between scripts goes through `importlib.util` (see `priors.py`), not packaging.
- **No tests dir.** Manual smoke-test via CLI; see `python scripts/validate_report.py < .consilium/runs/<latest>.json` as the minimum.

## Authoritative areas (touch carefully)

- **`prompts/voices/*.md`** — read by each voice at runtime. A change here affects all future deliberations → high `regression_risk` in Conservator. Prefer injecting extra context into the voice's input rather than into the prompt.
  - Core voices: `generator.md`, `control.md`, `conservator.md` — run in any mode
  - `skeptic.md` — focal challenger, run in `skeptic_on_chosen` (composable flag over any base mode)
  - `<personality>_lens.md` (Essentialist/Verifier/Sentinel) — prepended over core voices in `trias`
- **`SKILL.md` Constitution + workflow** — changing steps 0–7 breaks the JSON format expected by `aggregator.py` and `validate_report.py`. Modify both at the same time.

## Available modes

User-selectable modes (SKILL.md documents them in detail):

- **Sequential** (default) — Generator → Conservator → Control single-context.
- **Dialectic** — Sequential + Skeptic sub-agent on the chosen answer (Pass-2 and the old merge script removed; Dialectic no longer uses Pass-2).
- **Trias** — 3 personalities (Essentialist/Verifier/Sentinel), each runs Sequential internally and blind; democratic vote over the 3 results, then one Skeptic sub-agent (`skeptic_on_chosen`) challenges the winner post-vote (4 sub-agents nominal, worst-case 7, ~2.67× Sequential). The 2026-06-19 skeptic-lever redesign replaced the 3 per-personality pre-vote Skeptics with this single post-vote Skeptic.
- **`trias_split`** — removed 2026-09-21 (deprecated 2026-05-21); use standard `trias`.
- **`skeptic_on_chosen`** — composable flag over any base mode (+1 sub-agent overhead). Advisory by default; opt-in override via `--skeptic-can-override`. Opt-in via `--skeptic-on-chosen` plus non-confidence triggers (high Conservator concern, similar recent BAD, irreversibility); the old `confidence < 0.70` auto-trigger was removed because confidence does not predict outcomes. Replaces the fixed modes `parallel_skeptic` (= `parallel + skeptic_on_chosen`) and `dialectic_skeptic` (= `dialectic + skeptic_on_chosen`) — collapsed on 2026-05-17, legacy names remain accepted via `validate_report.py`'s `_LEGACY_MODE_ALIASES` map for backward-compat.

**Parallel removed.** Parallel dispatch is no longer available in any form (PR #454, 2026-06-26 — review GO_WITH_CONDITIONS, 0 divergences in 41 empirical runs; the silent 20-run audit was removed with it). For `critical` + `irreversible` changes, select `trias` explicitly. Legacy `mode: "parallel"` runs stay valid because `validate_report.py` does not enum-validate `telemetry.mode`; `"parallel"` is kept in its `_MULTI_VOICE_MODES` set so historical runs still get the per-voice telemetry check (`_LEGACY_MODE_ALIASES` covers only `parallel_skeptic` / `dialectic_skeptic`).

## Local files (gitignored)

All deliberation state lives under `.consilium/` (gitignored; paths centralized in `scripts/utils.py`).

- `.consilium/FEEDBACK.html` — real-usage journal, append-only via `scripts/log_feedback.py` (atomic writes). Migrated from `.md` format via a one-shot tool (now removed — see git history).
- `.consilium/runs/*.json` — output of each deliberation (schema in `docs/runs-schema.md`; only `.consilium/runs/.gitkeep` is tracked).
- `docs/superpowers/plans/`, `docs/superpowers/specs/` — artifacts from `superpowers:writing-plans` / `executing-plans` (one file per non-trivial feature, naming `YYYY-MM-DD-<slug>.md`). **Local-only (gitignored):** personal planning scratch with local paths/insider detail — kept on disk, not published.

## Self-improvement loop

When editing the skill itself: run `/consilium` on your own change. For changes to core prompts / architecture, consider `trias` over single-context deliberation. Save the run to `.consilium/runs/` and log it to `.consilium/FEEDBACK.html` via `log_feedback.py`.

## Git workflow

Rules for any non-trivial change made by Claude in this repo:

1. **New branch from `main`** before editing. Naming: `feat/<slug>` for features / new capabilities, `fix/<slug>` for bugfixes. Slug in kebab-case, descriptive (e.g. `feat/parallel-voices`, `fix/aggregator-null-confidence`). Only these two prefixes.
2. **One commit per branch** — first `git commit`, then `git commit --amend --no-edit` (or with a new message if scope changed) for each subsequent change in the same session. The branch always stays at 1 commit.
3. **Auto-push after commit** — without asking. If the user requests changes before the push — amend + push immediately.
4. **Push once**, then `git checkout main` automatically. After pushing, no amend + force-push without an explicit request — new changes = new branch.
5. **The user creates the PR manually.** Do not run `gh pr create`. At the end, just report the pushed branch.
6. **Exception: typos / 1-line fixes** can go directly to `main` if the user explicitly requests it. Everything else follows the workflow above.
7. **Commit messages** stay in Conventional Commits format (`feat(scope): ...`, `fix(scope): ...`), aligned with the branch prefix.
8. **Version bump on meaningful changes.** Bump `.claude-plugin/plugin.json`'s `version` (semver) and add a matching `## [X.Y.Z] — YYYY-MM-DD` entry to `CHANGELOG.md` together, in the same branch/commit as the change. Then run `python scripts/check_versions.py --fix` to propagate the version into `.claude-plugin/marketplace.json`. CI (`scripts/check_versions.py` + the "matching CHANGELOG entry" step) fails the build if the manifests drift apart or a version bump ships without a changelog entry — mirrors `requirement-manager`'s check_versions.py gate (adopted 2026-07-06). Trivial changes (docs typos, comment fixes) don't need a bump.
9. **Local gates when CI cannot run.** While GitHub Actions is unavailable (billing), run `python -X utf8 .claude/skills/run-consilium/driver.py smoke` (every `test_*.py` suite, `run_evals`, `check_doc_drift`, `reqmap.py gate --strict`, `build.py --check`) and `python scripts/check_public_leak.py` before each push, and list the results in the PR body — a merge without a green CI run must carry that record.

Automation: `scripts/commit.ps1 -Message "..."` handles stage → commit → push (`-Amend` for subsequent changes on the same branch). The `.claude/settings.json` `Stop` hook detects uncommitted changes on `feat/*`/`fix/*` branches after each turn and prompts Claude to complete the workflow.
