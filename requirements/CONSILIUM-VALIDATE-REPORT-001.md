---
milestone: v1.0
id: CONSILIUM-VALIDATE-REPORT-001
status: draft
level: code
layer: bus
owner: alxmax
depends_on: [CONSILIUM-PERSONALITIES-001, CONSILIUM-UTILS-001]
risk: 2  # REVIEW
satisfies: [ARCH-CONSILIUM-REPORT-001]
---

# validate_report

> Describes observed behavior, verified against consilium/scripts/validate_report.py source.

## Description

Every line in this section is binding.

- `validate_report.py` reads a deliberation report JSON from stdin, produced by `build_report.py`.
- `validate_report.py` validates report *shape*, not deliberation *substance* — confirming required fields exist and are well-formed. This is the Constitution Principle #4 gate.
- `success_criterion` and `verification` are required to be non-empty strings.
- `chosen_approach` is present and is either a non-empty string or JSON null.
- A missing `chosen_approach` field is an error; an explicit null is accepted.
- Explicit null occurs on a conservative-override veto or on a Trias null-vote pattern; the gate makes no distinction between an intentional and an unintentional null.
- `skipped: true` requires `skip_reason` to be a non-empty string.
- `deliberation_log` contains an aggregate step whose `result` is a dict, not a string narrative.
- For non-bypassed reports, `deliberation_log` also requires the `generator` and `control` steps to be present.
- `deliberation_log`'s `conservator` step presence is not enforced, except when `--strict-round2` is set.
- For a pipeline-executed, non-Trias, non-passthrough report whose aggregate result carries an `admissibility` block, the chosen candidate must be admissible by the report's own log: a `valid: true` Control verdict and (for the `sequential` scheme) `net_concern` not above 0.8. A chosen candidate that is not is an error unless the aggregate result's `admissibility.waived` names it with a non-empty `reason`. Reports without the block (older runs) are not judged.
- `telemetry` is present for non-skipped reports and carries a non-empty `mode` string.
- Telemetry count fields (`tokens_in`, `tokens_out`, `latency_ms`) are non-negative ints, checked strictly via `isinstance(v, int)`; a float value such as `1500.0` is rejected.
- Each telemetry count field is optional per voice.
- Reports assembled manually outside `build_report.py` are rejected by this gate, which catches shape drift such as `aggregate.result` written as a narrative string.
- Exit 0 means the report is valid; exit 1 means validation failed, with each problem printed to stderr; exit 2 means the JSON input is malformed.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given a valid report from `.consilium/runs/*.json`, when `validate_report.py` runs, then it exits 0.
- **CASE-2** — Given a report missing `success_criterion`, when `validate_report.py` runs, then it exits 1 with a message naming the field.
- **CASE-3** — Given `skipped: true` without `skip_reason`, when `validate_report.py` runs, then it exits 1.
- **CASE-4** — Given a non-skipped report missing `telemetry.mode`, when `validate_report.py` runs, then it exits 1.
- **CASE-5** — Given malformed JSON input, when `validate_report.py` runs, then it exits 2.

## Context (non-binding)

**Current implementation** — `consilium/scripts/validate_report.py`.
