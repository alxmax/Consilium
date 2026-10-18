---
milestone: v1.0
id: CONSILIUM-AGGREGATOR-001
status: draft
level: code
layer: feature
owner: alxmax
depends_on: [CONSILIUM-UTILS-001]
risk: 2
satisfies: [ARCH-CONSILIUM-REPORT-001]
---

# aggregator

> Merges scored Generator/Control/Conservator outputs into a chosen candidate via one of five aggregation schemes.

## Description

Every line in this section is binding.

- `aggregator.py` merges the scored outputs of the Generator, Control, and Conservator voices into a single chosen candidate and ranking, using one of five schemes selected by the `--scheme` flag (default `conservative_override`).
- The `majority` scheme picks the candidate with the highest mean voice score.
- The `conservative_override` scheme vetoes any candidate whose Conservator risk exceeds `veto_threshold`, then ranks survivors by a weighted utility that flips Conservator into a safety signal.
- The `risk_adjusted_utility` scheme applies a smooth sigmoid penalty instead of a hard veto, so candidates clustered near the threshold rank gracefully.
- The `team_vote` scheme implements the democratic majority-vote logic used in Trias mode: it derives a vote pattern — one of `3-0`, `2-1`, `2-0`, `1-1-1`, `0-0-0` — from three personality sub-agents' chosen-IDs.
- The `sequential` scheme is the authoritative single-context aggregation path: it applies a priority-ordered veto cascade (`glossary_fail` -> `irreversibility_flag` -> `escalate` -> `rework` -> `adapt_short`/`extend` -> `aggregate`) over raw voice output dicts rather than numeric scores.
- `aggregator.py` reads input from stdin, or from the file named by `--input` (default: stdin), as a JSON object with a `candidates` array and optional `weights`, `veto_threshold`, `personalities` keys; the exact schema varies by scheme.
- `aggregator.py` writes a JSON object to stdout with `scheme`, `chosen`, and `ranking`, plus scheme-specific fields drawn from `vetoed`, `vote_pattern`, `dissent`, `retry_suggested`, `low_separation`, `veto_uncertain`.
- `aggregator.py` exits 0 on success and exits non-zero (a raised `ValueError`) on invalid input.
- `conservative_override` with `auto_relax=False`, when all candidates are vetoed, returns `{"chosen": null, "reason": "all candidates vetoed by conservator or rejected by Control", "vetoed": [...]}` with no `retry_suggested` field.
- `conservative_override` also excludes a candidate Control did not clear — `valid: false`, or a `control` score of 0 or less (the encoding `build_report.py` gives an invalid or never-evaluated candidate) — and lists it in `vetoed` with `reason: "control_invalid"`. When no candidate passed Control the result sets `escalation_required` and no `retry_suggested`, since relaxing the risk threshold cannot help.
- The `sequential` scheme runs an admissibility check on the Generator's `preferred` before AGGREGATE: no Control verdict (`not_evaluated`), a verdict that is not `valid: true` (`invalid`), or `net_concern` above `0.8` (`vetoed`, strict) yields `REWORK` with `reason: "preferred_inadmissible"`, `chosen: null`, `inadmissible_reasons` and the `admissible_alternatives`. An optional `waiver` `{id, reason}` (non-empty reason, naming the preferred id) lets the pick proceed and is recorded in `admissibility.waived`. `scale_down` skips Control by design and is exempt. Every successful `sequential` and `conservative_override` result carries `admissibility: {checked: true}`.
- The `sequential` scheme's input schema is three top-level keys — `generator`, `control`, `conservator` — holding raw voice output dicts; the function reads only the raw-dict keys (`glossary_fail`, `disagreements`, `scores[]`, `preferred`, `abstain`). No mixed numeric-score input is defined; passing numeric scores alongside raw dicts is undefined behavior.
- All seven sequential routing outcomes (BLOCK/glossary_fail, BLOCK/irreversibility_no_consent, ESCALATE, REWORK, ADAPT_SHORT, ADAPT_EXTENDED, AGGREGATE) are tested in `scripts/test_round2.py`.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given a candidates list where every candidate's Conservator score exceeds `veto_threshold` and `auto_relax=True`, when `conservative_override` runs, then the output contains `chosen: null` and a non-empty `retry_suggested` block.
- **CASE-2** — Given two candidates with identical generator and control scores but different Conservator risk, when `conservative_override` ranks them, then the candidate with lower risk ranks first.
- **CASE-3** — Given `vote_pattern='2-1'` with three personalities where two of them choose the same candidate, when `team_vote` runs, then `chosen` equals the majority candidate and `dissent` is non-empty.
- **CASE-4** — Given sequential input where `control_out['glossary_fail']` is `True`, when the `sequential` scheme runs, then the output has `result: BLOCK` and `reason: glossary_fail`, regardless of other signals.
- **CASE-5** — Given three or more simultaneous triggers, when the `sequential` scheme runs, then the output has `result: ESCALATE` with a `triggers` list of length >= 3.
- **CASE-6** — Given a sequential input whose preferred candidate has `valid: false`, no Control verdict, or `net_concern` above 0.8, when `sequential` runs, then the result is `REWORK` with `chosen: null`; with a matching `waiver` the result is `AGGREGATE` and `admissibility.waived` records the reason.
- **CASE-7** — Given a candidate with the best generator and safety scores but a `control` score of 0, when `conservative_override` runs, then it is not chosen and appears in `vetoed` with `reason: "control_invalid"`.

## Context (non-binding)

**Current implementation** — `consilium/scripts/aggregator.py`, tested in `scripts/test_round2.py`.
