---
milestone: v1.1
id: CONSILIUM-CONFIDENCE-CALIBRATION-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: [CONSILIUM-FEEDBACK-001]
satisfies: [ARCH-CONSILIUM-LEARNING-001]
risk: 1
---

# confidence_calibration

> Decides from logged outcomes whether high confidence actually predicts success, which is the evidence that lets Trias's post-vote Skeptic become confidence-gated (Variant C) instead of unconditional (Variant A).

## Description

Every line in this section is binding.

- `confidence_calibration.py` reads `.consilium/FEEDBACK.html` through `feedback.py`'s parser.
- `confidence_calibration.py` keeps only rows that are resolved (a success or failure outcome) and carry a `conf=<x>` value in their note.
- A row whose confidence lies outside 0.0–1.0, or whose outcome is still pending, is left out of every count.
- The script splits the kept rows at `--gate` (default 0.7) into a low band and a high band and computes each band's OK-rate.
- The verdict is `INSUFFICIENT_DATA` when there are fewer than 20 resolved rows, fewer than 10 failures, or fewer than 5 rows in either band. Each defaults to a flag.
- Otherwise the verdict is `SHIP_C` when the high band beats the low band by at least `--margin` (default 0.15) and reaches `--high-floor` (default 0.75), and `FALLBACK_A` in every other case.
- The script prints a per-bin table, or JSON under `--json`, and never writes a file.

## Verify intent

- None - resolved 2026-09-27: the verdict is advisory. `modes/trias.md` now says switching the Trias default from A to C is a maintainer's edit made once this script returns `SHIP_C`; no code reads the verdict at dispatch time.

## Cases

- **CASE-1** — Given entries mixing resolved, pending and untagged rows, when `calibration_records` runs, then only the resolved rows with a `conf=` value are returned.
- **CASE-2** — Given records where the high band is clearly more successful than the low band, when `decide` runs, then the verdict is `SHIP_C`.
- **CASE-3** — Given records where both bands succeed at the same rate, when `decide` runs, then the verdict is `FALLBACK_A`.
- **CASE-4** — Given fewer resolved records than `min_resolved`, or no failures at all, when `decide` runs, then the verdict is `INSUFFICIENT_DATA`.

## Context (non-binding)

**Current implementation** — `scripts/confidence_calibration.py`, tested in `scripts/test_confidence_calibration.py`.
