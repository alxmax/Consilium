---
milestone: v1.0
id: CONSILIUM-PRIORS-001
status: draft
level: code
layer: feature
owner: alxmax
depends_on: [CONSILIUM-FEEDBACK-001, CONSILIUM-UTILS-001]
risk: 2  # REVIEW
satisfies: [ARCH-CONSILIUM-LEARNING-001]
---

# priors

> Describes observed behavior, verified against consilium/scripts/priors.py source.

## Description

Every line in this section is binding.

- `priors.py` computes advisory soft-prior signals from past deliberation history and emits them as a JSON object to stdout.
- The signal block is pasted into the deliberation at step 0 so voices can calibrate toward patterns that have caused past problems.
- Signals are advisory only; prompts in `prompts/*.md` remain authoritative.
- `priors.py` reads `.consilium/FEEDBACK.html` (the usage journal, parsed via `feedback.py`) and `.consilium/runs/*.json` (past deliberation reports).
- CLI flags control the read: `--n N` sets the recent-slice size (default 10); `--no-runs` skips the runs/ directory; `--feedback-file` overrides the FEEDBACK.html path; `--runs-dir` overrides the runs/ directory path.
- `recent` holds the last N FEEDBACK entries, newest first.
- `counts` tallies outcomes (OK / BAD / OVR / PEND) over the recent slice.
- `bad_rate` is a risk indicator derived from the `[confirmed]` rows of the recent slice (also surfaced to Conservator via `--memory-summary`); `unconfirmed_count` counts the OK/BAD/OVR rows left out.
- Rates count only rows whose note carries `[confirmed]`, so `rated_count == confirmed_count`. Outcomes assigned at log time without evidence do not move the rates.
- With `--label`, `prior_deliberation_match` is the newest in-window `OK` row whose context contains the label AND whose note carries `[confirmed]`; an unconfirmed `OK` never matches, because the match lets the caller skip re-deliberation.
- Headless mode is set only by explicit signals (`--headless`, `CONSILIUM_HEADLESS=1`, `CLAUDE_HEADLESS=1`); a non-tty stdin does not imply headless.
- `stale_pendings` lists FEEDBACK rows still PEND and older than `STALE_PEND_DAYS`. `STALE_PEND_DAYS = 2` is hardcoded, reduced from 7, and not CLI-configurable; entries older than 2 days surface at step 0 for retrospective close.
- `missing_feedback_runs` lists `runs/` files with no matching FEEDBACK row.
- Exit code is non-zero on a parse error.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given a valid `FEEDBACK.html` and `runs/` directory, when `python consilium/scripts/priors.py` runs, then it completes without error.
- **CASE-2** — Given the `--no-runs` flag, when `priors.py` runs, then `missing_feedback_runs` is suppressed from the output.
- **CASE-3** — Given FEEDBACK entries with outcome PEND older than `STALE_PEND_DAYS`, when `priors.py` runs, then those entries appear in `stale_pendings`.
- **CASE-4** — Given `runs/` files with no matching FEEDBACK row, when `priors.py` runs, then those files appear in `missing_feedback_runs`.

## Context (non-binding)

**Notes** — Signals described here reflect observed behavior, verified against the `consilium/scripts/priors.py` source rather than a separate design spec.

**Current implementation** — `consilium/scripts/priors.py`
