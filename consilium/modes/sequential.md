---
name: sequential
subagents: 1
cost_multiplier: 1.0
confidence_floor: 0.70
models: sonnet
dispatch_count: 3
description: Default mode — Generator, Conservator, Control run together inside one dispatched sub-agent call; the orchestrator implements the chosen approach fresh, in its own context.
---

# Sequential mode (default)

**Mechanics:** Generator → Conservator → Control run together inside **one dispatched sub-agent call**, not the orchestrator's own context. Internally the sub-agent still runs all three roles in a single shared context — `strip_context.py` still strips the prior voice's prompt between turns (Steps 3-4), and Generator still gets genuine turn-1 blindness to risk framing — this part is unchanged from the pre-2026-07-07 architecture. What changes: the sub-agent returns the three raw voice outputs (`generator_out`, `control_out`, `conservator_out`) **unchanged** — no compressed or reshaped schema — and the orchestrator feeds them into `aggregate_sequential()` exactly as before, then implements the chosen approach in its own fresh context, without carrying forward the deliberation's accumulated history. Cost: 1× (baseline, by definition — see Accepted tradeoffs below for what this figure does and doesn't currently measure).

**Why dispatch, not in-context.** Isolating the deliberation into its own sub-agent context keeps the implementation phase from inheriting the deliberation's growing context (candidate JSON, rejected alternatives, risk scoring) — previously Sequential's structural gap relative to Trias/Dialectic's sub-agent-based modes. See **Accepted tradeoffs** for what this trades away.

## Accepted tradeoffs (2026-07-07 override)

This architecture was reviewed twice, same day, by an independent internal design review and returned **MODIFY** both times (DEEPLY_SPLIT in round 1, MODIFY in round 2 after focal cross-examination). The user reviewed both verdicts explicitly and instructed an override. Shipped anyway, with these specific risks disclosed rather than silently absorbed:

- **Likely net cost increase, not a proven saving.** A freshly dispatched sub-agent does not inherit the orchestrator's warm prompt-cache — isolating the deliberation into its own context probably trades the prior accumulated cache-read cost for a cold, full-price re-read of whatever context the sub-agent needs, rather than eliminating cost. This was not measured before shipping.
- **Trias's atomic-dispatch precedent does not transfer.** Trias isolates each personality to protect independent-lens *voting* integrity across 3 personalities. Sequential has no vote and nothing on that axis for isolation to protect — citing Trias as justification (as the original proposal did) was an invalid analogy, not merely under-evidenced (design review, round 2).
- **Doc-drift coverage gap (follow-up, not yet done).** The repository's doc-drift checker (`check_doc_drift.py`) has no invariant tying Sequential/Dialectic's `subagents` count to this file, `SKILL.md`'s mode table, or `docs/architecture/src/*.jsx` — today only Trias and the implement pipeline are drift-gated. Consistency across those three surfaces was checked by hand for this change; it is not CI-enforced yet.

**Instrumentation fix shipped alongside this change.** `telemetry.voices.*.latency_ms` was previously hardcoded to `0` for every in-context voice — the actual driver that made the cost-increase risk above unmeasurable at review time. Now that Sequential is a real dispatch, the orchestrator records the sub-agent Agent-call's actual wall-clock duration (dispatch start → return) as `telemetry.voices.sequential_dispatch.latency_ms`; per-voice (Generator/Conservator/Control) breakdown remains best-effort (the sub-agent may report its own internal per-turn timings if it tracks them, but is not required to). This does not retroactively validate the cost claims above — it only makes the next comparison measurable.

`strip_context.py` applies ONLY in Sequential mode (Steps 3-4, within the sub-agent's own turn sequence) — it strips the prior voice's prompt before the next voice runs. Trias isolates voices by separate per-personality dispatch instead, so it does not use it.

## Three-layer architecture

| Layer | Components | Role |
|---|---|---|
| **Deliberation** | Generator → Conservator → Control | Runs on every user question |
| **Aggregation** | aggregate_sequential() with 8-component veto cascade | Synthesizes voice outputs, decides what user sees |

## Dispatch order

Default order: **Generator → Conservator → Control**

1. Generator runs first, **blind to risk framing** (anti-anchoring), and self-scales its depth from the change's blast radius — there is no upstream `tokens_budget`
2. Conservator receives Generator's candidates, scores risk per candidate, and sets `tokens_budget.control` for Control
3. Control receives full outputs from both Generator and Conservator

The irreversibility consent gate runs **pre-dispatch** (SKILL.md Step 1.6, `scope_gate.consent_required`), before Generator — so an irreversible change is gated before any generation effort is spent. Conservator's `irreversibility_flag` is the backstop. `scale_down` (Conservator, now second) short-circuits by skipping **Control only** — Generator has already run.

**Role separation, not Chinese wall (within the dispatch).** Inside its one dispatched sub-agent call, Sequential still runs the same LLM playing three roles in one context; `strip_context.py` strips the prior voice's prompt, but does not clear the model's in-context memory — unchanged by the move to sub-agent dispatch. Reordering changes *speaking order*, not voice-to-voice isolation: Generator still gets genuine turn-1 blindness to risk framing (Conservator has not run yet), but role prompts still provide separation, not true isolation, *between voices*. What the dispatch newly isolates is a different axis: the deliberation's context from the orchestrator's own subsequent implementation phase (see Mechanics above). True voice-to-voice isolation still requires Trias's 3 independent personality dispatches.

**Advisory.** When Conservator outputs `magnitude: critical` AND `reversibility: irreversible`, consider upgrading to **Trias** for true independent-context isolation across 3 personalities. Trias does not auto-trigger; select it explicitly.

## Veto powers

**Sub-agent return contract.** `aggregate_sequential()` is unmodified by the move to sub-agent dispatch: it still takes three separate dicts (`generator_out`, `control_out`, `conservator_out`) and still reads `irreversibility_flag`/`meta_recommendation` from inside `conservator_out["scores"][i]` per candidate. The dispatched sub-agent's job is only to *produce* those three dicts (internally, across its own Generator→Conservator→Control turns) and return all three raw — never a compressed or reshaped summary. This was a real correctness gap in the original proposal (caught by the Sentinel personality during the Trias implementation-planning deliberation, verified against `scripts/aggregator.py` by the post-vote Skeptic): an earlier draft of this change considered returning only `{chosen_approach, rationale, confidence}`, which would have silently disabled the entire veto cascade below (BLOCK/REWORK/SHORT-CIRCUIT/ESCALATE never firing for Sequential, since none of their trigger fields would exist on that shape).

The 8 design components (per spec): vocabulary_map, length_targets, priority_veto_order, tension_expose, metadata, user_profile, multi_confidence, escalation_rule. The `aggregate_sequential()` function produces 7 distinct routing outcomes derived from these components: `BLOCK` (glossary_fail), `BLOCK` (irreversibility), `REWORK`, `SHORT-CIRCUIT` (scale_down — skip Control), `ADAPT_EXTENDED` (scale_up), `ESCALATE` (3+ triggers), `AGGREGATE` (default).

| Trigger | Source | Effect | Action |
|---|---|---|---|
| `consent_required: true` | scope_gate (Step 1.6) | BLOCK (hard) | Ask explicit consent **before Generator** (pre-dispatch) |
| `irreversibility_flag: true` | Conservator | BLOCK (backstop) | Ask consent before finalizing (Step 1.6 gates the common case) |
| `glossary_fail: true` | Control | BLOCK (soft) | Ask user to reformulate with operational terms |
| `disagreements: substantial` | Control | REWORK | Re-run Generator with clarification context |
| `meta_recommendation: scale_down` | Conservator | SHORT-CIRCUIT | Skip Control (Generator already ran). Emit minimal report with `chosen_approach: "trivial-direct"`, `confidence: 0.85`, `pipeline_executed: false`. See SKILL.md Step 3 (authoritative). |
| `meta_recommendation: scale_up` | Conservator | ADAPT_EXTENDED | Warn user, add context |
| 3+ of above simultaneously | Aggregator | ESCALATE | Present trigger table to user, request decision |

## Failure-mode recovery

- **Sequential's dispatch crash / timeout:** retry the Agent call once; on a second failure, fall back to running Generator → Conservator → Control in the orchestrator's own context for this deliberation (the pre-2026-07-07 architecture) rather than leaving the user without a report.
- **Malformed JSON from a voice inside the dispatch:** reject that voice's output, treat as missing (`{}` for verdicts/scores, or `{"candidates":[]}` for generator) and continue with the others. Log the error in `deliberation_log` with step `"<voice>_parse_error"`.
- **Missing mandatory fields (e.g. `candidates` empty):** raise a warning in the terminal, skip the aggregator and emit a skipped report with `skip_reason: "voice output incomplete after retry"`.
- **strip_context.py** runs inside the dispatched sub-agent's own turn sequence (Steps 3-4) — it strips the prior voice's prompt between Generator/Conservator/Control turns. Trias's per-personality isolation and Dialectic's Skeptic dispatch are a different, coarser-grained isolation (whole-dispatch, not within-dispatch) and don't use it for that purpose.

## Optional personality lens (`--lens`, opt-in, default OFF)

By default Sequential runs **no lens** — the cost-safe baseline. A lens adds ~18% per-voice prompt tokens, so it is applied only on explicit request (this keeps the default path's cost unchanged). When invoked with `--lens essentialist`, prepend `prompts/voices/essentialist_lens.md` to each voice prompt (Generator→Conservator→Control), biasing perception toward first-principles minimalism. Record `telemetry.lens_applied: {"decider": "essentialist"}`; omit the field on a default no-lens run.

**Status: opt-in, value unproven** — see [modes/dialectic.md](dialectic.md) for the shared rationale and the governing 2026-07-07 design review. Ships OFF by default; a single-lens Sequential run has no vote to catch the lens's blind spot, so the bias is applied only on explicit request.

## When to use

- Default for all deliberations unless a higher mode is warranted
- Bugfix or <20-line diff — scope_gate will often skip automatically
- Low-stakes exploratory changes where isolation between voices is not needed
- Any deliberation where the user has not explicitly requested a higher mode

<!-- implements: CONSILIUM-MODE-SEQUENTIAL-001 -->


<!-- implements: CONSILIUM-MODE-LENS-001 -->
