---
milestone: v1.0
id: CONSILIUM-BUILD-REPORT-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: [CONSILIUM-UTILS-001]
risk: 2
satisfies: [ARCH-CONSILIUM-REPORT-001]
---

# build_report

> Assembles the canonical deliberation report shape from intermediate voice/aggregation outputs.

## Description

Every line in this section is binding.

- `build_report.py` assembles the canonical deliberation report shape from an input JSON bundle containing `success_criterion`, `verification`, `generator`, `control`, `conservator`, `aggregate`, and `confidence`.
- Missing any of those required keys exits with code 1.
- `build_report.py` reads the bundle from stdin, or from the file named by `--input` (default: stdin).
- `--input` and stdin are mutually exclusive by argparse design: `FileType` defaults to stdin, and providing `--input` opens the file instead. No conflict resolution is needed.
- `build_report.py` extracts `voice_scores` for the chosen candidate from the Control verdict and the Conservator score lists.
- `build_report.py` derives a `why_not` summary for each non-chosen alternative from Control issues and Conservator risk: an invalid control verdict lists its issue categories; a valid verdict with issues uses the first issue's detail; a Conservator `net_concern >= 0.5` appends `risk=N.NN`.
- When neither source yields text, `why_not` falls back to `"ranked below chosen"`, or to `"all candidates vetoed"` when `chosen` is null.
- `build_report.py` stamps `consilium_version` and `consilium_ref` from the version module into the telemetry block of every non-skipped report it emits.
- Skipped reports (trivial-direct, prior-deliberation passthrough) go through a separate code path that requires only `skip_reason` and `signals`.
- `pipeline_executed` is absent on skipped reports; `validate_report.py` skips that field check entirely when `skipped: true`. Full-pipeline reports always set `pipeline_executed: true`.
- `validate_report.py` gates every report before the orchestrator writes it to `.consilium/runs/`.
- `build_report.py` writes to stdout a canonical JSON report with fields `success_criterion`, `verification`, `chosen_approach`, `reasoning`, `alternatives`, `voice_scores`, `confidence`, `pipeline_executed`, `deliberation_log`, `telemetry`, and optional Trias fields (`team`, `personalities`, `vote_pattern`, `dissent`, `abstained`, `personality_choices`).
- `build_report.py` exits 0 on success, exits 1 on a missing required field, and exits 2 on malformed JSON input.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given a well-formed full bundle, when `build_report.py` runs, then the output contains `pipeline_executed: true` and a `deliberation_log` array with entries for the `generator`, `control`, `conservator`, and `aggregate` steps.
- **CASE-2** — Given a skipped bundle (`skipped: true`) with a valid `skip_reason`, when `build_report.py` runs, then the output contains `chosen_approach: skipped`, `pipeline_executed` absent or false, and `deliberation_log: []`.
- **CASE-3** — Given a bundle where the chosen candidate's control verdict has `valid=false` with issues, when `build_report.py` runs, then `voice_scores.control` is below 1.0 and the alternatives list a `why_not` string derived from those issues.
- **CASE-4** — Given any valid bundle, when `build_report.py` runs, then the telemetry block contains a non-empty `consilium_version` and a `consilium_ref` that is either the committed HEAD sha or `""` on a dirty/unknown tree (the version-module contract — see CONSILIUM-VERSION-001), both stamped by the version module.
- **CASE-5** — Given a bundle missing `success_criterion`, when `build_report.py` runs, then it exits with code 1 and prints an error to stderr without writing any JSON to stdout.

## Context (non-binding)

**Current implementation** — `consilium/scripts/build_report.py`.
