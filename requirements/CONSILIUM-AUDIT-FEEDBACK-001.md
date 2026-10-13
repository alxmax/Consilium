---
id: CONSILIUM-AUDIT-FEEDBACK-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: [CONSILIUM-FEEDBACK-001, CONSILIUM-UTILS-001]
risk: 1
test_exempt: integration-only — depends on live FEEDBACK.html + runs/; acceptance-tested via --dry-run and manual backfill
satisfies: [ARCH-CONSILIUM-LEARNING-001]
---

# Orphan run detection and PEND backfill

> Finds `.consilium/runs/*.json` files that have no matching row in `FEEDBACK.html` (orphans created when step 6 log is skipped) and optionally backfills them with default PEND rows so `priors.py` can surface them.

## WHAT — Contract

- Without flags, `audit_feedback.py` lists orphan runs (runs with no FEEDBACK.html row) and exits 0.
- With `--backfill`, `audit_feedback.py` appends one PEND row per orphan to `FEEDBACK.html`, using the same note-derivation as `log_feedback.py`.
- `audit_feedback.py` never overwrites an existing row — a run is considered matched if any row shares the same date AND chosen_approach prefix.
- With `--dry-run`, `audit_feedback.py` prints the rows that would be appended without writing.
- Backfill outcome is always PEND (never retroactively OK); the user closes them via the standard PEND→OK/BAD prompt at the next step 0.

## WHAT — Verify intent (open questions for the human)

- None — contract matches docstring and SKILL.md Step 0 prose exactly.

## HOW — Acceptance (= tests)

- Given a run file with no FEEDBACK row, `audit_feedback.py` lists it; `--backfill` appends a PEND row; re-run lists nothing (idempotent).
- Given a run file with an existing row, `--backfill` does not duplicate it.
- Given `--dry-run`, no write occurs to FEEDBACK.html.

## WHERE — Current implementation

- consilium/scripts/audit_feedback.py
<!-- implements: CONSILIUM-AUDIT-FEEDBACK-001 -->
