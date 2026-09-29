---
milestone: v1.0
id: CONSILIUM-MARK-OUTCOME-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: [CONSILIUM-FEEDBACK-001, CONSILIUM-RENDER-FEEDBACK-HTML-001, CONSILIUM-UTILS-001]
risk: 1
satisfies: [ARCH-CONSILIUM-LEARNING-001]
---

# mark_outcome

> Corrects a logged FEEDBACK.html outcome in place once production reality is known.

## Description

Every line in this section is binding.

- `mark_outcome.py` closes the feedback loop opened by `log_feedback.py`, allowing an outcome recorded at deliberation time to be corrected based on what happened in production.
- The script rewrites the matched FEEDBACK.html row in place, updating the outcome cell and annotating the note with `[confirmed]`.
- Rows are located via a fingerprint sidecar map (`--run-path`) or by a direct `--date` + `--chosen` pair.
- When no match is found, a fallback diagnostic lists the five most recent entries.
- `--dry-run` allows inspection of which rows would be updated without modifying any file.
- Overwrites `.consilium/FEEDBACK.html` atomically with updated outcome and annotated note for each matched row.
- stdout carries per-matched-row lines of the form `matched [i]: date | chosen | old_outcome -> new_outcome`.
- stdout carries `skip [i]: ...` lines when a row is already at the target outcome, or when PEND_HEADLESS is applied to a non-PEND row.
- stdout prints `(dry-run; no write)` when `--dry-run` is active.
- Exit code 0 on success or when no rows needed updating; exit code 1 on missing feedback file, bad argument combinations, or no match found.
- When matching by `--date` and `--chosen`, all rows that satisfy the predicate are updated, not only the first; each matched row produces a `matched [i]: ...` stdout line.
- `[confirmed]` annotation is idempotent: `_annotate_note` checks for its presence before appending, so repeated calls never accumulate duplicate tokens.
- `outcome_reason=` is similarly replaced (old stripped, new inserted) rather than accumulated.
- `--outcome PEND_HEADLESS` enforces a source-state guard: if the matched row's current outcome is not `PEND`, the row is skipped with a stderr diagnostic and exit 0 (not an error).
- Only rows already at `PEND` are converted by `--outcome PEND_HEADLESS`.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given a valid `--run-path` pointing to a logged run, when `mark_outcome.py` runs, then the corresponding FEEDBACK.html row's outcome field is updated to the specified value and the note gains `[confirmed]` (or `outcome_reason=...` if `--reason` is provided).
- **CASE-2** — Given `--dry-run`, when the script runs, then no file is written and stdout reports the matched rows with their pending transition.
- **CASE-3** — Given `--outcome PEND_HEADLESS` without `--benchmark`, when the script runs, then it exits 1 with a descriptive error and does not modify FEEDBACK.html.
- **CASE-4** — Given neither `--run-path` nor both `--date` and `--chosen` are supplied, when the script runs, then it exits 1 with a usage error.
- **CASE-5** — Given a query that matches no rows, when the script runs, then it exits 1 and prints the last 5 rows to stderr as disambiguation candidates.

## Context (non-binding)

**Notes** — Input: `--run-path` (relative or absolute path to a `runs/*.json` file); `--date YYYY-MM-DD` + `--chosen <id>` as an alternative direct-match strategy; `--outcome` one of `OK | BAD | OVR | PEND | PEND_HEADLESS` (required); `--reason`; `--dry-run`; `--benchmark` (required guard for `--outcome PEND_HEADLESS`); `--feedback` override path. Reads and rewrites `.consilium/FEEDBACK.html` in place and reads the `.consilium/runs/.run_path_map.json` sidecar populated by `log_feedback.py`. Rationale: the initial outcome logged at Step 6 is a subjective gut-feel, and production reality can contradict it days later (a chosen approach may break production, or a risky override may prove correct); `[confirmed]` lets `priors.py` weight confirmed-outcome rows higher than purely subjective ones.

**Current implementation** — `scripts/mark_outcome.py`.
