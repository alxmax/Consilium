---
id: CONSILIUM-INFER-PIPELINE-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: [CONSILIUM-IMPLEMENT-PIPELINE-001, CONSILIUM-UTILS-001]
risk: 1
satisfies: [ARCH-CONSILIUM-IMPLEMENT-001]
---

# Infer implementation pipeline steps

> Reads a deliberation report (from `build_report.py`) and determines which implementation steps apply — using a lookup table keyed on magnitude × reversibility — then presents them for confirmation before execution (SKILL.md Step 7).

## WHAT — Contract

- `infer_pipeline.py` reads a deliberation JSON (from `--input` or stdin) and looks up `(magnitude, reversibility)` in the step table, returning an ordered list from `{implement, compile, review, test}`.
- With `--dry-run`, it prints the inferred steps and exits 0 without confirmation or execution.
- With `--yes`, it skips the confirmation prompt (CI/headless mode).
- `infer_pipeline.py` exits 1 when the user declines or the inference produces no steps.
- `infer_pipeline.py` exits 2 on invalid JSON or missing required fields.
- When `chosen_approach` is `do_nothing` or `skipped`, it exits 1 with a clear message (no steps to infer).
- `infer_pipeline.py` also exposes `recommend_implement_mode(report)`, which returns `"pipeline"` for regression-risk quadrants (`moderate×irreversible`, `high×{partial,irreversible}`, `critical×any`), else `"single_shot"`.

## WHAT — Verify intent (open questions for the human)

- None — contract matches SKILL.md Step 7 routing table and script docstring.

## HOW — Acceptance (= tests)

- Given a report with `magnitude=moderate, reversibility=irreversible`, inferred steps are `[implement, compile, review, test]`.
- Given `chosen_approach=do_nothing`, exits 1.
- Given `--dry-run`, prints steps and exits 0 without writing any file.
- Given invalid JSON input, exits 2.
- `recommend_implement_mode` returns `"pipeline"` for `moderate×irreversible`; `"single_shot"` for `trivial×complete`.

## WHERE — Current implementation

- consilium/scripts/infer_pipeline.py
<!-- implements: CONSILIUM-INFER-PIPELINE-001 -->
