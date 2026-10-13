# Deliberation Runs

Each time the skill is invoked on a real task, the agent writes the full
deliberation as a JSON file to `.consilium/runs/` at the end of Step 6.
Files are gitignored — they're personal logs that feed the priors loop,
not part of the skill itself. The data directory layout and the path
constants that locate it (`RUNS_DIR`/`FEEDBACK_PATH`) live in
`scripts/utils.py`.

Filename: `YYYY-MM-DD_HHMM_<short-label>.json`
Example: `2026-05-12_1430_pr42-extract-helper.json`

## Schema

The exact shape is enforced by `scripts/validate_report.py`. Required
fields are marked **REQUIRED**; the rest are recommended but not blocking.

### Full deliberation report

```json
{
  "success_criterion": "REQUIRED — testable sentence from Step 1",
  "verification": "REQUIRED — concrete check that proves success_criterion",
  "chosen_approach": "approach_id OR null (if all candidates vetoed)",
  "reasoning": "short summary of why chosen won",
  "alternatives": [
    {"id": "...", "summary": "...", "why_not": "..."}
  ],
  "voice_scores": {
    "generator": 0.8,
    "control": 0.9,
    "conservator": 0.4
  },
  "confidence": 0.85,
  "pipeline_executed": true,
  "telemetry": {
    "mode": "sequential | dialectic | trias | skeptic_on_chosen | sequential_scale_down | prior_deliberation_passthrough | user_spec_passthrough",
    "dispatch_count": 3,
    "passes": 1,
    "voices": {
      "generator":   {"tokens_in": 1200, "tokens_out": 400, "latency_ms": 3500},
      "control":     {"tokens_in":  800, "tokens_out": 200, "latency_ms": 2100},
      "conservator": {"tokens_in":  900, "tokens_out": 180, "latency_ms": 1800}
    },
    "personalities": {
      "pioneer":   {"tokens_in": 5200, "tokens_out": 1400, "latency_ms": 8000},
      "architect": {"tokens_in": 5200, "tokens_out": 1400, "latency_ms": 8200},
      "steward":   {"tokens_in": 5200, "tokens_out": 1400, "latency_ms": 7900}
    },
    "total_tokens_in": 12950,
    "total_tokens_out": 3300,
    "total_latency_ms": 23400
  },
  "deliberation_log": [
    {"step": "generator",   "candidates": [...]},
    {"step": "control",     "verdicts":   [...]},
    {"step": "conservator", "scores":     [...]},
    {"step": "aggregate",   "scheme": "conservative_override", "result": {...}}
  ]
}
```

### Skipped report (scope_gate said the change is too small to deliberate)

```json
{
  "success_criterion": "REQUIRED",
  "verification": "REQUIRED",
  "chosen_approach": "skipped",
  "skipped": true,
  "skip_reason": "REQUIRED when skipped=true — e.g. '1 file, 4 lines, no sensitive paths'",
  "signals": {
    "files_changed": 1,
    "lines_changed": 4,
    "blocklist_hits": []
  },
  "voice_scores": null,
  "confidence": null,
  "alternatives": [],
  "deliberation_log": []
}
```

## Field notes

- **`pipeline_executed`** (bool) is **REQUIRED for non-skipped reports**
  (`validate_report.py` rejects reports without it). `true` when the full
  voice pipeline ran; **must be `false`** for the bypass templates
  (`trivial-direct` scale_down short-circuits, `prior-deliberation` /
  `user-spec` passthroughs) — setting it `true` there is rejected as
  inconsistent. Not required when `skipped: true`.
- **`telemetry`** is **REQUIRED for non-skipped reports**: the block itself
  and a non-empty `telemetry.mode`. Per-voice blocks (`telemetry.voices`)
  are required for the multi-voice modes (trias / dialectic /
  skeptic_on_chosen). Fill what you can measure and omit the rest of the
  optional counters. `telemetry.mode` is an open string — historical
  `parallel` runs stay readable (see `_MULTI_VOICE_MODES` in
  `validate_report.py`); legacy names `parallel_skeptic` /
  `dialectic_skeptic` are normalized via `_LEGACY_MODE_ALIASES`
  (`trias_split` was removed from it on 2026-09-21).
- **`chosen_approach`** can be `null` legitimately when `aggregator.py`
  with `conservative_override` vetoes every candidate. In that case
  `deliberation_log[aggregate].result` should carry `retry_suggested`.
- **`skeptic_challenges_count`** / **`post_vote_skeptic_used`** (Trias only,
  optional). The 2026-06-19 skeptic-lever redesign replaced the 3 per-personality
  pre-vote Skeptics with one post-vote `skeptic_on_chosen`. `post_vote_skeptic_used`
  is `true` when that Skeptic fired (always under default-A; only when
  `confidence ∈ [0.0, 0.70)` — strictly below 0.70 — under the opt-in
  `--trias-skeptic-gate`).
  `skeptic_challenges_count` is `0` (skipped), `1` (challenged the winner), or
  `2` (winner demolished → `--skeptic-can-override` re-vote → new winner
  re-challenged). These exist so a future `confidence_calibration.py`-style
  coverage check can measure skeptic-coverage-vs-outcome and confirm or roll back
  the 3→1 reduction (the open **T1 debt** — Reviewer 8/Reviewer 9, 2026-06-19 audit).

## Consumers

- **`scripts/priors.py`** — at start of each new deliberation, summarizes
  recent runs to surface patterns (override rate, veto rate, repeating
  keywords).
- **`scripts/feedback.py`** — counts schemes used across runs (reads from
  `deliberation_log[aggregate].scheme`).
- **`scripts/memory.py`** — uniform read API over runs (medium tier).
- **`scripts/validate_report.py`** — shape-check before persisting a
  report; fails fast if `success_criterion`/`verification` are missing.
