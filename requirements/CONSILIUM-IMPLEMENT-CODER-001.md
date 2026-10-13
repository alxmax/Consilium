---
milestone: v1.1
id: CONSILIUM-IMPLEMENT-CODER-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: [CONSILIUM-IMPLEMENT-PIPELINE-001]
satisfies: [ARCH-CONSILIUM-IMPLEMENT-001]
---

# implement-coder

> WHY: Isolates implementation from test-writing so the two roles can run in parallel without file conflicts and so the Red→Green gate has a clean stub to test against. The Coder owns all implementation paths and never touches test files.

## WHAT — Contract (normative)
- The Coder writes the minimum code satisfying `chosen_approach + success_criterion`, using only the Write tool; the Coder does not write test files (disjoint-path rule — `test_*` paths belong to the Test Writer).
- Coder output is strict JSON containing `files_written[]` (each entry has `path`, `purpose`, `symbols[]`) and `maps_to_criterion` (one sentence describing how the written code satisfies the success criterion).
- If `chosen_approach.sketch` is insufficient to implement without guessing a missing decision, the Coder sets `blocked: true` with a non-null `blocked_reason` describing the specific missing decision; the Coder does not fabricate intent.
- Any file that the Coder would touch outside the paths specified by `chosen_approach` / `files_touched` is reported in `scope_escapes[]`, and the Coder does not edit that file.
- Malformed or non-JSON output is a hard failure; the implement-subagent retries the dispatch once, then aborts.

## WHAT — Verify intent
- None — all questions resolved.

## HOW — Acceptance (= tests)
AC-1
  Given a well-formed chosen_approach and success_criterion
  When  the Coder completes
  Then  output parses as JSON with non-empty files_written, non-empty maps_to_criterion, and blocked = false

AC-2
  Given a chosen_approach with an incomplete sketch (insufficient to implement without guessing)
  When  the Coder processes the input
  Then  blocked = true and blocked_reason is a non-null, non-empty string; no files are written

AC-3
  Given a task that would require touching a path outside files_touched
  When  the Coder detects the scope escape
  Then  the out-of-scope path appears in scope_escapes[], the Coder stops before writing it, and the path does not appear in files_written

## WHERE — Current implementation
- prompts/implement/coder.md
- consilium/scripts/validate_implement_output.py
