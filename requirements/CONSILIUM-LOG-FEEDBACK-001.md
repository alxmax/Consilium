---
milestone: v1.0
id: CONSILIUM-LOG-FEEDBACK-001
status: draft
level: code
layer: feature
owner: alxmax
depends_on: [CONSILIUM-FEEDBACK-001, CONSILIUM-RENDER-FEEDBACK-HTML-001, CONSILIUM-UTILS-001]
risk: 1
satisfies: [ARCH-CONSILIUM-LEARNING-001]
---

# log_feedback

> Atomically appends (or upgrades) a FEEDBACK.html row from a deliberation report.

## Description

Every line in this section is binding.

- `log_feedback.py` atomically appends a feedback entry to FEEDBACK.html from a deliberation report JSON, removing the manual friction of Step 6 outcome logging.
- `log_feedback.py` derives `date` (today), `context` (first 60 chars of `success_criterion`), `chosen` (from `chosen_approach`), an auto-generated `note` (candidate count, veto count, confidence, mode), and records the caller-supplied `outcome`.
- Before appending, it checks for duplicates using a 16-character SHA-256 fingerprint keyed on `date|chosen|context|run_id`.
- If the existing row has the same `run_path` but a different outcome (e.g., PEND->OK), the row is upgraded in place rather than duplicated.
- The sidecar `.run_path_map.json` is updated on every real write so `efficiency.py` and `audit_feedback.py` can later join outcomes to telemetry by run path.
- `--weak` adds the `[weak]` marker to the note for a run below its mode confidence floor; the row's outcome is unchanged (`PEND`), because WEAK is advisory quality metadata, not an observed outcome. `--outcome WEAK` is rejected.
- `--outcome OK` requires `--confirmed` (the verification passed or the user confirmed the result), which adds the `[confirmed]` marker; it also enforces a 0.70 confidence threshold gate, requiring `--force-override` to bypass.
- stdout is a `date | context | chosen | outcome | note` summary line (or `skipped (duplicate): ...` on exit 3).
- `.consilium/FEEDBACK.html` is updated atomically with the new or upgraded row; `.consilium/runs/.run_path_map.json` is updated with the new fingerprint->run_path entry.
- Exit code is 0 on success, 1 on validation error or confidence gate rejection, 2 on malformed JSON or missing required args, 3 on duplicate entry skipped.
- When `run_id` is absent, the fingerprint falls back to a microsecond-precision timestamp (`datetime.now().strftime("%f")`) as the 4th field, not a 3-field key. This prevents same-day collisions but makes the fingerprint non-deterministic.
- Two recomputed fingerprints for the same legacy row differ, so old no-run_id rows can never be matched by fingerprint lookup — they fall back to `run_path=None`.
- The confidence gate reads `report.get("confidence")` — the top-level key only. When a report carries both a top-level `confidence` and a nested `confidence.confidence` dict, the top-level value is used and the nested form is silently ignored.
- The whole append or upgrade — parse the rows, write the row, write the sidecar — runs under `feedback_lock` (an exclusive cross-process lock on `FEEDBACK.html.lock`), so concurrent callers (appends and outcome upgrades alike) each start from the previous caller's result and no row is lost. A caller that cannot get the lock within 30 s fails with `TimeoutError`.
- The row is written before its sidecar entry. A call interrupted between the two leaves a row with no sidecar entry; a retry with the same `--run-path` adopts that row (same `date|chosen|context`, claimed by no sidecar entry) instead of appending a duplicate, and saves the missing sidecar entry.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given a report with a valid `success_criterion` and `chosen_approach`, when `log_feedback.py` runs, then it produces a new `<tr>` row in FEEDBACK.html with the correct date, truncated context, and derived note.
- **CASE-2** — Given the same report is appended twice with the same `--run-path` and the same `--outcome`, when the second call runs, then it exits 3 and does not add a duplicate row.
- **CASE-3** — Given the same report is appended twice with the same `--run-path` but a different outcome (e.g. PEND then OK), when the second call runs, then it upgrades the existing row in place and exits 0.
- **CASE-4** — Given `--outcome OK` with a report whose `confidence` is below 0.70, when the script runs without `--force-override`, then it exits 1 with an error message.
- **CASE-4b** — Given `--outcome OK` without `--confirmed`, when the script runs, then it exits 1 and writes nothing.
- **CASE-5** — Given `--outcome OVR` without `--override-target`, when the script runs, then it exits 2 with an error message to stderr.
- **CASE-6** — Given several `log_feedback.py` processes run at once (distinct appends plus an outcome upgrade of an existing row), when they all finish, then every appended row is present and the upgrade is applied.
- **CASE-7** — Given the sidecar write fails after the row was written, when the same call is retried, then FEEDBACK.html still holds exactly one such row and the sidecar maps the run path.
- **CASE-8** — Given a below-floor result from `check_mode_floor`, when `log_feedback.py --weak` runs, then FEEDBACK.html holds one row with outcome `PEND` and a `[weak]` note marker, and `feedback.py` reads it back.

## Context (non-binding)

**Notes** — Input: deliberation report JSON via stdin (required); `.consilium/FEEDBACK.html` (created if absent, overridable via `--feedback`); `.consilium/runs/.run_path_map.json` read and updated; CLI flags `--outcome OK|BAD|OVR|PEND|PEND_HEADLESS`, `--override-target`, `--user-note`, `--run-path`, `--dry-run`, `--force-override`. Contract addenda derive from a code audit dated 2026-06-04.

**Current implementation** — `consilium/scripts/log_feedback.py`.
