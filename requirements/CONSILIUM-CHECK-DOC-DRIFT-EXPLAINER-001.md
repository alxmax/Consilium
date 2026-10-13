---
milestone: v1.1
id: CONSILIUM-CHECK-DOC-DRIFT-EXPLAINER-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: []
satisfies: [ARCH-CONSILIUM-REPO-GATES-001]
risk: 1
---

# check_doc_drift — explainer parity checks

> The three `check_doc_drift.py` check families that keep the architecture explainer (`docs/architecture/src/*.jsx`) in step with its sources of truth. All three are pure functions of file text, so they are unit-tested directly; the parent [[CONSILIUM-CHECK-DOC-DRIFT-001]] owns the integration-only families and the script's exit-code contract.

## Description

Every line in this section is binding.

- **CI_CHECKS completeness** (`check_ci_checks_completeness`): every named non-test `ci.yml` step is represented by a card in the explainer's `CI_CHECKS` list (`extras.jsx`), or by a named `ALLOWED_OUT_OF_SCOPE_CI_STEPS` entry.
- The completeness check matches on the invoked script's exact basename (e.g. `reqmap.py`), not the full run-line. Two steps that share one script under different flags therefore resolve to one card.
- `scripts/test_*.py` steps are always skipped, because the "Unit suites" card covers them generically. A step with no `scripts/*.py` or `docs/architecture/build.py` reference needs an `ALLOWED_OUT_OF_SCOPE_CI_STEPS` entry, or the check fails.
- **Trias personality-name parity** (`check_trias_personality_name_parity`): the `PERSONALITIES` names in `consilium/scripts/personalities.py` (the single source of truth) match `trias.jsx`'s `LENSES`, `modes.jsx`'s personalities array and `make_full_architecture.py`'s `personalities_row`.
- The name comparison is case-insensitive, since `personalities.py` uses lowercase and the explainer uses Title Case. Each of the three sources is compared separately, so a drift in one is reported for that file alone.
- **Implement-pipeline spec alignment** (`check_implement_pipeline_spec_alignment`): the `subagents` and `cost_multiplier` frontmatter of `modes/implement_pipeline.md` both appear in `extras.jsx`'s `GATE_ITEMS` (the ImplementSection).
- The alignment check formats the multiplier through `check_trias_spec_alignment`'s explicit `_COST_FMT` float→string map, never `f'{v}×'`. A missing count and a missing multiplier are reported as two independent failures.

## Verify intent

- None - contract moved verbatim from CONSILIUM-CHECK-DOC-DRIFT-001, which the owner had confirmed.

## Cases

- **CASE-1** — Given a named `ci.yml` step invoking a script with no `CI_CHECKS` card and no `ALLOWED_OUT_OF_SCOPE_CI_STEPS` entry, when `check_ci_checks_completeness` runs, then it reports a failure naming the step and the script.
- **CASE-2** — Given two `ci.yml` steps invoking the same script under different flags and one card naming that script, when `check_ci_checks_completeness` runs, then it reports no failure.
- **CASE-3** — Given `trias.jsx`'s `LENSES`, `modes.jsx`'s personalities array or `make_full_architecture.py`'s `personalities_row` regressed to a retired name (e.g. `Pioneer`), when `check_trias_personality_name_parity` runs, then it reports a failure naming the offending file.
- **CASE-4** — Given `extras.jsx`'s `GATE_ITEMS` missing the sub-agent-count or the cost-multiplier string, when `check_implement_pipeline_spec_alignment` runs, then it reports the matching failure(s). Given `modes/implement_pipeline.md` missing either frontmatter field, the script exits 2.

## Context (non-binding)

**Notes** — All three families were added on 2026-07-06 after a Trias self-audit. Each covers a drift that had already happened: the explainer's "what CI runs" list had fallen behind `ci.yml`, the v3 lens rename (PR #482) never touched the explainer or the poster, and the implement pipeline was the only mode whose sub-agent count and cost were missing from its own section. They were split out of the parent on 2026-09-21, when requirement-manager 8.0.0 capped a requirement at 7 acceptance criteria.

**Current implementation** — `scripts/check_doc_drift.py`, tested in `scripts/test_check_doc_drift.py`.
