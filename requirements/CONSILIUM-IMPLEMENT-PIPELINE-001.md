---
milestone: v1.0
id: CONSILIUM-IMPLEMENT-PIPELINE-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: [CONSILIUM-UTILS-001]
risk: 1
satisfies: [ARCH-CONSILIUM-IMPLEMENT-001]
---

# implement_pipeline

> Turns a deliberation report into an implementation dispatch plan; optionally verifies the red->green gate.

## Description

Every line in this section is binding.

- In planning mode, `implement_pipeline.py` turns a completed deliberation report into a structured implementation dispatch plan: Coder -> Test Writer || Reviewer.
- Planning mode extracts `chosen_approach`, `success_criterion`, and `verification` from the report.
- Planning mode resolves `chosen_approach` to the full candidate object `{id, summary, sketch, rationale}` from the generator step of `deliberation_log` when present; otherwise it falls back to the bare id with `chosen_resolved: false`. This ensures the Coder receives the sketch its input contract promises.
- Planning mode maps the three roles (Coder, Test Writer, Reviewer) to their prompt files and emits a JSON plan for the orchestrating agent to consume.
- The script is a planner, not a dispatcher: `agents/consilium-implement-subagent.md` performs the actual sub-agent calls.
- In gate-verification mode (`--verify-gate`), the script runs the real test suite, expecting GREEN (exit 0).
- Gate-verification mode then rewrites the target file with stub bodies — a heuristic line-scanner that inserts `raise NotImplementedError` after each `def`/`async def` — to confirm the suite fails RED.
- The stub heuristic appends the stub marker as a new line after the `def`/`async def` header; it does not replace an existing `pass` or `...` body, and nested functions each receive their own stub insertion.
- Gate-verification mode restores the original target file content in a `finally` block regardless of outcome.
- The script exits 1 for `do_nothing`/`skipped` chosen approaches, and 2 for malformed input.
- Exit code 1 is shared between `do_nothing`/`skipped` (no pipeline) and gate failure; the caller reads stdout to distinguish the two cases — this collapse is intentional and documented in the script's module docstring.
- stdout in plan mode is a human-readable plan summary followed by `{"plan": ...}` JSON; stdout in gate mode is `{"red_ok": bool, "green_ok": bool, "gate_passed": bool}` JSON.
- Exit code is 0 on success, dry-run, or gate passed; 1 on no-pipeline or gate failure; 2 on bad input.
- The plan JSON schema (`spec`, `sequence`, `roles`, `rules`) is defined entirely by `build_plan()` in this script; the subagent handoff contract lives in `agents/consilium-implement-subagent.md` and is not part of this requirement.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given a report with a non-empty `chosen_approach`, when `build_plan` runs, then it returns a dict with `spec`, `sequence`, `roles`, `rules` keys, each role lists whether its prompt file exists, and `spec.chosen_approach` is the full generator candidate object with `chosen_resolved: true` when resolvable from `deliberation_log`, else the bare id with `chosen_resolved: false`.
- **CASE-2** — Given `chosen_approach` is `do_nothing` or `skipped`, when the script runs, then it prints a message and exits 1.
- **CASE-3** — Given `--verify-gate` mode, when the script runs, then `gate_passed` is `true` only if the real suite passes (exit 0) and the stubbed suite fails (exit non-0).
- **CASE-4** — Given `--verify-gate` mode, when the test command raises or the stubbed run crashes, then `verify_red_green` always restores the original target file content.
- **CASE-5** — Given `--verify-gate` without `--test-cmd` or `--target`, when the script runs, then it exits 2 with an error message to stderr.

## Context (non-binding)

**Notes** — Input: deliberation report JSON via `--input <path>` or stdin; CLI flags `--dry-run`, `--verify-gate`, `--test-cmd`, `--target`, `--stub-marker`. The gate only needs the suite to go RED, not a clean AST rewrite — hence the line-scanner heuristic rather than an AST rewrite.

**Current implementation** — `consilium/scripts/implement_pipeline.py`.
