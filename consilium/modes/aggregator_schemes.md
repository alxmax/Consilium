---
name: aggregator_schemes
script: scripts/aggregator.py
default_scheme: conservative_override
schemes: majority, conservative_override, risk_adjusted_utility, team_vote, sequential
veto_threshold: 0.8
relaxed_veto_cap: 0.85
description: Aggregation schemes that merge voice scores into a chosen candidate. Selected via --scheme; conservative_override is the default.
---

# Aggregator schemes

`scripts/aggregator.py` exposes five schemes via `--scheme`. All consume voice scores or voice outputs on stdin and emit `{scheme, chosen, ...}`. `conservative_override` is the default (Step 5).

```bash
cat input.json | python scripts/aggregator.py --scheme conservative_override
```

## Scheme reference

| Scheme | Input shape | Veto | Tie-break / ranking | When to use |
|---|---|---|---|---|
| `conservative_override` (default) | `candidates[].scores` + optional `weights`, `veto_threshold` | risk `>` threshold (strict) | weighted avg of `(generator, control, 1−conservator)`; safer wins on tie | Step 5 default — risk-first ranking with a hard cutoff |
| `risk_adjusted_utility` | `candidates[].scores` | none (soft) | `utility × (1 − sigmoid(risk))` | many candidates clustered near the veto threshold; want a smooth ramp, not a cliff |
| `majority` | `candidates[].scores` | none | highest mean; tie → lowest stdev → insertion order | quick mean-of-voices pick without risk weighting |
| `team_vote` | `personalities[].chose` + `candidates[]` | abstain = `chose: null` | democratic majority (≥2 of 3); exact tie raises | Trias mode — vote over 3 personalities' chosen candidates |
| `sequential` | `generator`, `control`, `conservator` voice outputs | cascade (see below) | priority-ordered verdict, not a score rank | Sequential mode — single-context veto cascade |

## conservative_override (default)

Vetoes any candidate whose conservator risk is **strictly greater** than `veto_threshold` (default `0.8` — `risk = 0.80` survives, `0.81` is vetoed). Survivors are ranked by weighted average of `(generator, control, safety)` where `safety = 1 − conservator`. Flipping conservator into safety is the point of the scheme: without it a higher-risk survivor would outrank a lower-risk one when the other voices tie.

- **Control-rejected candidates** (`valid: false`, or a `control` score of 0 or less — how `build_report.py` encodes invalid / never-evaluated) are excluded and listed in `vetoed` with `reason: "control_invalid"`; they can never win on generator or safety score.
- **All vetoed** → `chosen: null`. With `auto_relax` (default on), emits `retry_suggested` with a relaxed threshold = lowest candidate risk, unless that risk exceeds `RELAXED_VETO_CAP` (0.85), in which case it sets `escalation_required` instead — relaxing would not help.
- **Veto uncertainty band** — candidates within `VETO_UNCERTAINTY_BAND` (0.15) of the threshold are flagged `veto_uncertain` (inter-run conservator pstdev is 0.12–0.18, so boundary vetoes may not reproduce).

## risk_adjusted_utility

No hard veto. `final = utility × (1 − penalty)` where `utility = mean(gen, ctrl, 1−cons)` and `penalty = sigmoid(STEEPNESS × (risk − 0.5))` (midpoint 0.5, steepness 10). Risk 0.5 → 0.5 penalty; 0.7 → ~0.88; 0.85 → ~0.97. High-risk candidates can still win on dramatically higher utility, but the sigmoid is steep enough that `risk > 0.7` rarely survives.

## team_vote (Trias)

Requires exactly 3 personalities, each with `chose` (a candidate id or `null` = abstain). Derives a vote pattern (`3-0`, `2-1`, `2-0`, `1-1-1`, …). Majority = ≥2 votes for one candidate. A genuine tie (two candidates both at the top count) raises `ValueError` — the orchestrator must run the B2 deadlock cascade. `0-0-0` (all abstain) emits `retry_suggested`. Pipe the output directly into `confidence.py`, which reads `vote_pattern` (see [confidence.md](confidence.md)).

## sequential

Operates on voice **outputs**, not candidate scores. Priority-ordered veto cascade:

1. `glossary_fail` (Control) → **BLOCK**
2. `irreversibility_flag` (Conservator) → **BLOCK**
3. ≥3 triggers at once → **ESCALATE**
4. substantial disagreement → **REWORK**
5. `scale_down` meta → **ADAPT_SHORT**; `scale_up` → **ADAPT_EXTENDED**
6. default → **AGGREGATE** (picks Generator's `preferred`, derives `confidence_per_option` from `net_concern`) — but only if `preferred` is admissible: Control evaluated it (`valid: true`) and `net_concern` is not above `0.8`. Otherwise **REWORK** (`reason: preferred_inadmissible`, `chosen: null`, with `admissible_alternatives`) unless the input carries `waiver: {id, reason}` for it, which is recorded in `admissibility.waived`. `scale_down` skips Control by design and is exempt.

<!-- implements: CONSILIUM-AGGREGATOR-001 -->
