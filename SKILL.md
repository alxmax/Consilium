---
name: consilium
description: Evaluate code changes through Generator/Control/Conservator deliberation. Use when reviewing PRs, planning refactors, assessing risk of proposed changes, before committing non-trivial changes, before implementing non-trivial features (to catch missing tests and prevent code loss), or when uncertain between multiple implementation approaches.
---

# Consilium — Code Deliberation Skill

Multi-perspective deliberation pattern for any code change. Three independent voices collaborate to evaluate a change:

- **Generator** (creative) — proposes alternatives, divergent thinking
- **Control** (analytical) — verifies technical correctness
- **Conservator** (prudent) — evaluates risk and reversibility

Reference material (calibration caveats, Step 7 lookup table, script table, maintenance rules) lives in [docs/skill-reference.md](docs/skill-reference.md); each step links the section it needs.

## Constitution

Four principles that govern **every** deliberation. They take priority when a voice gives a recommendation that conflicts with them.

1. **Think before coding.** Expose tradeoffs explicitly. If the request has 2 plausible interpretations, list them as separate `candidates` — do not silently pick one.
2. **Simplicity first.** Minimum code. Refuse speculative abstractions and unsolicited features. `do_nothing` is always in the candidate list.
3. **Surgical changes.** Touch only what the goal requires. Conservator measures drift via `scope_drift` — respect a high score.
4. **Goal-driven execution.** Restate the goal as a testable **success criterion** before Generator. The final output includes a **verification** step.

## When to use

Activate this skill when:
- Doing a **PR review** or diff
- Planning a **refactor** that touches 2+ files
- You must choose between **multiple approaches**
- You are about to **commit to shared/core code**
- You want a **risk assessment** before accepting a suggestion
- You are about to **implement** non-trivial functionality (>1 file or >30 lines)
- You want to verify that a completed implementation has not lost existing functionality, edge cases, or tests

Keywords: "review PR", "evaluate change", "refactor planning", "risk assessment", "should I commit", "which approach", "before implementing", "implement feature", "code quality", "missing tests".

## Workflow

### Pipeline at a glance

| Stage | Name | Steps |
|-------|------|-------|
| 1 | Setup | **0** Bootstrap · **1** Gather & Goal · **1.5** Scope Gate · **1.6** Consent Gate |
| 2 | Generator | **2** Produce alternatives (runs FIRST) |
| 3 | Risk & Verify | **3** Conservator · **4** Control |
| 4 | Aggregate | **5** Aggregate · **5b** Confidence · **5d** Retry (optional) |
| 5 | Output | **6** Report · **7** Auto-pipeline |

**Pipeline Invariants:**

| Step(s) | Status |
|---------|--------|
| 0 · 1 · 2 · 3 · 5 · 5b · 6 | mandatory |
| 1.5 | auto — scope gate, fails open; skippable for non-diff tasks |
| 1.6 | auto — consent gate, fails **safe**; pre-dispatch (before Generator) |
| 5d | conditional — only when `confidence < 0.7` and `chosen` non-null, non-headless |
| 7 | **auto-dispatch** when prompt declares deliverables (no confirmation); opt-in otherwise |

---

## Stage 1 — Setup

### 0. Bootstrap (before any grep / Read on the codebase)
Two actions in order:

1. **Read the contracts required by the mode** — minimum 3 core voices: `prompts/voices/generator.md`, `prompts/voices/control.md`, `prompts/voices/conservator.md`. Dialectic and skeptic modes also read `prompts/voices/skeptic.md`; Trias also reads `<personality>_lens.md` (`essentialist_lens.md`, `verifier_lens.md`, `sentinel_lens.md`). They define the exact fields produced by each voice. **Sub-agent dispatch note:** the content of each prompt must be *inlined* into the sub-agent dispatch — reading at Step 0 is not enough. For a non-default mode, also read `modes/<mode>.md` (full mode workflow + machine-readable config).
2. **Run `python scripts/priors.py --label "<short task label>"`** — soft priors from `FEEDBACK.html` + `runs/`; `--label` also checks for a matching prior authoritative run (see **Prior-deliberation passthrough** below). Fields to act on:
   - `stale_pendings` non-empty (PEND older than 2 days): ask *"You have N old PEND entries: [date | chosen] × N. Want me to close them (OK/BAD/unverified/skip)?"* — update via `mark_outcome.py --date <d> --chosen <id> --outcome OK|BAD|CLOSED_UNVERIFIED` (preferred; OK/BAD only on evidence the approach worked or failed, `CLOSED_UNVERIFIED` when there is none) or `Edit` on `FEEDBACK.html`. **Do not** use `log_feedback.py` — it duplicates the row.
   - `missing_feedback_runs` non-empty: run `python scripts/audit_feedback.py --backfill`, then resolve the new PEND rows as above. If the list is larger than 3, resolve the gap *before* a new deliberation.
   - `pend_pressure > 0.3` (PEND ratio in the last 10 entries): soft alert *"{pend_count}/{window_size} recent entries are PEND — consider closing them?"* — do not block.
   - `prompt_drift` non-empty (advisory, non-blocking): surface *"{changed_files} prompt/mode file(s) changed since last deliberation ({since_run})"*; inspect with `python scripts/version.py --drift <since_ref>`.

   **Headless** (`claude -p` or CI): `priors.py` detects it from explicit signals only — `--headless`, `CONSILIUM_HEADLESS=1` or `CLAUDE_HEADLESS=1` — and returns `stale_pendings`/`missing_feedback_runs` as `[]` and sets `headless_mode: true`. Log warnings to stderr, never prompt; run `audit_feedback.py --backfill` automatically.

   **Prior-deliberation passthrough.** If `priors.py --label` returns a non-null `prior_deliberation_match` (outcome OK, within 30 days, label substring match), ask:
   > *"Prior deliberation found: `<match.chosen>` (`<match.date>`, outcome=`<match.outcome>`). Proceed directly to implementation without re-deliberating?"*

   - **YES** → skip Steps 1–5; build this report and go to Step 7:
     ```json
     {
       "success_criterion": "<current task>",
       "chosen_approach": "prior-deliberation",
       "verification": "manual — implement per prior run's chosen_approach",
       "alternatives": [],
       "voice_scores": null,
       "confidence": 0.90,
       "pipeline_executed": false,
       "deliberation_log": [{"step": "prior_deliberation_passthrough", "matched": "<match.chosen>", "date": "<match.date>"}],
       "telemetry": {"mode": "prior_deliberation_passthrough", "dispatch_count": 0, "consilium_version": "<python scripts/version.py>", "consilium_ref": "<python scripts/version.py --ref>"}
     }
     ```
   - **NO**, **headless**, or `CONSILIUM_FORCE_FULL=1` → run the full pipeline from Step 1.

   **User-spec passthrough (explicit fiat only).** If the user *explicitly* supplies `chosen_approach`, `success_criterion` and `verification` (stated or directly derivable) AND an unambiguous skip instruction ("skip deliberation", "implement exactly this, no deliberation"), build the same report with `"chosen_approach": "user-spec"`, the user's criterion and verification, `deliberation_log: [{"step": "user_spec_passthrough", "spec": "<one-line summary>"}]` and `"telemetry": {"mode": "user_spec_passthrough", "dispatch_count": 0, "consilium_version": "<python scripts/version.py>", "consilium_ref": "<python scripts/version.py --ref>"}`, then go to Step 7. Never infer the fiat — a detailed request without the explicit skip instruction gets the full pipeline. Step 7 runs **with all gates intact** (routing, red→green gate, Reviewer); persist + log like any run. Headless works identically (the instruction is the consent).

### 1. Gather context & state the goal
Read the proposed change. Identify scope (files, modules, lines), type (bugfix/feature/refactor/cleanup), blast radius. Formulate `success_criterion` — a testable sentence.

**Clarity gate.** Before Generator: *can you write 2+ plausible distinct interpretations?* If yes — Stop, list them, ask which is the real one. Red flags: vague verbs without a concrete object, undisambiguated references, implicit scope, missing limits. If all are clear → continue without asking. **Non-interactive exception (subagent):** you cannot ask the user — emit each interpretation as a Generator candidate with prefix `interp_a_*`, `interp_b_*` and document the branches in `subagent_notes.clarity_branches`.

### 1.5. Scope gate (auto)
```bash
python scripts/scope_gate.py            # working tree vs HEAD
python scripts/scope_gate.py --ref main # main..HEAD
```
If `should_skip: true`, emit the minimal report and stop:
```json
{
  "success_criterion": "...", "verification": "...",
  "chosen_approach": "skipped", "skipped": true,
  "skip_reason": "...", "signals": {"files_changed": 1, "lines_changed": 4, "blocklist_hits": []},
  "voice_scores": null, "confidence": null, "alternatives": [], "deliberation_log": []
}
```
Defaults: `max_files=1`, `max_lines=15`, conservative blocklist (`auth/`, `security/`, `migrations/`, `.github/workflows/`, `**/*secrets*`, `.env*`, `Dockerfile`, `*.tf`, dependency files). Override via `scope_gate.json` (`{max_files, max_lines, blocklist}`). Escape hatch: `CONSILIUM_FORCE_FULL=1` forces `should_skip=false`. Gate **fails open** (no repo / bad ref → `should_skip: false`). **Non-diff tasks** (audit, architecture review, planning): skip Step 1.5.

### 1.6. Pre-dispatch consent gate (auto)
Generator runs **first**, so the irreversibility consent gate fires **before any voice**. Read `consent_required` (and `signals.blocklist_hits`) from the scope_gate output:

- `consent_required: true` (auth, migrations, CI, secrets, deps — or an undeterminable change) → **stop and ask**: *"This change touches an irreversible/sensitive path. Confirm you want to proceed before I deliberate?"* Proceed only on explicit YES. **Headless** (`is_headless()`): do not block; set `metadata.headless_overridden: true` and continue.
- **Text markers complement the path signal:** irreversible-action language ("DROP TABLE", "delete all", "no way back", "force-push", "publish/break API") with no documented consent also counts as `consent_required`.
- **Fail-safe, not fail-open.** A probe/config failure returns `consent_required: true`. Conservator's `irreversibility_flag` (Step 3) is the backstop.

**Non-diff tasks:** skip Step 1.6 unless the request text itself carries irreversible-action language.

## Stage 2 — Generator

### 2. Generator — produce alternatives (runs FIRST)
Use `prompts/voices/generator.md`. Runs **before** Conservator and Control and **receives no Conservator output** — blind to risk framing (anti-anchoring). Request **3–5 candidates** (including `do_nothing` and any `adversarial_*`). Generator **self-scales** candidate count/detail from the blast radius; default to 3 candidates when the signal is unclear.

Output: `{candidates: [{id, summary, sketch, rationale, downside_estimate}], fallback_scenario, coverage_check, challenge_upward, abstain, preferred}`. Adversarial is conditional (shared/core code OR a function with >3 external callers) — otherwise emit `"adversarial_skipped": "<reason>"`. Unconventional is included by default — emit `"unconventional_skipped": "<reason>"` when omitting.

**Challenge upward:** if `challenge_upward.triggered: true`, forward the flag into Conservator's input so it scales up its scrutiny (one-way signal, not a re-run).

## Stage 3 — Risk & Verify

### 3. Conservator — assess risk (runs after Generator)
Use `prompts/voices/conservator.md`. Receives **Generator's candidates** and scores the risk of each. Its `tokens_budget.control` output caps how deep Control goes.

**Memory context:** prepend the output of `python scripts/priors.py --memory-summary --label "<task label>"` (2–3 lines) to Conservator's input — after Generator's candidates, before the required questions. Skip silently when empty.

Required Questions (Q1-Q5): reversibility, magnitude, counterparty_risks, status quo bias check, meta_recommendation.

Output per candidate: `{id, regression_risk: {reversibility, magnitude, net_concern}, counterparty_risks, bias_check, meta_recommendation, tokens_budget: {generator, control}, irreversibility_flag, rollback_recipe, notes}`. Magnitude/reversibility labels flip between runs on ambiguous inputs — see [calibration caveats](docs/skill-reference.md#calibration-caveats-steps-3-5-5b).

**Veto check (auto, after Conservator output):**
- `irreversibility_flag: true` (backstop — Step 1.6 did not already obtain consent) → ask: *"Conservator marks this decision as irreversible. Do you confirm you want to continue?"* — proceed only on explicit YES. **Headless**: do not block; set `metadata.headless_overridden: true` and continue.
- `meta_recommendation: scale_down` → **short-circuit**: skip **Control** (Generator already ran) and build the report directly:
  ```json
  {
    "success_criterion": "<input success_criterion>",
    "verification": "manual review (scope_gate determined trivial)",
    "chosen_approach": "trivial-direct",
    "alternatives": [],
    "voice_scores": {"conservator": "<conservator net_concern>"},
    "confidence": 0.85,
    "pipeline_executed": false,
    "deliberation_log": [{"step": "scale_down_short_circuit", "reason": "<conservator notes>"}],
    "telemetry": {"mode": "sequential_scale_down", "dispatch_count": 2, "consilium_version": "<python scripts/version.py>", "consilium_ref": "<python scripts/version.py --ref>"}
  }
  ```
  `confidence: 0.85` is deliberate — it stays above the `< 0.7` retry (5d) and override-prompt (Step 6) thresholds. **Dialectic exception:** in `dialectic` mode the Skeptic stage still runs on the trivial-direct answer; `can_object: true` with a concrete constraint → log `skeptic_caught_constraint: true` and reconsider (advisory unless `--skeptic-can-override`). See `modes/dialectic.md`.
- `meta_recommendation: scale_up` → warn user, add context request. **Headless**: warn on stderr and continue with existing input.

**Optional — autoprobe:** `python scripts/probe_change.py [--ref main --churn 30]` — anchor `magnitude` to `files_changed/lines_*` and `regression_risk.net_concern` to the churn distribution when present.

### 4. Control — verify correctness
Use `prompts/voices/control.md`. Per candidate: types, logic, tests, style. **Receives** full Generator output + full Conservator output.

Required Questions (Q1-Q5): glossary (max 5), hidden_assumptions (max 3), disagreements, fixed/negotiable_constraints, mandatory dissent (`strongest_objection` / `no_blocking_defect_attested` — exactly one set). Q5 is orchestrator-advisory: when `strongest_objection.target_id` is non-null (especially if it names the eventual chosen), surface it as a caveat in the report.

Output: `{glossary, hidden_assumptions, disagreements, fixed_constraints, negotiable_constraints, glossary_fail, glossary_attempts, verdicts: [{id, valid, confidence_in_verdict, issues, tests_to_write, notes}], strongest_objection, no_blocking_defect_attested}`. `tests_to_write` mandatory for `valid: true` (except `do_nothing`) — 1-4 acceptance tests.

**Post-Control veto check:** `glossary_fail: true` → BLOCK, request reformulation. Any `disagreements` of `type: substantial` → REWORK: re-run Generator with clarification before aggregating.

## Stage 4 — Aggregate

### 5. Aggregate
```bash
python scripts/aggregator.py --scheme conservative_override
```
Default **conservative_override** — veto at `risk_score > 0.8` (strictly greater: `0.80` is NOT vetoed, `0.81` IS); ranking by weighted average `(generator + control + safety)` with `safety = 1 - conservator`; ties go to the safer candidate. Alternative: `--scheme risk_adjusted_utility` (sigmoid penalty, no rigid veto). All schemes + input shapes: [modes/aggregator_schemes.md](modes/aggregator_schemes.md).

### 5b. Confidence
```bash
echo '{"candidates": [...], "chosen": "approach_id"}' | python scripts/confidence.py
```
Returns `{confidence, agreement, separation}`; `confidence` is `null` when `chosen` is `null` (all vetoed) and Step 5d is then skipped. It is an internal-consistency signal, not a calibrated probability ([caveats](docs/skill-reference.md#calibration-caveats-steps-3-5-5b)). **Advisory:** it does not predict outcomes (64 `[confirmed]` FEEDBACK outcomes: Brier 0.163 vs 0.085 for the base rate; OK-rate 0.92 at ≥ 0.7 vs 0.90 below), so it no longer auto-dispatches the Skeptic; the thresholds below are heuristics. Formula, vote-pattern path, floors: [modes/confidence.md](modes/confidence.md). Pass JSON via stdin or `--input <file>`, not inline `-c "..."` (quoting breaks).

**Mode confidence floor.**
```python
import sys; sys.path.insert(0, "scripts")  # scripts/ is not a package; confidence.py uses flat sibling imports
from confidence import check_mode_floor
result = check_mode_floor(telemetry_mode, confidence_value, vote_pattern)  # vote_pattern only for trias; omit/None otherwise
# result["below_floor"] == True → log with --outcome WEAK in FEEDBACK.html
```
Floors: `sequential=0.70`, `dialectic=0.75`, `trias=0.80`. **Trias exemption:** decisive vote patterns (`3-0`/`2-1`/`2-0`) are exempt from WEAK — `2-1` (0.75) and `2-0` (0.70) sit structurally below 0.80; pass `vote_pattern`.

### 5d. Retry on low confidence (optional, single pass)
If `confidence < 0.7`, **before** asking the user: identify the single question whose answer would discriminate the top-2 candidates (an unverified assumption, a file you haven't read, an empirical check you can run). Gather that evidence yourself (Read + Grep + smoke-run), then re-run Generator/Control/Conservator **once** with the enriched input. If confidence is still < 0.7, only then ask the user (Step 6). **Headless:** skip Step 5d; go to Step 6 (`PEND_HEADLESS`).

## Stage 5 — Output

### 6. Report

**Telemetry (mandatory — accumulate in the bundle before `build_report.py`).** A run without telemetry is invisible to cost analysis.
- `telemetry.voices.<voice_name>`: `{tokens_in: ceil(len(prompt)/4), tokens_out: ceil(len(response)/4), latency_ms}` — prompt = full text sent; sum across retries of the same dispatch.
- `telemetry.mode` ← canonical label (`"sequential"`, `"trias"`, …); `telemetry.dispatch_count` ← total dispatches incl. retries.
- `telemetry.lens_applied` ← only on an opt-in `--lens` run: `{decider, skeptic?}`; for Dialectic `decider` ≠ `skeptic` (`validate_report.py` enforces it).
- `telemetry.consilium_version` / `consilium_ref` ← stamped by `build_report.py` (and by the hand-built templates above); see `scripts/version.py`.

Bundle schema: `{success_criterion, verification, generator, control, conservator, aggregate, confidence, telemetry}`. `build_report.py` derives `voice_scores`, `alternatives` (with `why_not`) and `deliberation_log`. It accepts only an `AGGREGATE` result (which carries `chosen`) or a `skipped` bundle — `BLOCK`/`REWORK`/`ESCALATE`/`ADAPT_EXTENDED` are handled by the orchestrator before Step 6 ([interception contract](docs/skill-reference.md#step-6--interception-contract)).

**Output JSON** (required fields — validated by `validate_report.py`, required by Principle #4):
```json
{
  "success_criterion": "<string — testable sentence>",
  "chosen_approach": "<id from candidates | null>",
  "verification": "<command or concrete check>",
  "alternatives": [{"id": "...", "summary": "...", "why_not": "..."}],
  "voice_scores": {"generator": 0.0, "control": 0.0, "conservator": 0.0},
  "confidence": 0.0,
  "deliberation_log": [{"step": "generator|control|conservator|aggregate", "...": "..."}]
}
```

**Terminal output discipline.** Do not write intermediate `bundle_*.json` to disk; pipe outputs. The only terminal output at the end:
```
chosen: <id> | conf: <X> | .consilium/runs/<file>.json
```

**Final actions (mandatory — the deliberation is not complete without them; a report not logged is invisible to priors):**

1. **Persist + validate** to `.consilium/runs/YYYY-MM-DD_HHMM_<label>.json` — build to a `.partial`, validate it, and only then `mv` it into place, so an invalid run is never committed (`validate_report.py`: exit 0 OK, 1 missing/empty field or bad telemetry, 2 malformed JSON).
2. **Log to `.consilium/FEEDBACK.html`** (never skipped). The outcome is not known yet, so the row starts as **PEND** — confidence measures agreement between voices, not whether the choice worked:
   - default (any confidence, incl. `null`) → `python -X utf8 scripts/log_feedback.py --run-path .consilium/runs/<file>.json < .consilium/runs/<file>.json`
   - `confidence < 0.7` → first ask: *"Confidence below threshold (`<X>`). Want to override `<chosen>`? Alternatives: `<alt_ids>`. Reply alt_id, 'no', or 'skip' — or rerun with `--mode dialectic` / `--skeptic-on-chosen`."* `<alt_id>` → add `--outcome OVR --override-target <alt_id>`; `no` / `skip` → the default PEND call.
   - **Headless** → `--outcome PEND_HEADLESS` (excluded from `pend_pressure` and `stale_pendings`; no manual resolution).
3. **Close the row on evidence** (the only way a run becomes OK): when the report's `verification` passes (Step 7 or later), `python scripts/mark_outcome.py --run-path .consilium/runs/<file>.json --outcome OK --reason "verification passed: <command>"`; when reality refutes the choice, `--outcome BAD`. Both add the `[confirmed]` marker — `priors.py` computes its rates from confirmed rows only. `log_feedback.py --outcome OK` is refused without `--confirmed`.

When no override prompt is needed (`confidence >= 0.7`, or headless with `--outcome PEND_HEADLESS`), run the tail as **one** `&&`-chained call (fewer turns, ~4–5% cheaper):
```bash
python scripts/build_report.py < bundle.json > .consilium/runs/<file>.json.partial \
  && python scripts/validate_report.py < .consilium/runs/<file>.json.partial \
  && mv -f .consilium/runs/<file>.json.partial .consilium/runs/<file>.json \
  && python -X utf8 scripts/log_feedback.py --run-path .consilium/runs/<file>.json < .consilium/runs/<file>.json
```
On a validate failure, delete the `.partial`, fix the bundle and re-run. **Do not chain** when the `confidence < 0.7` override prompt must run between validate and log.

Outcome details and scale_down regret tracking: [docs/skill-reference.md](docs/skill-reference.md#step-6--outcome-confirmation-retroactive).

### 7. Auto-pipeline (post-report)

**Mandatory — auto-dispatch (no confirmation prompt) if the user's prompt contains a header of the form `**Required output file(s):**` or `**Deliverable(s):**` (with or without colon, singular or plural) — authoritative detection regex: `\*\*\s*(?:Required\s+output\s+files?|Deliverables?)\s*\*\*\s*:?` applied per whole line, case-insensitive.** Step 7 then fires automatically after Step 6:

```
Agent(subagent_type="consilium-implement-subagent",
      prompt="Implement the chosen approach from .consilium/runs/<file>.json. Spec is the report.")
```

**Preconditions (skip with visible error if not met):** `chosen_approach` ∉ `{do_nothing, skipped}` AND `success_criterion` non-empty AND `verification` non-empty. If one fails, emit an error in the response and stop — do not dispatch. If the prompt declares deliverables and the deliberation still chose `do_nothing`, emit a hard error: *"deliberation chose `do_nothing` on a prompt with declared deliverables — the user must decide"* — never a silent skip.

**Mode-agnostic:** the dispatch is identical for sequential, dialectic and trias. The validated report is the spec; the subagent routes internally via `recommend_implement_mode()` — single-shot for greenfield, **Coder → (Test Writer ∥ Reviewer)** for regression-risk quadrants (Reviewer reuses `prompts/voices/control.md`). Declared files must exist on disk (Write tool) before the turn closes, not only as fenced blocks in chat. Full spec: [modes/implement_pipeline.md](modes/implement_pipeline.md).

**Opt-in otherwise** — without declared deliverables (audit, "should I commit", "which approach"), Step 7 is at the user's discretion; on confirmation, dispatch the same call. To inspect the inferred steps first:
```bash
python scripts/infer_pipeline.py --input .consilium/runs/<file>.json --dry-run   # print only; --yes for CI/headless
python -X utf8 scripts/implement_pipeline.py --input .consilium/runs/<file>.json --dry-run   # print dispatch plan
```
Lookup table and step definitions: [docs/skill-reference.md](docs/skill-reference.md#step-7--inferred-implementation-steps). **Headless:** run with `--yes`; Step 7 stays mandatory when deliverables are declared. **After implementation:** run the report's `verification`; if it passes, close the FEEDBACK row as OK via `mark_outcome.py` (Step 6, action 3).

## Feedback loop & memory

All deliberation state lives under **`.consilium/`** in the current project, or under `$CONSILIUM_DATA_DIR` when set — never in the install directory (paths in `scripts/utils.py`): `.consilium/runs/*.json` (one report per deliberation, schema in `docs/runs-schema.md`) and `.consilium/FEEDBACK.html` (one row per use: `date | context | chosen | outcome | note`, outcome `OK`/`BAD`/`OVR`/`PEND`). `mark_outcome.py` adds a `[confirmed]` marker; `priors.py` rates only confirmed rows. `CLOSED_UNVERIFIED` closes a PEND with no evidence either way. Memory tiers (short/medium/long): `scripts/memory.py --tier <short|medium|long|all>`; see [docs/memory-tiers.md](docs/memory-tiers.md). Storage details: [docs/skill-reference.md](docs/skill-reference.md#feedback-loop--storage-details).

## Headless invariants

When `CLAUDE_HEADLESS=1` (set by the external orchestrator that invoked `claude -p`; strict boolean, helper `from utils import is_headless`), user-facing prompts are replaced by documented defaults. `is_headless()` false → behavior unchanged.

| Step | Headless default |
|---|---|
| 0 (`stale_pendings`, `missing_feedback_runs`, `pend_pressure`) — via `priors.py` (`--headless` / `CONSILIUM_HEADLESS=1` / `CLAUDE_HEADLESS=1`) | log warning to stderr + continue; run `audit_feedback.py --backfill` automatically |
| 1.6 / 3 (`consent_required` / `irreversibility_flag`) | set `metadata.headless_overridden: true` in bundle + continue (the orchestrator has assumed the stake) |
| 5d (retry on low confidence) | skip entirely; go directly to Step 6 with `PEND_HEADLESS` |
| 7 (auto-pipeline) | run with `--yes`; **mandatory** when the prompt declares deliverables (Step 7 regex) — writing the declared files is part of the contract |

**Pipeline-execution contract.** Every `/consilium` invocation MUST end by writing a report to `.consilium/runs/` (a real, `skipped` or `trivial-direct` one). The skill cannot self-enforce this; an orchestrator detects a skipped deliberation by the absence of a fresh report ([details](docs/skill-reference.md#headless--pattern-and-pipeline-execution-contract)).

## Modes

Dispatch defaults: all voices on `model: "sonnet"`; in Trias each personality uses the model from `scripts/personalities.py` (all three → `sonnet`). Each mode file in `modes/` carries YAML frontmatter (`name`, `subagents`, `cost_multiplier`, `confidence_floor`, `models`) — the single source of truth for mode config. Read it at Step 0 before running a non-default mode.

| Mode | File | Subagents | Cost | Conf. floor |
|---|---|---|---|---|
| Sequential (default) | [modes/sequential.md](modes/sequential.md) | 1 | 1× | 0.70 |
| Dialectic | [modes/dialectic.md](modes/dialectic.md) | 2 | 1.33× | 0.75 |
| Trias | [modes/trias.md](modes/trias.md) | 4 (worst: 7) | 2.67× | 0.80 |
| skeptic_on_chosen (flag) | [modes/skeptic_on_chosen.md](modes/skeptic_on_chosen.md) | +1 over base | base+1 | N/A |

Cost multipliers are sub-agent-count estimates, not measured run costs; Trias's 2.67× was token-checked only as a 4-vs-6 spawn ratio on n=2 problems (`experiments/trias-6to4-cost-2026-06-19.md`).

- **Sequential** — Generator → Conservator → Control inside 1 dispatched sub-agent that returns the three raw voice outputs; the orchestrator aggregates in its own context.
- **Dialectic** (opt-in) — Sequential + 1 Skeptic sub-agent on the chosen answer; code context (language, files, tests, CI gate) injected into voice inputs.
- **Trias** (high-stakes opt-in) — 3 personalities (Essentialist/Verifier/Sentinel) each run Sequential blind, then a democratic vote, then **one** post-vote Skeptic (`skeptic_on_chosen`; `--skeptic-can-override` re-votes excluding a demolished winner). Lazy routing: low/medium → Sequential, high → Dialectic, only `critical` → full Trias. Never auto-triggers.
- **`skeptic_on_chosen`** (flag over any mode) — opt-in via `--skeptic-on-chosen`, plus the non-confidence triggers in its mode file (high Conservator concern, similar recent BAD, irreversibility). Not triggered by confidence (see 5b). Advisory by default; `--skeptic-can-override` opts in.
- **`--lens <name>`** (flag, default OFF) — prepends one lens (`essentialist` | `verifier` | `sentinel`) to Sequential's voices; in Dialectic (`--lens essentialist`) Essentialist goes on the decider and the Verifier lens tints the Skeptic (decider ≠ skeptic). No extra sub-agent, but ~18% more prompt tokens per voice; value unproven. Records `telemetry.lens_applied`.
- **Parallel** — removed; legacy `mode: "parallel"` runs still validate.

`modes/` also holds reference docs for sub-components: [implement_pipeline.md](modes/implement_pipeline.md) (Step 7), [aggregator_schemes.md](modes/aggregator_schemes.md) (Step 5), [confidence.md](modes/confidence.md) (Step 5b).

## Routing boundary

| Decision profile | Mode |
|---|---|
| One nagging concern about the chosen answer | `dialectic + skeptic_on_chosen` |
| 2+ plausible architectural approaches without clear winner | `trias` |
| `magnitude = critical` AND `reversibility = irreversible` | consider `trias` (select explicitly) |
| Bugfix evident OR diff ≤15 lines / 1 file | Sequential (scope_gate skips — `max_lines: 15`, `max_files: 1`) |
| All other PR-level reviews | Sequential |

## Veto triggers (quick reference)

| Trigger | Source | Effect | Action |
|---|---|---|---|
| `consent_required: true` | scope_gate (Step 1.6) | BLOCK (hard) | Ask user for explicit consent **before Generator** (pre-dispatch) |
| `irreversibility_flag: true` | Conservator | BLOCK (backstop) | Ask consent before finalizing (Step 1.6 already gates the common case) |
| `glossary_fail: true` | Control | BLOCK (soft) | Ask user to reformulate with operational terms |
| `disagreements: substantial` | Control | REWORK | Re-run Generator with clarification context |
| `meta_recommendation: scale_down` | Conservator | ADAPT_SHORT | Short-circuit: skip Control (Generator already ran), emit trivial-direct report (`pipeline_executed: false`) |
| `meta_recommendation: scale_up` | Conservator | ADAPT_EXTENDED | Warn user, add context before Generator |
| 3+ of above simultaneously | Aggregator | ESCALATE | Present trigger table to user, request decision |
