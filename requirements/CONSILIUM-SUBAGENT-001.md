---
milestone: v1.1
id: CONSILIUM-SUBAGENT-001
status: confirmed
level: code
layer: bus
owner: alxmax
depends_on: [CONSILIUM-MODE-SEQUENTIAL-001]
test_exempt: "agent spec document — behavioral contract validated by consilium-subagent smoke tests and Trias/Dialectic integration runs"
satisfies: [ARCH-CONSILIUM-MODES-001]
---

# consilium-subagent

> WHY: Isolated-context deliberation wrapper that lets any orchestrator (Trias, Dialectic, Step 7) spawn a fresh Consilium run without polluting its own context with intermediate voice output. Sequential-only — no recursive Agent calls.

## WHAT — Contract (normative)
- The system provides a `consilium-subagent` agent that runs the full Sequential deliberation workflow (Steps 0–6 from SKILL.md) in an isolated context and returns a canonical `.consilium/runs/<ts>_<slug>.json` report as its final assistant message (no prose, no fences — raw JSON only).
- The subagent operates in Sequential mode only; if the dispatch input includes a `mode: parallel|dialectic` hint, the subagent logs it as ignored in `subagent_notes` and proceeds with Sequential.
- The subagent never prompts the user (non-interactive): stale PENDs are passed through as `subagent_notes.stale_pendings`; clarity branches are emitted as Generator candidates with `interp_a_*`/`interp_b_*` id prefixes; blocking gates produce `chosen_approach: null` with `subagent_notes.blocked_reason`.
- Final message contract: after `validate_report.py` exits 0 on the persisted report, the subagent emits exactly that file's contents as its final assistant message.
- Tool allowlist: `Read, Write, Bash, Grep, Glob`. No `Edit`, no `Agent` (nested dispatch is prohibited by rule).

## WHAT — Verify intent
- None — all questions resolved.

## HOW — Acceptance (= tests)
AC-1
  Given a dispatch prompt with a diff and a success_criterion
  When  the subagent runs
  Then  the final message parses as valid JSON, `python consilium/scripts/validate_report.py < <output>` exits 0, and exactly one new file appears under `.consilium/runs/`

AC-2
  Given a dispatch with `mode: dialectic` hint in the prompt
  When  the subagent processes the input
  Then  it logs the mode hint as ignored in `subagent_notes` and completes as Sequential

AC-3
  Given a low-confidence deliberation (3+ close candidates)
  When  the subagent completes
  Then  it does not stall — completes within a bounded turn count with outcome=PEND in FEEDBACK.html

## WHERE — Current implementation
- agents/consilium-subagent.md
