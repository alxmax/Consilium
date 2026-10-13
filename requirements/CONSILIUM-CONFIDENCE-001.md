---
milestone: v1.0
id: CONSILIUM-CONFIDENCE-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: [CONSILIUM-UTILS-001]
risk: 2
satisfies: [ARCH-CONSILIUM-REPORT-001]
---

# confidence

> Derives a calibrated confidence score from inter-voice agreement + runner-up separation (or Trias vote pattern).

## Description

Every line in this section is binding.

- `confidence.py` reads input from stdin, or from the file named by `--input` (default: stdin).
- For score-based mode, the input is a JSON object with `candidates` (a list of `{id, scores: {generator, control, conservator}}`) and `chosen` (a string or null).
- For Trias mode, the input is a JSON object with `vote_pattern` (e.g. `3-0`, `2-1`) and optional `dissent` and `abstained` lists, instead of `candidates`/`chosen`.
- `confidence.py` reads `modes/*.md` frontmatter at import time to populate per-mode confidence floors from the `confidence_floor` key.
- `confidence.py` derives a calibrated confidence score for a deliberation result from two complementary signals: inter-voice agreement on the chosen candidate, and separation from the runner-up candidate.
- Agreement is measured as 1 minus the population stdev of the three voices after flipping Conservator from risk to safety, normalized against the theoretical maximum stdev.
- Separation is the difference in mean utility between the chosen candidate and the runner-up; when there is only one candidate (no runner-up), separation defaults to `1.0`.
- The two signals are blended as `0.7 * agreement + 0.3 * separation`, then clamped to `[0.05, 0.99]`.
- For Trias mode, `confidence.py` bypasses voice-score arithmetic entirely and derives confidence from the democratic vote pattern via a hardcoded lookup table, `VOTE_PATTERN_CONFIDENCE`.
- In Trias mode, `confidence.py` applies Sentinel-specific penalties: -0.10 when the conservative personality dissents, -0.15 when it abstains.
- The dissent and abstain penalties apply only when the Sentinel personality is the dissenter/abstainer; Essentialist and Verifier dissent/abstain carry no penalty.
- Sentinel (conservative-leaning, K=0.40) is the sole risk-anchor voice, and its absence from the majority signals a materially higher risk that the base vote-pattern score does not capture.
- The `check_mode_floor` helper lets callers determine whether the derived confidence falls below the mode-specific floor loaded from `modes/*.md` frontmatter.
- `check_mode_floor` exempts structurally decisive Trias vote patterns — `3-0`, `2-1`, `2-0` — from the WEAK flag.
- The `2-0` exemption is intentional: `2-0` means one personality had all candidates vetoed (a veto, not a deadlock), and a winner still emerged, so the run is structurally decisive.
- The lower base confidence for `2-0` (0.70 vs 0.75 for `2-1`) already encodes the stronger risk signal; flagging it WEAK on top would double-penalize the run.
- `confidence.py` writes to stdout a JSON object with three fields: `confidence` (float or null), `agreement` (float), `separation` (float or null).
- The stdout object may also carry optional `source` and `notes` fields.
- When `chosen` is null or absent from `candidates`, the output is JSON with `confidence: null` and a `reason` string.
- `confidence.py` exits 0 on success and exits 1 on an invalid input shape.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given a chosen candidate with `generator=0.8`, `control=0.9`, `conservator=0.1` (high utility, low risk, high agreement) and no runner-up, when `confidence.py` runs, then the output confidence is close to 0.99 (agreement near 1.0, separation defaults to 1.0).
- **CASE-2** — Given `chosen: null` in the input, when `confidence.py` runs, then the output is `{confidence: null, reason: "..."}` and the script exits 0.
- **CASE-3** — Given `vote_pattern='2-1'` with a dissent list containing the Sentinel personality, when `confidence.py` runs, then the output confidence equals `VOTE_PATTERN_CONFIDENCE['2-1']` minus the `SENTINEL_DISSENT_PENALTY` (0.10), rounded to 3 decimal places.
- **CASE-4** — Given `vote_pattern='3-0'`, when `check_mode_floor` runs with `mode='trias'`, then it returns `below_floor=false` regardless of the numeric floor, because `3-0` is in the decisive exempt set.
- **CASE-5** — Given a candidates list where one candidate is missing the `scores` key, when `confidence.py` runs, then it exits 1 and prints a descriptive error to stderr before producing any output.

## Context (non-binding)

**Current implementation** — `consilium/scripts/confidence.py`.
