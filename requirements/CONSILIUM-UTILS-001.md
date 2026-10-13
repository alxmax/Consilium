---
milestone: v1.0
id: CONSILIUM-UTILS-001
status: confirmed
level: code
layer: bus
owner: alxmax
depends_on: []
risk: 0
satisfies: [ARCH-CONSILIUM-REPORT-001]
---

# utils

> Shared stdlib-only utilities: canonical paths, atomic writes, stdin JSON, headless detection.

## Description

Every line in this section is binding.

- `consilium/scripts/utils.py` provides shared stdlib-only utilities that every other Consilium script imports instead of defining its own copies.
- `DATA_DIR` resolves to `$CONSILIUM_DATA_DIR` (made absolute) when that variable is set to a non-blank value, and otherwise to `.consilium/` under the current working directory, which is the project the orchestrator writes its reports to.
- `RUNS_DIR` resolves to `runs/` under `DATA_DIR`.
- `FEEDBACK_PATH` resolves to `FEEDBACK.html` under `DATA_DIR`.
- `DATA_DIR` never depends on where `consilium/scripts/utils.py` is installed: a plugin cache or an APM-deployed skill folder is replaced on every update, so state kept there would reset each version.
- `atomic_write_text(path, content)` writes the given string content to `path` atomically, through a sibling `.tmp` file with fsync and rename.
- A read-only parent directory makes `atomic_write_text` raise `OSError`, which propagates to the caller.
- `atomic_write_text` deletes the temp file on any error path, so no stale `.tmp` file persists across crashes.
- `load_json_stdin` reads and parses JSON from stdin.
- `load_json_stdin` exits code 2 on empty stdin or a parse failure.
- `issue_penalty(severity)` returns a float score penalty for an issue dict's severity: `0.05` for `low`, `0.15` for `medium` or a missing severity, `0.30` for `high`.
- `validate_keys(data, keys)` checks a data dict against a required-keys list and raises `ValueError` on a schema violation; callers map that to exit 1 or 2.
- `is_headless()` reads the `CLAUDE_HEADLESS` environment variable and returns `True` only when it equals the string `'1'`; any other value, including `'true'`, `'0'`, or empty, returns `False`.
- `force_utf8_streams` guards script stdout/stderr against Windows cp1252 encoding errors.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given `CONSILIUM_DATA_DIR` is unset or blank, when a script imports `DATA_DIR`, `RUNS_DIR`, or `FEEDBACK_PATH`, then they point to `.consilium/`, `.consilium/runs/`, and `.consilium/FEEDBACK.html` under the current working directory; given it names a directory, then they point to that directory, its `runs/`, and its `FEEDBACK.html`.
- **CASE-2** — Given `atomic_write_text` is interrupted mid-write, when the write fails, then the original file is left intact and no truncated or stale `.tmp` file persists.
- **CASE-3** — Given `CLAUDE_HEADLESS` is unset or holds any value other than `'1'` (including `'true'` or `'0'`), when `is_headless` runs, then it returns `False`; given it equals `'1'`, then it returns `True`.
- **CASE-4** — Given empty stdin or invalid JSON, when `load_json_stdin` runs, then it prints a diagnostic message to stderr and exits code 2.
- **CASE-5** — Given a severity of `low`, `medium`, a missing severity, or `high`, when `issue_penalty` runs, then it returns `0.05`, `0.15`, `0.15`, or `0.30` respectively.

## Context (non-binding)

**Notes** — The module's functions have no CLI entry point of their own; each function is called directly by importer scripts (`load_json_stdin` reads stdin, `atomic_write_text(path, content)` takes a file path and string content, `issue_penalty(severity)` takes an issue dict, `validate_keys(data, keys)` takes a data dict and a required-keys list).

**Current implementation** — `consilium/scripts/utils.py`.
