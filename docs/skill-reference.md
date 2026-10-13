# Consilium — skill reference

Reference material moved out of `SKILL.md` to keep the per-run contract small. `SKILL.md` stays authoritative for the workflow; each section here is linked from the step that uses it. Read a section only when that step sends you here.

## Calibration caveats (Steps 3, 5, 5b)

**Categorical flip caveat:** Conservator `magnitude`/`reversibility` labels have a ~40% inter-run flip rate on ambiguous inputs (experiment 2026-05-17). If the deliberation is sensitive to the magnitude/reversibility boundary, consider double-sampling.

**Aggregator veto threshold.** The 0.8 boundary has not been empirically validated in the [0.7, 0.9] region — boundary cases may fire non-deterministically until a follow-up stability experiment closes that gap (see `experiments/voice-score-stability-2026-05-17.md` F4).

> **Calibration (R2 audit 2026-05-17):** `agreement` measures divergence between roles within ONE run — not inter-run stability. Conservator scores are anchored by categorical formula (see `conservator.md`); Generator/Control scores are unanchored self-assigned floats. A second run with the same input may produce different scores (pstdev estimated 0.12–0.18 on `risk_score`). The `confidence` value is not a calibrated probability — it is an internal-consistency signal.

## Step 6 — interception contract

> **Interception contract.** `build_report.py` accepts only the `AGGREGATE` aggregate shape (which carries `chosen`) or a `skipped` bundle. The non-`AGGREGATE` results of `aggregate_sequential` — `BLOCK` (glossary_fail / irreversibility), `REWORK` (substantial disagreement), `ESCALATE` (3+ triggers), `ADAPT_EXTENDED` (scale_up) — are **interception points** the orchestrator handles *before* Step 6 (ask the user, reformulate, re-run). `ADAPT_SHORT` (scale_down) builds its `trivial-direct` report by hand (SKILL.md Step 3), not via `build_report.py`. So `build_report.py` raising `ValueError` on a `chosen`-less aggregate is the correct hard-fail for a contract violation, not a shape it is expected to render.

## Step 6 — outcome confirmation (retroactive)

**Outcome confirmation (retroactive).** The outcome logged in step 2 is subjective — it reflects the immediate impression. If production later reveals a regression or a good choice, overwrite it with the confirmed marker:
```bash
python scripts/mark_outcome.py --run-path .consilium/runs/<file>.json --outcome BAD --reason "broke prod migration"
```
The `[confirmed]` marker appears in the note; `priors.py` computes `bad_rate` from confirmed rows only (`unconfirmed_count` reports the rest).

**Scale_down regret tracking (A2).** If `telemetry.mode == "sequential_scale_down"` and the retroactive outcome is `BAD`:
```bash
python scripts/mark_outcome.py --run-path .consilium/runs/<file>.json --outcome BAD --reason "scale_down regret — full deliberation needed"
```
Calibration signal: if `scale_down` regret rate > 10% over n≥20 runs, Conservator's scale_down threshold is too aggressive — adjust the prompt. If the rate stays < 5%, the optimization is validated.

## Step 7 — inferred implementation steps

The script reads `chosen_approach`, `magnitude`, and `reversibility` from the report and looks up the table below:

| magnitude | reversibility | inferred steps |
|---|---|---|
| trivial | complete | implement |
| trivial | partial | implement → compile |
| trivial | irreversible | implement → compile → test |
| moderate | complete | implement → compile |
| moderate | partial | implement → compile → test |
| moderate | irreversible | implement → compile → review → test |
| high | complete | implement → compile → test |
| high | partial | implement → compile → review → test |
| high | irreversible | implement → compile → review → test |
| critical | any | implement → compile → review → test |

**Step definitions:**
- `implement` — Write the code per `chosen_approach`. If the prompt contains a header matching the authoritative regex from the mandatory clause (plural or singular, with or without colon), use the Write tool for each declared file at the specified path — do not emit the implementation only as a fenced block in chat. Files must exist on disk, not only in the response.
- `compile` — run the target, verify exit code 0 (runtime check)
- `review` — re-run the Control voice on the actually-written code (not the proposal)
- `test` — run the existing test suite (pytest/unittest autodiscovery)

Output JSON: `{"steps": [...], "rationale": {"chosen": "...", "magnitude": "...", "reversibility": "...", "lookup_key": "..."}}`.

Reject (`n` at prompt) → rejection logged in `.consilium/runs/YYYY-MM-DD_HHMM_pipeline_rejected.json`. Rerun with `--yes` for CI or `--dry-run` for audit without confirmation.

**Skip Step 7 if:** `chosen_approach` is `do_nothing` or `skipped` (the script exits with exit 1 and a clear message). In headless context (`claude -p`), run with `--yes` (non-interactive, no confirmation prompt).

## Step 7 — implementation pipeline details

**Routing gate (single-shot vs pipeline).** `recommend_implement_mode(report)` in `infer_pipeline.py` picks the mode, keyed on **regression risk, not size**: it returns `"pipeline"` when the change warrants a `review` step (the regression-prone quadrants — `moderate×irreversible`, `high×{partial,irreversible}`, `critical×any`), else `"single_shot"`. Greenfield (even large, fully reversible) stays single-shot. **Opt-out:** the routing decision is advisory — the user may override at the Step 7 prompt (press `n`) or by passing `--dry-run` to inspect before committing.

```bash
python -X utf8 scripts/implement_pipeline.py --input .consilium/runs/<file>.json --dry-run   # print dispatch plan
python -X utf8 scripts/implement_pipeline.py --verify-gate --test-cmd "pytest -x" --target <impl_file...>   # pass every Coder-written impl file (fan-out: all of them)
```

Dispatch via `Agent(subagent_type="consilium-implement-subagent", ...)` (see `agents/consilium-implement-subagent.md`). Invariants enforced by the vehicle: **disjoint-path ownership** (Coder writes impl, Test Writer writes `test_*`, Reviewer read-only → collision-free parallel stage), **malformed-JSON hard-fail** (retry once, then abort — never a silent-empty manifest), and the **red→green gate** (a test that passes against a `raise NotImplementedError` stub is rejected).

> **Status: promoted to default for regression-risk changes (2026-05-25).** Combined benchmark R1+R2 (n=6, hidden oracle; see `experiments/pipeline-bench/RESULTS.md`): pipeline **1 win / 5 ties / 0 losses** vs plain single-shot `implement`, at ~1.1× tokens / 3–7× wall-clock. The win was a **refactor with a semantically-isolated secondary branch** (review caught a second-code-path defect the single-shot shipped); on greenfield and algebraically-obvious tasks the base model already nailed the edges (ties). Graduation criterion (≥2/3 wins) not met — promoted on user decision. Audit trail: `runs/2026-05-25_2140_pipeline-step7-default.json` + `experiments/pipeline-bench/`.

## Headless — pattern and pipeline-execution contract

**Pattern adopted:** strict boolean `CLAUDE_HEADLESS=1` (other values → False). Aligned with `CONSILIUM_FORCE_FULL=1` precedent (see `scripts/scope_gate.py`). The external orchestrator (run_task.py, CI script, parent agent) sets the env var before invocation; the skill never modifies the env.

**Note:** `an internal design audit` + internal review H2+H4 (verdict B+X 5/7 + 4/7) validated this contract.

Every `/consilium` invocation MUST terminate by writing a report to `.consilium/runs/` — either a real deliberation report, or a `skipped` / `trivial-direct` report (Step 1.5 / scale_down short-circuit). A run that produces **no** report did not execute the pipeline (it answered directly with the skill merely in context — the gap found in the 2026-05-26 benchmark audit, where `consilium_sequential`/`dialectic` collapsed to bare Sonnet).

**Detection is the orchestrator's responsibility, not the skill's.** A guard written as SKILL.md prose ("assert dispatch happened, else warn") is self-defeating: the skip happens *because* the model didn't execute the steps, so it would skip the guard too — a non-executing process cannot run its own self-check (review 2026-05-26, `an internal design audit`). Therefore the skill does **not** self-enforce headless execution. Instead, any orchestrator that invokes `claude -p` with this skill detects a skipped deliberation by the **absence of a fresh `runs/` report** for the invocation. Reference implementation: `Consilium-Benchmark/run_task.py` `detect_pipeline_execution()` (writes `pipeline_audit.json`; surfaced in `report.html` as a `pipeline: deliberated|skipped` badge). Interactive (non-headless) use is not silent — the operator sees in the transcript whether the pipeline ran.

> Deliberation of record: `.consilium/runs/2026-05-26_2230_live-path-guard.json` (chosen `doc_only_invariant` over a `.claude/settings.json` Stop hook — the hook has a global blast radius and false-positives on correct `trivial-direct` short-circuits, for a benefit confined to third-party headless orchestration).

## Feedback loop — storage details

All deliberation state lives under **`.consilium/`** at the repo root (the single data directory; in this repo it is gitignored). In a consumer project, adding `.consilium/` to `.gitignore` is the recommended default but a preference, not a requirement — keep it tracked if you want the deliberation trail versioned. Paths are centralized in `scripts/utils.py` (`DATA_DIR`/`RUNS_DIR`/`FEEDBACK_PATH`) — scripts import them as defaults, `--runs-dir`/`--feedback` still override.

- **`.consilium/runs/`** — JSON per deliberation in `.consilium/runs/YYYY-MM-DD_HHMM_<label>.json` (schema in `docs/runs-schema.md`). Read by `priors.py` (Step 0), `feedback.py`, `memory.py`. Run-paths are stored relative to `.consilium/` (key `runs/<file>.json`); `--run-path` accepts any spelling (`.consilium/runs/<f>.json`, `runs/<f>.json`, absolute) and `utils.canonical_run_path` normalizes it to that key.
- **`.consilium/FEEDBACK.html`** — one line per use: `date | context | chosen | outcome | note`. Outcome: `OK`, `BAD`, `OVR`, `PEND`. **Drill-down:** when `log_feedback.py` appends, existing rows lose drill-down; bulk re-population was a one-shot migration tool (now removed — see git history).
- **Confirmed outcome.** `mark_outcome.py` adds the `[confirmed]` marker in note. `priors.py` computes its rates from these rows only. Use when production reality contradicts the subjective outcome from Step 6.

## Skill maintenance

Apply only when editing the skill (`scripts/*.py`, `prompts/*.md`, `SKILL.md`), not at every deliberation.

**Eval harness** — when editing `aggregator.py`, `confidence.py`, `validate_report.py`, `strip_context.py`, or `personalities.py`:
```bash
python scripts/run_evals.py
```

**Periodic feedback audit**: `python scripts/feedback.py [--recent 10 --runs]` (stats), `python scripts/audit_feedback.py [--backfill]` (runs without FB row).

**Benchmarking discipline** — any quantitative claim about voice behavior (`fab-rate`, `accuracy`, `catch-rate`) must cite an **independent oracle** (a second expert OR explicit citation from the statement/specs that fixes the ground truth), not the evaluator's quick take. Before publishing benchmark results: for each plausible option (A/B/C/D...), document explicitly *"is there an alternative reading of the problem in which answer X becomes correct?"* — explicit answer per option. A "fabrication" verdict on a piece of reasoning remains blocked until oracle review, separate from the evaluator's intuition. Retroactively applied: any existing fab-rate claim in `experiments/` and `runs/` is reviewed through this grid. Operational checklist: `experiments/README.md`. Origin: the P3 corrigendum (see `experiments/oracle-discipline.md`) — the wrong oracle semantically inverted the "fabrication" conclusion → "real constraint catch".

## Resources

| Script | Role |
|---|---|
| `scripts/priors.py` | Soft priors from FEEDBACK.html + runs/ (Step 0). Surfaces `missing_feedback_runs`, `stale_pendings` (2-day threshold), `bad_rate` over `[confirmed]` rows, and `prompt_drift` (advisory — set when prompts/modes changed since the most-recent prior run's `consilium_ref`). |
| `scripts/version.py` | Repo version provenance: `consilium_version()` (git describe stamp), `consilium_ref()` (resolvable committed sha or `""`), `prompts_changed_since(ref)` (guarded drift count). CLI: `(no flag)` prints the display stamp / `--ref` / `--drift <ref>`. |
| `scripts/scope_gate.py` | Auto-detect skip if scope is small (Step 1.5) |
| `scripts/probe_change.py` | Anchor diff_size to `git diff --numstat` (Step 4) |
| `scripts/aggregator.py` | 5 aggregation schemes + auto-relax on total veto (Step 5); reference: `modes/aggregator_schemes.md` |
| `scripts/confidence.py` | Derives confidence from variance + separation (Step 5b); reference: `modes/confidence.md` |
| `scripts/build_report.py` | Assemble the canonical report from the bundle (Step 6) |
| `scripts/validate_report.py` | Principle #4 gate: success_criterion + verification + chosen_approach |
| `scripts/log_feedback.py` | Auto-append to FEEDBACK.html at the end of Step 6 |
| `scripts/mark_outcome.py` | Retroactive outcome overwrite (`[confirmed]` in note → counted in the rates; `CLOSED_UNVERIFIED` closes without evidence) |
| `scripts/infer_pipeline.py` | Step 7: infer + confirm implementation steps from the report; `--dry-run` / `--yes` |
| `scripts/implement_pipeline.py` | Step 7: plan the Coder→(Test Writer∥Reviewer) dispatch + red→green gate verifier; default for regression-risk changes; `--dry-run` / `--verify-gate` |
| `scripts/validate_implement_output.py` | Step 7: validates the Coder, Test Writer and implement-subagent manifest JSON (`--role coder\|test_writer\|manifest`; exit 0 ok / 1 problems / 2 not JSON) |
| `scripts/render_impl_preview.py` | Opt-in Step 7 companion: report (+ optional `git diff`) → self-contained static HTML review page (spec + rationale + multi-file diff) for pre-commit handoff; never in the dispatch control flow. Interactive sessions: the orchestrator also publishes the generated page as an Artifact by default (shareable link); headless runs produce the file only |
| `agents/consilium-implement-subagent.md` | Vehicle for the implementation pipeline; default for regression-risk changes (Step 7); returns a file manifest + Control verdict |
| `prompts/implement/{coder,test_writer}.md` | Implementation pipeline role templates (Reviewer reuses `prompts/voices/control.md`) |
| `modes/implement_pipeline.md` | Machine-readable config + full spec for the implementation pipeline (roles, routing, invariants, red→green gate, benchmark) |
| `scripts/audit_feedback.py` | List runs without FB row; with `--backfill` adds default PEND |
| `scripts/memory.py` | Uniform read API over the 3 tiers (short/medium/long) |
| `scripts/strip_context.py` | Project previous voice's output to minimum (Steps 3-4 sequential) |
| `scripts/personalities.py` | Trias mode — 3 fixed personalities with weights + lens paths |
| `prompts/voices/skeptic.md` | Focal voice for the `skeptic_on_chosen` flag (composable over any mode) — receives only the chosen, produces a concrete objection or `meta_scope_mismatch` |
| `scripts/run_evals.py` + `evals/scenarios.json` | Regression suite for deterministic scripts |
| `agents/consilium-subagent.md` | Subagent for isolated invocation via `Agent(subagent_type="consilium-subagent", ...)` |
| `scripts/vocabulary_map.py` | User-facing translations (reversibility/magnitude/meta_recommendation/verdict) + `compute_tokens_budget(magnitude, reversibility, meta)` |
