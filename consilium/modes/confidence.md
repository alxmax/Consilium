---
name: confidence
script: scripts/confidence.py
agreement_weight: 0.7
separation_weight: 0.3
floor: 0.05
ceil: 0.99
mode_floors: sequential=0.70, dialectic=0.75, trias=0.80
description: Derives report confidence from inter-voice agreement + separation from runner-up. Score-based for most modes; vote-pattern-based for Trias.
---

# Confidence derivation

`scripts/confidence.py` replaces the hand-picked `confidence` number with one derived from the voice scores. Step 5b. Two code paths:

- **Score-based** (Sequential, Dialectic, Skeptic) — from `candidates[].scores` + `chosen`.
- **Vote-pattern-based** (Trias) — from `vote_pattern` piped from `aggregator.py --scheme team_vote`.

```bash
echo '{"candidates": [...], "chosen": "approach_id"}' | python scripts/confidence.py
```

## Score-based formula

`confidence = 0.7 × agreement + 0.3 × separation`, clamped to `[0.05, 0.99]`.

- **agreement** = `1 − stdev([gen, ctrl, safety]) / MAX_STDEV` where `safety = 1 − conservator` and `MAX_STDEV ≈ 0.471` (the pstdev of `[0,0,1]`). The conservator flip matters: without it, "everyone thinks this is a great, safe candidate" (gen high, ctrl high, conservator low) would register as *high disagreement*.
- **separation** = `utility(chosen) − max utility(others)`, where `utility(c) = mean(gen, ctrl, 1−cons)`. No runner-up → `1.0`.

If `chosen` is `null` (all vetoed), returns `{"confidence": null}` — confidence is undefined without a winner, and Step 5d retry is skipped.

## Vote-pattern (Trias)

| Pattern | Confidence | Agreement |
|---|---|---|
| 3-0 | 0.95 | 1.0 |
| 2-1 | 0.75 | 0.67 |
| 2-0 | 0.70 | 0.67 |
| 1-1-1 / 1-1-0 / 1-0-0 / 0-0-0 | null | 0.0 |

**Uncalibrated priors, not probabilities.** These confidence values encode inter-personality **consensus**, not validated accuracy. `scripts/vote_degeneracy.py` (n=25) confirms the *ordering* is earned — 3-0 occurs only ~48% of the time, so unanimity is a genuine signal rather than forced — but the *magnitudes* (0.95 / 0.75 / 0.70) are not calibrated against correctness. On the `transport_choice` benchmark task a 3-0 landed on a **wrong** answer (32/100): agreement ≠ truth. Treat the numbers as ordered priors until a corpus of ≥20 labeled `(vote_pattern, outcome)` pairs produces a calibration curve. (review 2026-05-26 round 2, D1.)

**Sentinel penalty.** Sentinel is the conservative-leaning personality. When it is the dissenter in a 2-1 (−0.10) or the abstainer in a 2-0 (−0.15), confidence drops below the auto-ship threshold so the orchestrator prompts the user. The same outcome from Essentialist or Verifier carries no penalty.

## Mode confidence floor (E1)

After deriving confidence, `check_mode_floor(mode, confidence)` compares against the per-mode floor. Below floor → log `--outcome WEAK` in FEEDBACK.html (the mode did not deliver value for its cost). Floors are loaded at import time from each `modes/*.md` frontmatter `confidence_floor` field, with a hardcoded fallback when `modes/` is absent (older installs):

| Mode | Floor |
|---|---|
| sequential / sequential_scale_down | 0.70 |
| dialectic | 0.75 |
| trias | 0.80 |
| skeptic_on_chosen | N/A (flag, no own floor) |

## Calibration caveat

`agreement` measures role-prompt divergence **within one run**, not inter-run stability. Conservator scores are anchored by a categorical formula; Generator/Control scores are self-assigned unanchored floats. A second run on the same input may differ (predicted pstdev 0.12–0.18 on risk_score). The `confidence` value is an internal-consistency signal, **not a calibrated probability**.

<!-- implements: CONSILIUM-CONFIDENCE-001 -->
