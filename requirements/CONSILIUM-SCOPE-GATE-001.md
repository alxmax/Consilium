---
milestone: v1.0
id: CONSILIUM-SCOPE-GATE-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: []
risk: 1
satisfies: [ARCH-CONSILIUM-REPORT-001]
---

# scope_gate

> Decides whether a change is small enough to bypass full deliberation (fails open), and whether it needs explicit consent before any voice runs (fails safe).

## Description

Every line in this section is binding.

- `scope_gate.py` decides whether a change is small enough to bypass full deliberation.
- `scope_gate.py` collects diff signals from git via `probe_change.py`. The default is `HEAD`; `--ref <ref>..HEAD` and `--range <A>..<B>` are alternative diff selectors.
- Alternatively, when `--signals-stdin` is set, `scope_gate.py` reads pre-computed signals as stdin JSON (`{files_changed, lines_added, lines_removed, paths}`) instead of running git.
- `--files` optionally restricts the git diff to a path.
- `--config` optionally points to a `scope_gate.json` overriding `max_files`, `max_lines`, and `blocklist`.
- `CONSILIUM_FORCE_FULL=1` forces `should_skip=false` and `magnitude='critical'` without reading the diff.
- `scope_gate.py` checks file and line counts against the configured thresholds, and scans changed paths against a sensitive-path blocklist.
- `scope_gate.py` classifies the change's magnitude as one of `low`, `medium`, `high`, `critical`.
- `scope_gate.py` derives a `mode_ceiling` — the maximum deliberation mode the magnitude allows.
- `scope_gate.py` outputs a JSON decision the orchestrator uses to short-circuit or proceed.
- The gate fails open on the cost check: probe failures, missing git repos, and config load errors all produce `should_skip=false`, so an uncertain situation always triggers deliberation rather than silently skipping it.
- Any path matching a blocklist entry forces `should_skip=false`, `magnitude='critical'`, and `mode_ceiling='trias'`, regardless of file or line counts.
- The same probe derives `consent_required` — a pre-dispatch irreversibility consent gate.
- Because the Generator voice now runs first, `consent_required` lets the orchestrator request explicit user consent before any voice runs, so generation effort is never spent on a change the user might abort.
- `consent_required` is `true` for sensitive/irreversible (blocklist) paths, and `false` for an ordinary non-sensitive change.
- Unlike `should_skip`, `consent_required` fails safe: an undeterminable change returns `consent_required=true` rather than silently bypassing consent.
- Output is a JSON object to stdout with keys `should_skip`, `consent_required`, `magnitude`, `mode_ceiling`, `reason`, `signals`, `config_used`.
- Exit code is always 0; errors are reported inside the JSON, not via a non-zero exit.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given a single-file, single-line change with no blocklist hits and default config, when the gate runs, then it returns `should_skip=true` and `magnitude='low'`.
- **CASE-2** — Given a path matching a blocklist pattern, when the gate runs, then it returns `should_skip=false`, `magnitude='critical'`, and `mode_ceiling='trias'` regardless of file/line counts.
- **CASE-3** — Given `CONSILIUM_FORCE_FULL=1`, when the gate runs, then it returns `should_skip=false` and `magnitude='critical'` without reading the diff.
- **CASE-4** — Given `--signals-stdin` with a pre-computed payload, when the gate runs, then it bypasses git and classifies magnitude purely from the payload values.
- **CASE-5** — Given a probe failure (e.g. not a git repo), when the gate runs, then it returns `should_skip=false` with the error text in the `reason` field and exits 0.
- **CASE-6** — Given a blocklist (sensitive/irreversible) path, an ordinary non-sensitive change, and a probe failure, when the gate evaluates `consent_required`, then it returns `true`, `false`, and `true` respectively — the probe failure fails safe, the opposite direction from `should_skip` (`scripts/test_consent_gate.py`).

## Context (non-binding)

**Notes** — None beyond the Description above.

**Current implementation** — `consilium/scripts/scope_gate.py`
