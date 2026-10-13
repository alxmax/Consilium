---
milestone: v1.2
id: CONSILIUM-VERSION-001
status: confirmed
level: code
layer: bus
owner: alxmax
depends_on: []
risk: 1
satisfies: [ARCH-CONSILIUM-REPORT-001]
---

# version

> Repo version provenance: git-describe display stamp, resolvable committed-HEAD ref, and a guarded prompt-drift counter — the primitives every report producer stamps into telemetry.

## Description

Every line in this section is binding.

- `consilium/scripts/version.py` is the single home for version provenance, separated from report assembly (`build_report.py`, which only consumes these values).
- `consilium_version()` returns the human display stamp from `git describe --tags --always --dirty`, and fails open to `"unknown"` when git is absent or errors — it never raises.
- `consilium_ref()` returns the resolvable diff operand: the committed HEAD sha on a clean tree.
- `consilium_ref()` returns `""` on a dirty or unknown tree — by contract, never a `<sha>-dirty` string — so a recorded ref is always `git checkout`-able.
- `ref_resolves(ref)` returns a bool, short-circuiting `""` and `"unknown"` to `False` without a git call.
- `prompts_changed_since(ref)` counts prompt/mode files changed since a prior ref and never raises: it returns 0 on `""`, `"unknown"`, or an unreachable ref.
- `prompts_changed_since` lets the Step-0 `prompt_drift` advisory call it unconditionally.
- The CLI supports `--version` (default), `--ref`, and `--drift <ref>` flags, and prints the requested value to stdout with exit 0.
- This split was retagged out of `CONSILIUM-BUILD-REPORT-001` on 2026-07-03 (review backlog-disposition audit, item b) because impact analysis on the report assembler was pulling in unrelated provenance code; origin: review 2026-05-31_200016 (versioning-provenance-design).

## Verify intent

- None - the report-stamping obligation (every producer writes these two fields into telemetry) belongs to CONSILIUM-BUILD-REPORT-001 and the two hand-built SKILL.md templates; this requirement covers only the provenance primitives themselves.

## Cases

- **CASE-1** — Given `_git` stubbed to fail, when `consilium_version()`, `consilium_ref()`, `ref_resolves("abc")`, and `prompts_changed_since("abc")` run, then they return `"unknown"`, `""`, `False`, and `0` respectively (`scripts/test_version.py`).
- **CASE-2** — Given a dirty-tree stub, when `consilium_ref()` runs, then it returns `""`; given a clean-tree stub, then it returns the HEAD sha.
- **CASE-3** — Given `ref_resolves("")` and `ref_resolves("unknown")`, when they run, then both return `False` without a git call.
- **CASE-4** — Given a real repo, when `consilium_version()` runs, then it returns a non-empty string.

## Context (non-binding)

**Notes** — Reads the git repository state via subprocess (`git describe`, `git status --porcelain`, `git rev-parse`).

**Current implementation** — `consilium/scripts/version.py`.

<!-- verified-by: scripts/test_version.py -->
