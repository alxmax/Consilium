---
name: trias
subagents: 4
cost_multiplier: 2.67
confidence_floor: 0.80
models: sonnet(essentialist),sonnet(verifier),sonnet(sentinel)
dispatch_count_worst_case: 7
lazy_routing: true
description: 3 personalities (Essentialist/Verifier/Sentinel), each runs Sequential internally, vote, then ONE Skeptic challenges the winning candidate post-vote (skeptic_on_chosen). Lazy routing downgrades by magnitude tier — low/medium → Sequential, high → Dialectic, critical → full Trias (blocklist hits only).
---

# Trias mode (high-stakes opt-in)

**Mechanics:** 3 fixed personalities (Essentialist / Verifier / Sentinel), each dispatched as **one Sequential sub-agent** (Generator→Conservator→Control internally) with the personality lens prepended. Democratic majority vote over the 3 chosen results, then **ONE** Skeptic sub-agent (`skeptic_on_chosen`) challenges the **winning** candidate post-vote. Cost: ~2.67× Sequential (4 sub-agents vs 1).

**Skeptic-lever redesign (2026-06-19, trias-6to4-impl-default-a, MODIFY 4-5-0).** The previous design ran **one Skeptic per personality** at Step 3.5 (3 Skeptics, pre-vote, = 6 sub-agents). That was the cost lever, not the personalities: the redesign drops the 3 per-personality Skeptics and adds **one** post-vote `skeptic_on_chosen` on the winner (6→4 spawns). The cost lever is the **Skeptic count (3→1)**, never the personality topology — the 3 personalities stay blind + parallel (the `trias_parallel_dispatch` invariant is preserved). The single post-vote Skeptic is **advisory by default** (the vote stands; the objection is recorded as a caveat); under the explicit `--skeptic-can-override` flag a demolishing objection triggers a re-vote (see Step 3.6). **Default policy is unconditional** (Variant A): the Skeptic always fires. A confidence-gated variant (Variant C — Skeptic fires only when `confidence ∈ [0.0, 0.70)`) is an opt-in `--trias-skeptic-gate` flag, **off by default**, because the calibration gate (`confidence_calibration.py`) currently returns `FALLBACK_A` on the corpus (16 negatives, discrimination 0.14 < 0.15 margin). Nothing reads that verdict at dispatch time: switching the default from A to C is a maintainer's edit to this file, made once the gate returns `SHIP_C`.

> **T1 coverage debt (unvalidated).** Replacing 3 pre-vote per-candidate Skeptics with 1 post-vote winner-only Skeptic is an **architectural assumption, not an empirically-validated equivalence** — the 2 losing candidates are no longer Skeptic-tested, and the winner is challenged only after it has won. There is no n≥5 evidence that 1 post-vote Skeptic catches what 3 pre-vote Skeptics caught (Reviewer 8/Reviewer 9, 2026-06-19 audit). The runs schema records `skeptic_challenges_count` + `post_vote_skeptic_used` so a future `confidence_calibration.py`-style coverage check can confirm or roll back the reduction.

**Why the vote diverges (D4).** All three sub-agents use the same model (Sonnet) but distinct lenses. Divergence source: **lens re-weighting** — Essentialist up-weights Generator (upside), Sentinel up-weights Conservator (risk), Verifier balances. Divergence is measured by `vote_degeneracy.py` — empirical baseline ~52% non-unanimity at n=25 (uniform Sonnet). Revert signal: < 40% non-unanimity over ≥15 runs.

The weights act **within** each personality only — they decide that personality's own `chose`. **Between** personalities there is no precedence ordering: `aggregator.py --scheme team_vote` is a flat majority over the three `chose` values, and no lens outranks another. A true tie (1-1-1) does not resolve to a "senior" personality — it routes to the B2 deadlock cascade (Round 2 → Skeptic → PEND). So there is no authority hierarchy among the three; the only re-ranking is internal to each sub-agent.

**Previous mechanics (archived):** The old Trias dispatched 9 parallel sub-agents (3 personalities × 3 voices). The new design reduces from 9 to 3 personality sub-agents — each personality runs its own Sequential deliberation internally. Three Skeptic sub-agents (one per personality, Step 3.5) are added at the orchestrator level after Step 3. The democratic vote over 3 (possibly revised) chosen results is preserved.

## When to use
- Irreversible schema/DB migration
- Security audit (auth, crypto, RCE potential)
- Refactor > 5 files
- 2+ plausible architectural approaches, no clear winner
- Cost of wrong decision >> cost of running (4 sub-agents, ~2.67× Sequential)

## Lazy routing (default: enabled)

**Purpose:** Avoid the ~2.67× Trias cost when the change does not warrant it. Trias classifies magnitude via `scope_gate.py` and routes to the cheapest mode that fits — a **graduated ladder** keyed on `scope_gate._MODE_CEILING`:

| magnitude | routes to | cost |
|---|---|---|
| low / medium | **Sequential** | 1× |
| high | **Dialectic** | 1.33× |
| critical (blocklist hit: auth, security, migrations, CI workflows, secrets) | **full Trias** | ~2.67× |

**Default:** `lazy=true`. Only `critical` magnitude proceeds to full Trias; `high` downgrades to Dialectic; `low`/`medium` downgrade all the way to bare Sequential — at low/medium magnitude the marginal scrutiny of Dialectic's Skeptic isn't worth the 1.33× over Sequential. To force full Trias on a non-critical change, the user must explicitly state "use full Trias" or "no lazy routing" in their request.

**Override cost-warning (D2).** An explicit override on a sub-critical change is honored, but **not silently** — the user is paying ~2.67× for a change `scope_gate.py` judged low/medium/high. Before dispatching the 4 sub-agents on an overridden change, emit a one-line warning so the cost is a conscious choice:
```json
{"trias_override_warning": true, "magnitude": "<low|medium|high>", "cost_multiplier": 2.67,
 "note": "Full Trias forced below critical magnitude — ~2.67x cost. Drop the override to auto-route (low/medium → Sequential, high → Dialectic)."}
```
This is a warning, not a refusal: there is no hard block, because the user holds the authority on their own spend (a hard floor would override an explicit, informed instruction). The warning makes the tradeoff visible; the override still proceeds.

**Sequencing contract (mandatory):** Magnitude classification MUST run on the **original unstripped context** BEFORE Phase 1 context stripping is applied. Strip happens after the routing decision.

**Routing logic:**
```bash
gate=$(python -X utf8 scripts/scope_gate.py)          # on original context
magnitude=$(echo "$gate" | python -c "import sys,json; print(json.load(sys.stdin)['magnitude'])")
```
- `magnitude == "critical"` → proceed to full Trias (then apply Phase 1 strip below)
- `magnitude == "high"` → downgrade to **Dialectic**
- `magnitude in {"low", "medium"}` → downgrade to **Sequential**

For any downgrade, emit the structured notification:
```json
  {
    "trias_lazy_routed": true,
    "routed_to": "<sequential|dialectic>",
    "magnitude": "<low|medium|high>",
    "magnitude_score": {"files": "<n>", "lines": "<n>", "blocklist_hits": "<n>"},
    "threshold": "critical",
    "context_tokens_available": "<approx>",
    "override_instruction": "Re-invoke with explicit 'use full Trias' to force 6-sub-agent mode."
  }
  ```

## Workflow
0. **(Phase 2 — lazy routing)** Run scope_gate on original context and check magnitude. If `magnitude != "critical"` AND user has not explicitly requested full Trias, downgrade per the ladder above (high → Dialectic; low/medium → Sequential), emit the notification, and stop the Trias workflow here.
1. Orchestrator reads `python -X utf8 scripts/personalities.py` — emits the 3 personalities
2. **(Phase 1 — context strip)** Before building each sub-agent prompt, truncate the raw conversation context to ≈15 000 tokens:
   ```bash
   stripped=$(echo "$raw_context" | python -X utf8 scripts/strip_context.py --truncate-text 15000)
   ```
   Use `$stripped` (not `$raw_context`) in each personality sub-agent prompt. This runs **per sub-agent** so each gets the same budget-capped context. The truncation marker `[... context truncated ...]` signals to the sub-agent that context was cut; it should proceed normally.
3. **Dispatch all 3 personalities in parallel** (3 `consilium-subagent` Agent calls in the **same** orchestrator message), each with `prompts/voices/<personality>_lens.md` (the `lens` path from `personalities.py` output) prepended over the task context (using stripped context from Step 2). Each sub-agent runs a full Sequential deliberation (Generator→Conservator→Control) internally with its personality lens applied, and returns `{chosen_approach, rationale, confidence}`. Parallel dispatch is mandatory — sequential dispatch triples wall-clock for no quality gain, and is the root cause of the task-08 timeout pattern observed in benchmark n=10 (2026-05-27).

   **Model dispatch.** Each personality sub-agent is dispatched with `model: <personality.model>` from `personalities.py` output (all three → `sonnet`). All personalities use standard StructuredOutput schema dispatch.

   **Failure handling.** If any personality returns malformed or empty JSON, treat it as a non-vote and continue per B2 timeout rules (≥2 valid votes from the remaining personalities yield a clear majority; < 2 valid votes → PEND immediately).

   **Token cost.** The 3 personality sub-agents (all Sonnet) plus the **single** post-vote Skeptic sub-agent (Step 9, Sonnet) give `cost_multiplier: 2.67` (vs Sequential) — a sub-agent-count estimate; only the 4-vs-6 spawn ratio was token-measured, on n=2 problems ([experiments/trias-6to4-cost-2026-06-19.md](../experiments/trias-6to4-cost-2026-06-19.md)); the absolute cost against Sequential is unmeasured. The confidence-gated variant drops to ~2× on confident runs (Skeptic skipped).

   **Runtime audit (review 2026-05-28, trias-parallelism-enforcement, MODIFY 6-3-0):** `Consilium-Benchmark/scripts/check_trias_parallelism.py` (separate benchmark repo) reads the Claude CLI session JSONL transcript after each Trias run and writes `trias_dispatch_pattern: "serial"|"parallel"|"mixed"|"scale_down"` into `pipeline_audit.json`. Empirical observation as of 2026-05-28: 7/7 real-deliberation Trias runs were SERIAL despite this mandate. A spec-rewrite attempt (imperative phrasing + worked example + anti-pattern) also produced SERIAL — voice-prompt rewrites do not enforce orchestrator dispatch order (Reviewer 9 retrospective, 0/6 clean-GO). The mandate stays as guidance; the runtime audit is the observability mechanism. Full evidence: [experiments/trias-parallelism-2026-05-28.md](../experiments/trias-parallelism-2026-05-28.md).

   **Vehicle decision (review 2026-05-29, trias-parallelism-vehicle-a1-vs-a2, MODIFY 6-3-0):** a follow-up audit reviewed the two architectural fixes deferred above — A1 (benchmark subprocess fan-out) and A2 (reimplement the mode via a Workflow orchestration vehicle). Outcome: **serial dispatch is accepted as by-construction-not-intent, not a bug to fix now.** A2 was rejected (the LangGraph orchestration-vehicle pattern — STOP×2 historically, never regretted; needs a separate architectural proposal if ever revived). A1 is admissible only as an explicitly-labeled *benchmark-harness* wall-clock fix, never claimed as real `/consilium` behavior. Crucially, any parallelism investment is **gated on the existing kill-criterion** — ≥2 Trias wins in n≥20 oracle-validated tasks (current record: 0 wins at n=6 on a saturated corpus). Until Trias demonstrates value, the proportional path is accept-serial + observe. Graduation mechanism: `Consilium-Benchmark/scripts/check_trias_escalation.py` (counts accumulated serial runs; logs a "revisit parallelism" recommendation at threshold).
3.5. **(No pre-vote Skeptic.)** The per-personality pre-vote Skeptics were removed in the 2026-06-19 skeptic-lever redesign. The 3 personality chosens proceed **directly** to the vote (Steps 4–8). The single Skeptic now challenges only the **winning** candidate, **after** the vote — see Step 9.

4. Collect the 3 `chosen_approach` values (one per personality) → `chose` per personality
5. **Unanimous check (B1).** If all 3 personalities chose the same `chose`, skip `team_vote` — the result is unanimous. Set `vote_pattern: "3-0"` and `vote_skipped: true`. Confidence derived directly from `confidence_from_vote_pattern("3-0")`. Log in `deliberation_log` with `reason: "unanimous_personalities"`. If not unanimous, run `team_vote` normally.
6. Orchestrator runs `python -X utf8 scripts/aggregator.py --scheme team_vote` over the 3 chosens (skip if B1 detected unanimity)
7. Confidence derived from vote_pattern — pipe aggregator output directly to `confidence.py`:
   ```bash
   echo '{"personalities":[...],"candidates":[...]}' | python scripts/aggregator.py --scheme team_vote | python scripts/confidence.py
   ```
   Do not manually build `{"candidates":[...],"chosen":"..."}` for Trias — the candidates don't have `scores` per voice.
8. **Deadlock cascade (B2) — only if vote_pattern is 1-1-1 or 0-0-0.** See Failure recovery below.
9. **Post-vote Skeptic challenge (`skeptic_on_chosen`) — ONE sub-agent on the winner.** After a decisive vote yields a `chosen_approach`, dispatch **one** Skeptic sub-agent per `prompts/voices/skeptic.md`. Input: `{chosen: <winner's chosen_approach + sketch + rationale>, runner_up_rationale: <2nd-place personality's rationale>, success_criterion, verification}`. The runner-up rationale is supplied **as a counter-hypothesis the Skeptic must actively attack** (does the losing argument expose a flaw in the winner?), not as neutral background — this is the coverage compensation for no longer challenging the losers directly. Record `skeptic_challenges_count: 1` and `post_vote_skeptic_used: true` in telemetry.
   - **Default-A (unconditional):** the Skeptic always fires after a decisive vote.
   - **Variant-C gate (`--trias-skeptic-gate`, off by default):** fire only when `confidence ∈ [0.0, 0.70)`; on confident runs skip the Skeptic (`post_vote_skeptic_used: false`, `skeptic_challenges_count: 0`). Reuses the existing `skeptic_on_chosen` auto-trigger band — no new mechanism.
   - **"Demolishes the winner" is a concrete predicate:** the Skeptic output meets `can_object: true` AND (`addressable == "requires_redesign"` OR the objection names a falsifier that defeats the `success_criterion` — `failure_mode: goal_fit` or `verification_inadequate` with the mandated quote/scenario). Anything weaker (e.g. `addressable: in_place`) is **advisory** — recorded as a caveat, the vote stands. (Aligned with the `--skeptic-can-override` table in modes/skeptic_on_chosen.md — the predicate keys only on fields skeptic.md actually emits.)
   - **B2 exception unchanged:** the deadlock cascade (Step 8) runs its own tiebreaker Skeptic; the post-vote Step 9 Skeptic does **not** also fire on a B2-resolved winner (the tiebreaker already challenged it).
10. **Override re-vote (`--skeptic-can-override` only).** If Step 9's predicate fires (`demolishes` true) AND `--skeptic-can-override` is set: re-run `aggregator.py --scheme team_vote` over the **remaining** personality chosens **excluding the demolished winner** (no personality re-dispatch — the existing chosens are reused). The re-vote is a 2-way contest → `2-0` (confidence 0.70) or `1-1` (→ PEND). **The new winner is then itself challenged by one more `skeptic_on_chosen`** (the override must not silently promote an unscrutinised candidate); `skeptic_challenges_count: 2`. If that second Skeptic also demolishes, **PEND** (do not loop). Without `--skeptic-can-override`, Step 9 is advisory only and Step 10 never runs.

## Output schema (Trias-specific fields)
```json
{
  "chosen_approach": "candidate_id or null",
  "confidence": 0.82,
  "vote_pattern": "3-0",
  "personalities": [
    {"name": "Essentialist", "lens": "essentialist_lens.md", "chose": "candidate_id", "weights": {}},
    {"name": "Verifier", "lens": "verifier_lens.md", "chose": "candidate_id", "weights": {}},
    {"name": "Sentinel", "lens": "sentinel_lens.md", "chose": "candidate_id", "weights": {}}
  ]
}
```

## Vote patterns
| Pattern | Confidence | Outcome |
|---|---|---|
| 3-0 | 0.95 | OK auto |
| 2-1 | 0.75 | OK auto |
| 2-0 | 0.70 | OK auto |
| 1-1-1 | null | → B2 cascade (Round 2 → Skeptic → PEND) |
| 1-1-0 | null | → B2 cascade (2 distinct chosen + 1 abstain) |
| 1-0-0 | null | → B2 cascade (1 chosen + 2 abstain) |
| 0-0-0 | null | → B2 cascade (Round 2 → PEND) |

## Output JSON (Trias-specific fields)

```json
{
  "success_criterion": "<testable sentence>",
  "chosen_approach": "<id>",
  "team": ["essentialist", "verifier", "sentinel"],
  "vote_pattern": "2-1",
  "vote_counts": {"essentialist": "approach_a", "verifier": "approach_a", "sentinel": "approach_b"},
  "confidence": 0.75,
  "deliberation_log": [{"step": "trias_vote", "vote_pattern": "2-1", "trias_rounds": 1}]
}
```

## Failure recovery

**B2 — Deadlock cascade.** Fires when Round 1 yields 1-1-1 or 0-0-0.

**Round 2 (always first):** Re-dispatch all 3 personality sub-agents. Each receives the other two personalities' `{chosen_approach, reasoning_summary}` from Round 1 as additional context. Re-vote via `team_vote`. Cost: +3 sub-agents.

- Round 2 produces 2-1 or 3-0 → cascade exits, report normally. Set `trias_rounds: 2` in telemetry.
- Round 2 still **1-1-1** → proceed to Skeptic tiebreaker (below).
- Round 2 still **0-0-0** → **PEND** (Skeptic cannot arbitrate among nothing). Set `trias_rounds: 2, deadlock: "0-0-0"` in telemetry.
- Round 2 converts 0-0-0 → 1-1-1 → proceed to Skeptic tiebreaker.

**Skeptic tiebreaker (only after Round 2 1-1-1):** Dispatch 1 sub-agent with `prompts/voices/skeptic.md` in **tiebreak mode** (see its "Tiebreak mode" section) — input is all 3 competing `{chosen_approach, reasoning_summary}` pairs; output is `{"tiebreak": {"chosen": "<id>", "reason": ...}}`, validated by `scripts/validate_skeptic.py`. Cost: +1 sub-agent. Set `trias_rounds: 2, tiebreak: "skeptic"` in telemetry.

- `tiebreak.chosen` is one of the competing ids → chosen confirmed. Confidence: 0.65 (tiebreak path).
- `tiebreak.chosen: null` (abstain), invalid output, or error → **PEND**.

**Headless (B2):** All Round 2 and Skeptic dispatches run as non-interactive sub-agents — no prompt needed. Final PEND falls through to `PEND_HEADLESS` logging.

**Max cost.** Two mutually-exclusive tails (a decisive vote never also deadlocks):
- **Deadlock tail (1-1-1 → Round 2 → tiebreaker):** 3 (Round 1 personalities, no pre-vote Skeptics) + 3 (Round 2 personalities) + 1 (tiebreaker Skeptic) = **7 sub-agents**. The Step 9 post-vote Skeptic does not also fire on a B2-resolved winner.
- **Decisive-vote tail (Step 9 demolish → Step 10 override re-vote):** 3 (personalities) + 1 (Step 9 Skeptic) + 1 (Step 10 re-vote Skeptic on the new winner) = 5 sub-agents.

Worst case overall = **7** (`dispatch_count_worst_case: 7`).

**Dispatch failure / timeout guard (B2).** The cascade is depth-bounded (≤10 sub-agents) but each dispatch can still hang or error — a sub-agent that never returns must not strand the run with burned budget and no result. Every cascade dispatch (Round 2 ×3, Skeptic ×1) is treated as **best-effort**:

- A sub-agent that errors, times out, or returns malformed JSON is counted as a **non-vote** (it does not block the others). Do not retry more than once per dispatch.
- After Round 2, vote over **whichever personalities returned**. If ≥2 valid votes yield a clear majority → exit normally. If fewer than 2 valid votes remain, or the surviving votes still tie → **PEND immediately**; do NOT escalate to the Skeptic tiebreaker on incomplete data.
- A Skeptic dispatch that fails or times out → **PEND** (never hang waiting on it).
- Whenever the cascade exits on incomplete data, surface the **partial result** — the Round 1 `{personality, chosen_approach}` triple — in the report so the user sees the divergence, and set `cascade_incomplete: true` in telemetry alongside the count of sub-agents that actually returned (`cascade_dispatches_returned: <n>`). A PEND with the three competing positions shown is more useful than a silent stall.

Rationale: design audit 2026-05-26 (Reviewer 6) flagged that the 6th/7th cascade dispatch hanging on a slow/near-budget session would burn cost and write no run report (the badge never fires). This guard makes the failure **graceful and visible** instead of silent. The 1-1-1 path that triggers the cascade is rare in practice (≈8% of Trias runs — see `scripts/vote_degeneracy.py`), so the guard protects a real but infrequent tail.

## Skip Trias if
- Diff ≤ 15 lines / 1 file — `scope_gate.py` will skip anyway (`max_lines: 15`, `max_files: 1` in its DEFAULT_CONFIG)
- Strict conservatism required (aggregated Trias is −18% Conservator)
- Obvious bugfix — Sequential blind is enough

## trias_split — REMOVED

`trias_split` is no longer a user-selectable mode. With Trias reduced from 9 to 3 sub-agents at the time of deprecation (since grown to 6 with the per-personality Skeptic challenge, 4× Sequential), `trias_split`'s 3.3× cost advantage over the old 9× Trias no longer exists — both are now effectively the same cost tier. Use standard `trias` instead.

The `_LEGACY_MODE_ALIASES` entry that mapped legacy `trias_split` runs to `trias` was removed on 2026-09-21, when its dated milestone passed. Historical `trias_split` runs still validate: `telemetry.mode` is an open string, so they just skip the per-voice telemetry check.

<!-- implements: CONSILIUM-MODE-TRIAS-001 -->

