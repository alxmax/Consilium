---
milestone: v1.1
id: CONSILIUM-IMPLEMENT-TEST-WRITER-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: [CONSILIUM-IMPLEMENT-PIPELINE-001]
satisfies: [ARCH-CONSILIUM-IMPLEMENT-001]
---

# implement-test-writer

> WHY: Separates test authorship from implementation to enable parallel execution and to enforce the Red→Green gate independently. The Test Writer owns test_* files exclusively; implementation files are never touched by this role.

## WHAT — Contract (normative)
- The Test Writer writes `test_*` files only (disjoint-path rule); the Test Writer never writes or edits implementation files.
- Every test emitted satisfies the Red→Green gate: `fails_on_empty_impl` is true for each test — the test fails against a `raise NotImplementedError` stub and passes against the real implementation. A test that passes against the stub is not pinning behavior, and is rejected.
- Test Writer output is strict JSON containing `test_files_written[]` (each entry has `path` and `covers`), `tests[]` (each entry has `name`, `targets_symbol`, `behavior_pinned`, `fails_on_empty_impl`, `why`), and `uncoverable[]`.
- Malformed or non-JSON output is a hard failure; the implement-subagent retries once, then aborts.

## WHAT — Verify intent
- None — all questions resolved.

## HOW — Acceptance (= tests)
AC-1
  Given a well-formed success_criterion and files_written from the Coder
  When  the Test Writer completes
  Then  output parses as JSON, test_files_written is non-empty (every path starts with test_), and every test in tests[] has fails_on_empty_impl = true

AC-2
  Given a test emitted by the Test Writer
  When  the implement-subagent runs the Red→Green gate
  Then  the test is RED against a stub implementation and GREEN against the real one; any test that is green under the stub appears in gate_rejected

AC-3  <!-- verifiable by: inspection -->
  Given a behavior that cannot be covered by automated tests
  When  the Test Writer identifies it
  Then  it appears in uncoverable[] with a reason and no test is emitted for it

## WHERE — Current implementation
- prompts/implement/test_writer.md
- consilium/scripts/validate_implement_output.py
