---
milestone: v1.1
id: CONSILIUM-CHECK-DOC-DRIFT-001
status: confirmed
level: code
layer: feature
owner: alxmax
test_exempt: "reads live source files and runs git — integration-only gate"
depends_on: []
risk: 1
satisfies: [ARCH-CONSILIUM-REPO-GATES-001]
---

# check_doc_drift

> Enforces parity between authoritative behavior (SKILL.md, confidence.py) and the docs/diagrams.

## Description

Every line in this section is binding.

- `check_doc_drift.py` enforces parity between the authoritative behavior (`SKILL.md`, `scripts/confidence.py`) and the human-readable documentation (`modes/*.md`, `docs/architecture/src/*.jsx`).
- This prevents the class of silent drift found in the design audit of 2026-05-28, where four discrepancies had accumulated undetected.
- `check_doc_drift.py` runs seven independent check families.
- The first family is text-based regex invariants: required/forbidden patterns in specific files.
- The second family is Trias confidence parity, comparing `confidence.py`'s `VOTE_PATTERN_CONFIDENCE` dict (parsed via AST) against the `TRIAS_OUTCOMES` table in `trias.jsx` (parsed via regex).
- The third family is legacy MODE alias removal milestone enforcement: dated removal comments accompany deprecated aliases in `validate_report.py`.
- The fourth family is test-suite coverage: every `scripts/test_*.py` file appears in both `ci.yml` and the run-consilium driver.
- The fifth family, CI_CHECKS completeness, requires every non-test `ci.yml` step to be represented in the architecture explainer's `CI_CHECKS` card list, matched by exact script basename; it was added 2026-07-06 after a Trias self-audit found the explainer's own "what CI runs" section had silently fallen behind `ci.yml` itself.
- The sixth family, Trias personality-name parity, requires `scripts/personalities.py`'s `PERSONALITIES` names to match the explainer's `trias.jsx`/`modes.jsx` and the `make_full_architecture.py` poster generator; it was added 2026-07-06 after the v3 lens rename (PR #482) was found to have never touched those three files.
- The seventh family, implement-pipeline spec alignment, requires `modes/implement_pipeline.md`'s `subagents`/`cost_multiplier` frontmatter to be stated explicitly in the "Code integration pipeline" explainer section's `GATE_ITEMS`; it was added 2026-07-06 after that section was found to be the only mode/flag whose headline sub-agent count and cost multiplier weren't shown anywhere in its own text.
- The CI_CHECKS completeness, personality-name parity, and implement-pipeline alignment families are specified in [[CONSILIUM-CHECK-DOC-DRIFT-EXPLAINER-001]].
- `check_doc_drift.py` is intended to run before any commit that touches `modes/`, `docs/architecture/src/`, `scripts/confidence.py`, `scripts/personalities.py`, `.github/workflows/ci.yml`, or `scripts/test_*.py`.
- `check_doc_drift.py` reads `modes/trias.md` for the `trias_parallel_dispatch` and `trias_parallelism_runtime_audit` invariants.
- `check_doc_drift.py` reads `modes/sequential.md` for the `sequential_scale_down_skips_control` and `sequential_generator_first` invariants.
- `check_doc_drift.py` reads `docs/architecture/src/modes.jsx` for the `trias_tally_caption_confidence` and `explainer_modes_voices_generator_first` invariants, and for the Trias spec-alignment worst-case check.
- `check_doc_drift.py` reads `docs/architecture/src/trias.jsx` for the `TRIAS_OUTCOMES` confidence parity check.
- `check_doc_drift.py` reads `docs/architecture/src/extras.jsx` for the Trias spec-alignment check (the CostScatter TRI entry and the CostBars trias row).
- `check_doc_drift.py` reads `SKILL.md` for the `skill_templates_have_pipeline_executed` invariant.
- `check_doc_drift.py` reads `scripts/build_report.py` for the `build_report_emits_pipeline_executed` invariant.
- `check_doc_drift.py` AST-parses `scripts/confidence.py` for the `VOTE_PATTERN_CONFIDENCE` dict values.
- `check_doc_drift.py` reads `scripts/validate_report.py` for the legacy MODE alias removal milestone check.
- `check_doc_drift.py` reads `.github/workflows/ci.yml` and `.claude/skills/run-consilium/driver.py` for the test-suite coverage check.
- `check_doc_drift.py` globs `scripts/test_*.py` to enumerate all test suites requiring coverage.
- `check_doc_drift.py` parses `.github/workflows/ci.yml` and `docs/architecture/src/extras.jsx` for the `ci_checks_completeness` check.
- `check_doc_drift.py` AST-parses `scripts/personalities.py` for the `PERSONALITIES` list (name SSOT), used by the `trias_personality_name_parity` check.
- `check_doc_drift.py` regex-scans `docs/architecture/src/trias.jsx`, `docs/architecture/src/modes.jsx`, and `scripts/make_full_architecture.py` for Trias personality names, comparing them against `personalities.py`.
- `check_doc_drift.py` regex-parses `modes/implement_pipeline.md` for the `subagents`/`cost_multiplier` frontmatter (SSOT), used by the `implement_pipeline_spec_alignment` check.
- `check_doc_drift.py` scans `docs/architecture/src/extras.jsx`'s `GATE_ITEMS` array (ImplementSection) for the matching sub-agent-count / cost-multiplier strings.
- `check_doc_drift.py` prints `doc-drift OK: all invariants hold` to stdout when all checks pass.
- On failure, `check_doc_drift.py` prints a numbered list of violated invariants to stderr, each with its pattern, source, and rationale.
- `check_doc_drift.py` exits 0 when all invariants pass, exits 1 when one or more are violated, and exits 2 when a required input file is missing.
- Test-suite coverage uses plain substring match on the filename only (e.g., `test_round2.py`); a commented-out line that still contains the filename string passes the check — the script does not distinguish commented-out from active.
- The legacy MODE alias removal milestone date is ISO `YYYY-MM-DD` and appears within 200 characters of the alias literal in `validate_report.py`; any comment syntax is accepted as long as the date string is present, and future dates are accepted — the check only skips once the alias has been removed from the file entirely.
- When multiple invariants are violated, all violations are collected across all seven check families before any output; the script prints every violation (numbered) to stderr then exits 1 — it never stops at the first failure.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given all invariant patterns hold and `confidence.py`'s `VOTE_PATTERN_CONFIDENCE` matches `trias.jsx`'s `TRIAS_OUTCOMES` for patterns `3-0`/`2-1`/`2-0`, when `check_doc_drift.py` runs, then it exits 0 and prints the OK message.
- **CASE-2** — Given the scale_down wording in `modes/sequential.md` regresses to "Skip Generator AND Control", when `check_doc_drift.py` runs, then the `sequential_scale_down_skips_control` invariant fails and the script exits 1.
- **CASE-3** — Given `confidence.py`'s `VOTE_PATTERN_CONFIDENCE['2-1']` is changed to a value that differs from the `conf` field of the `2-1` row in `trias.jsx`'s `TRIAS_OUTCOMES`, when `check_doc_drift.py` runs, then the trias confidence parity check reports a failure.
- **CASE-4** — Given a new `scripts/test_*.py` file added without a corresponding entry in `ci.yml`, when `check_doc_drift.py` runs, then the `test_suite_coverage` check fails and the script exits 1.
- **CASE-5** — Given a required file listed in an invariant's `file` key is missing from disk, when `check_doc_drift.py` runs, then it exits 2 immediately.

## Context (non-binding)

**Current implementation** — `scripts/check_doc_drift.py`.

## Why test_exempt

`check_doc_drift.py` reads live source files and runs `git` commands — its correctness depends on the actual repo tree having specific file states (mode docs, architecture JSX, `confidence.py` constants, CI config). Simulating that tree faithfully in a fixture would be more complex and brittle than the script itself for most of its check families. The CI step against the actual repo IS the acceptance test for those. The `ci_checks_completeness`, `trias_personality_name_parity`, and `implement_pipeline_spec_alignment` check families are exceptions — all are pure functions of file text, specified in CONSILIUM-CHECK-DOC-DRIFT-EXPLAINER-001 and unit-tested directly in `scripts/test_check_doc_drift.py`.

<!-- verified-by: scripts/test_check_doc_drift.py -->
