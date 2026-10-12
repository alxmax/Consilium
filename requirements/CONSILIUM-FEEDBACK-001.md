---
milestone: v1.0
id: CONSILIUM-FEEDBACK-001
status: confirmed
level: code
layer: bus
owner: alxmax
depends_on: [CONSILIUM-UTILS-001]
risk: 1
satisfies: [ARCH-CONSILIUM-LEARNING-001]
---

# feedback

> Canonical FEEDBACK.html parser + a human-readable stats report over logged outcomes.

## Description

Every line in this section is binding.

- `parse_feedback` parses `.consilium/FEEDBACK.html`, supporting three HTML row layouts for backward compatibility: attribute-based (`data-field`), and two legacy positional cell-count variants.
- Layout precedence is strict: attribute-based (`data-field`) is tried first; positional fallback applies only when no `data-field` attributes are found, matched by exact cell count in order 8-cell (Trias) -> 7-cell (previous) -> 6-cell (legacy) -> skip.
- Rows with an unrecognized `outcome` field are dropped entirely, excluded from both the total count and all outcome stats.
- `parse_feedback` returns an empty list without error when `.consilium/FEEDBACK.html` does not exist.
- The success-rate denominator is `OK + BAD + OVR` only; `PEND` and `PEND_HEADLESS` are excluded from the rate calculation.
- `parse_feedback` is a shared utility imported by `priors.py`, `log_feedback.py`, `efficiency.py`, and deprecated scripts.
- As a CLI tool, `feedback.py` prints to stdout: total logged uses, per-outcome counts, overall success rate excluding pending entries, recent overrides, and (with `--runs`) a breakdown of runs-on-disk by aggregation scheme.
- Exit code is 0 always.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given `.consilium/FEEDBACK.html` does not exist, when `parse_feedback` is called, then it returns an empty list without error.
- **CASE-2** — Given FEEDBACK.html containing all three row layouts (8-cell Trias, 7-cell previous, 6-cell legacy) and attribute-based `data-field` rows, when `parse_feedback` runs, then it correctly parses all of them.
- **CASE-3** — Given a row whose `outcome` field is not one of `OK`, `BAD`, `OVR`, `PEND`, `PEND_HEADLESS`, when `parse_feedback` runs, then the row is silently skipped.
- **CASE-4** — Given `--recent N` is passed, when the report is generated, then only the last N entries are included in the report stats.
- **CASE-5** — Given `--runs` is passed, when the report is generated, then it includes a per-aggregation-scheme breakdown from `.consilium/runs/*.json`, tolerating both legacy `aggregation.scheme` and current `deliberation_log[step=aggregate].scheme` shapes.

## Context (non-binding)

**Notes** — Input: `.consilium/FEEDBACK.html` (path from `utils.FEEDBACK_PATH`); `.consilium/runs/*.json` read only when `--runs` is passed. Exists to give the developer a human-readable health check on the skill's real-world usefulness without opening the HTML journal manually.

**Current implementation** — `scripts/feedback.py`.
