---
name: skeptic_on_chosen
subagents: 1
cost_multiplier: base+1
confidence_floor: N/A
models: sonnet
description: Cross-cutting flag — +1 Skeptic sub-agent over any base mode post-hoc. Composable over Sequential/Dialectic/Trias.
---

# Skeptic-on-chosen mode (`skeptic_on_chosen`)

**Mechanics:** `skeptic_on_chosen` is a **cross-cutting flag**, not a fixed mode. It composes over any base mode (Sequential, Dialectic, Trias): after the base mode produces `chosen` and `confidence`, 1 additional Skeptic voice is dispatched on the resulting `chosen`, with the prompt `prompts/voices/skeptic.md`. The flag runs **sequentially post-hoc** on any mode. Dispatch uses standard invocation of `prompts/voices/skeptic.md` with the current chosen; the returned output is validated by `scripts/validate_skeptic.py` (Step 3) — invalid output is rejected and the original chosen ships unchallenged.

**Cost:** +1 sub-agent over the chosen base mode (whichever it is). E.g.: Dialectic + flag = 2 sub-agents (~1.66× Sequential — current Dialectic is 1 Skeptic sub-agent, not the retired 6-voice Pass-1+Pass-2 layout).

> **Legacy note.** The modes `parallel_skeptic` and `dialectic_skeptic` were distinct fixed modes (Parallel/Dialectic with Skeptic baked-in). They were collapsed into this composable flag on 2026-05-17 — at the time, the identical functionality was obtained via `parallel + skeptic_on_chosen` and `dialectic + skeptic_on_chosen` (Parallel itself was later removed, 2026-06-26). The legacy names remain accepted via `validate_report.py`'s `_LEGACY_MODE_ALIASES` map for backward-compat with historical runs.

## When to use

**Not a trigger: confidence.** The former `confidence < 0.70` auto-trigger was removed: confidence does not predict outcomes (64 `[confirmed]` FEEDBACK outcomes: Brier 0.163 vs 0.085 for the base rate; OK-rate 0.92 at ≥ 0.7 vs 0.90 below; `scripts/confidence_calibration.py` returns `FALLBACK_A`).

**Auto-trigger conditions** (any is sufficient):
- `Conservator.net_concern` > 0.7 on the chosen — a high-concern winner is worth probing: `trigger_reason: "high_concern"`
- `chosen_approach` coincides with a `BAD` outcome from `FEEDBACK.html` (last 30 days, substring match on label): `trigger_reason: "similar_to_recent_bad"` — Reviewer 9-lite for classic modes
- `irreversibility_flag: true` — existing consent gate, Skeptic adds object-level check: `trigger_reason: "irreversibility_gate"`

- **Manual opt-in** via `--skeptic-on-chosen` when you want a focal challenger post-hoc regardless of confidence (medium-stakes, problems with known implicit constraints)
- Problems where chosen_confirmation_pass has empirically demonstrated value — particularly situations with implicit constraints not explicitly stated in success_criterion (P3 type: the logical preconditions of the solution don't appear in the statement)
- When you want the focal challenger on any base (Sequential / Dialectic / Trias) without dedicated fixed mode cost
- Cases where you want to know whether chosen missed something, but have no basis for comparison (no viable alternatives) — the focal Skeptic on chosen is cheaper than re-running the entire deliberation

## Workflow
1. Run the full base mode (any: Sequential / Dialectic / Trias) → produces `chosen`, `confidence`, intermediate report
2. If an auto-trigger condition above holds or the `--skeptic-on-chosen` flag is active, dispatch 1 Sonnet 5.5 sub-agent with `prompts/voices/skeptic.md` inline + minimal input:
   ```
   chosen: <id, summary, sketch, rationale>
   success_criterion: <the testable sentence>
   verification: <the command>
   ```
   DO NOT pass other candidates, scores, or deliberation logs.
3. Validate the skeptic output with `python scripts/validate_skeptic.py < <skeptic_output>.json` (exit 0 = accept, exit 1 = reject → ship the original chosen unchallenged, exit 2 = malformed JSON). The gate enforces:
   - `can_object: true` with `concrete_concerns` ≥ 2 OR `quoted_scenario` non-null → accept
   - `can_object: true` without evidence → reject (schema fail), ship the original chosen
   - `can_object: false` → ship the original chosen, log that there is no concrete objection
   - `failure_mode` must be one of the four canonical labels; `goal_fit` must quote `success_criterion`
4. Log the result in `deliberation_log` with step `"skeptic_on_chosen"` and set flag `skeptic_caught_constraint: true|false` in the report
5. Apply override semantics (section below)

## Override semantics
**Advisory by default.** The Skeptic's verdict is logged in `deliberation_log` as an entry with step `"skeptic_on_chosen"` and flag `skeptic_caught_constraint: true|false`. `chosen` is **not replaced** — it stays as produced by the base mode. The user sees the objection in the report and can act or ignore.

**Opt-in override via `--skeptic-can-override`.** If the flag is active AND Skeptic produces `addressable: requires_redesign`, the Skeptic's verdict supersedes `chosen`: the orchestrator presents the report's alternatives to the user and asks whether to change the choice. If Skeptic produces `addressable: in_place`, the override does not apply (advisory remains); if it produces `addressable: unaddressable` with `failure_mode: meta_scope_mismatch`, the report is marked `misapplied`.

Summary table:

| Skeptic output | Advisory (default) | With `--skeptic-can-override` |
|---|---|---|
| `can_object: false` | ship original chosen | ship original chosen |
| `in_place` | log + note in report | log + note in report (no override) |
| `requires_redesign` | log + advisory | orchestrator proposes alternatives |
| `unaddressable / meta_scope_mismatch` | mark `misapplied` | mark `misapplied` |

## Skip if
- No auto-trigger condition holds and the `--skeptic-on-chosen` flag is not active
- `chosen` is null (all candidates vetoed) — there is no chosen to challenge
- Diff is intrinsically high-stakes (auth, migrations, security) — use full Trias with justified cost

**Empirical origin.** The mode emerged from the analysis in `experiments/oracle-discipline.md`: `chosen_confirmation_pass` (the conceptual equivalent of this flag) reached 100% catch-rate in simulation and 4/7 in real reruns on the P3 implicit-constraint problem — performance superior to any other mode tested on that problem. **Scope caveat (n=1):** these figures derive from a single problem instance; generalizability to other problems is unconfirmed until ≥3 distinct problems are tested.

<!-- implements: CONSILIUM-MODE-SKEPTIC-ON-CHOSEN-001 -->

