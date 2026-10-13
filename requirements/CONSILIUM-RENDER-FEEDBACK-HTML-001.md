---
milestone: v1.0
id: CONSILIUM-RENDER-FEEDBACK-HTML-001
status: confirmed
level: code
layer: bus
owner: alxmax
depends_on: [CONSILIUM-UTILS-001]
risk: 1
satisfies: [ARCH-CONSILIUM-LEARNING-001]
---

# render_feedback_html

> Pure rendering engine: a list of Entry records -> one self-contained dark-themed FEEDBACK.html.

## Description

Every line in this section is binding.

- `render_feedback_html.py` converts a list of Entry records into one self-contained, dark-themed HTML file with inline CSS and JavaScript, and no external assets.
- `render_feedback_html.py` exists as a separate bus-layer module so that both `log_feedback.py` and `mark_outcome.py` can rewrite FEEDBACK.html without duplicating HTML generation logic.
- The primary input is a list of `Entry` dataclass instances passed programmatically; a path to the `runs/` directory is passed to `render()` so linked run JSON files can be loaded for drill-down panels.
- Invoked as a CLI script, it reads a JSON object with an `entries` array from stdin, and accepts `--runs-dir` as an optional override for the `runs/` directory path.
- For each entry, telemetry (`tokens_in`, `tokens_out`) and `deliberation_log` (Generator candidates, Control verdicts, Conservator risk scores) are loaded from the linked `.consilium/runs/*.json` file when one exists.
- `render()` generates one `<tr class="entry">` row and one `<tr class="drill">` row for each Entry.
- Each entry row shows date, context, chosen approach, outcome badge, token count, note, and vote pattern.
- Each entry's drill-down panel loads Generator candidates, Control verdicts, and Conservator risk scores from the linked run file.
- Token counts show the measured `tokens_in + tokens_out` total when telemetry is present.
- Token counts fall back to a `(calc)` estimate when telemetry is absent. The estimate is the lower-median of per-candidate samples across peer entries in the same render invocation.
- Legacy entries with no run data show an em-dash in the token count cell.
- The VETOED badge in the Conservator panel is sourced from the aggregate step's `vetoed` list, not re-derived from a risk threshold, to avoid lying about candidates in the `[0.7, 0.8]` band.
- `render()` returns the complete `<!doctype html>` string as its primary output; callers write it to disk.
- Invoked as CLI, the HTML string is written to stdout.
- Exit code is 0 always.
- The output contains no `<link>`, `<script src>`, or `<img src>` references to external URLs.

## Verify intent

- None - `(calc)` peer runs are all entries in the current `render()` call that have measured telemetry (non-zero `tokens_in + tokens_out`); no filtering by mode or date. The median is the lower-median of the sorted per-candidate samples (`samples[len // 2]`). Reproducibility is therefore scoped to a single render invocation.
- None - when the run was produced by the `sequential` scheme (no `vetoed` list in the aggregate step), `vetoed_ids` resolves to an empty set; the Conservator drill-down panel is shown normally but no VETOED badges appear. Under-showing is preferred over fabricating badges.
- None - the self-contained property is stated as an Acceptance criterion but is not covered by any assertion in `scripts/test_feedback_html.py`; it remains a stated-only contract.

## Cases

- **CASE-1** — Given a list of Entry records, when `render()` runs, then it returns a string beginning with `<!doctype html>` containing one `<tr class="entry">` row and one `<tr class="drill">` row per Entry.
- **CASE-2** — Given an Entry whose `run_path` points to an existing `runs/*.json` file with telemetry data, when the page renders, then the tokens cell shows the measured sum of `tokens_in + tokens_out` across all voices, formatted compactly (e.g. `14k`).
- **CASE-3** — Given an Entry whose `run_path` points to a run file with a `vetoed` list in the aggregate step, when the Conservator drill-down panel renders, then it shows a VETOED badge only for candidates whose id appears in that list, never for a candidate exceeding a hard-coded risk threshold.
- **CASE-4** — Given an Entry with no linked run file (`run_path` is `None`), when the drill-down cell renders, then it contains the legacy stub message and no Generator/Control/Conservator panels.
- **CASE-5** — Given the rendered HTML output, when it is inspected, then it contains no `<link>`, `<script src>`, or `<img src>` tags referencing external URLs.

## Context (non-binding)

**Notes** — None beyond the Description above.

**Current implementation** — `consilium/scripts/render_feedback_html.py`
