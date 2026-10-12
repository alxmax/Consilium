# BENCHMARK COMMANDS

All runs use `claude -p` headless mode (Sonnet 5.5 by default, effort=high,
budget cap $5/task).

> **Easy mode:** the wrapper at `scripts/run.py` covers the common batches
> (`python scripts/run.py all`, `mode`, `task`, `report`). It runs in
> **append mode** by default — new runs land in the next free `rep_N` slot
> without touching existing data. Pass `--clean` to wipe a cell before
> running. Pass `--reps N` to add N replicates per cell. See
> `scripts/README.md` for the full menu.

---

## SETUP (once)

```powershell
cd benchmark   # from the Consilium repo root
# git init && git add . && git commit -m "init"   # if not initialised
```

Make sure the `claude` CLI is on PATH:

```powershell
claude --version
```

---

## TASK ORDER

3 tasks:
1.  `code/01_circuit_breaker`            — hard code (C++)
2.  `reasoning/01_transport_choice`      — reasoning (easy)
3.  `reasoning/02_rule_of_three`         — reasoning (hard, rule-of-three)

---

## DEFAULT RUNNER FLAGS

`run_task.py` (direct CLI):
```
--clean             → wipe this task's workspace before running
--rep N             → write to workspace/<mode>/<task>/rep_<N>/ (single slot)
--model    claude-sonnet-5-5   (default; sonnet_bare pins claude-sonnet-5-5;
                                pass claude-opus-5-5 for the Opus 5.5 batch)
--effort   high                (default; choices: low/medium/high/xhigh/max)
--budget   5.0                 (USD cap; halts with `error_max_budget` if hit)
--no-verify                    (skip automatic verify step after the run)
```

`scripts/run.py` (wrapper) — manages rep slots automatically:
```
--reps N            → add N replicate runs per cell (default 1)
--clean             → wipe each cell before running (else: APPEND to existing reps)
--extra <args>      → forward to run_task.py (e.g. --extra --budget 5 --effort medium)
```

Default behavior of the wrapper: each cell auto-detects highest existing
`rep_N` and writes to `rep_(N+1)`, `rep_(N+2)`, …, `rep_(N+reps)` — no data
is overwritten. Use `--clean` to wipe and start from `rep_1`.

Hard wall-clock cap per run: **15 minutes** (subprocess killed past that), aligned with the task prompt's 15-minute API-duration limit (raised from 10 min so heavy consilium/trias deliberations aren't killed mid-pipeline).

After each run, the runner auto-invokes `verify.py` if the task has a
`scoring/<task>/` folder (containing `meta.yaml` + tests/rubric/expected
answer), and writes the report into both `workspace/.../verify/report.json`
and the top of `RESULT.md`.

The `scoring/` tree lives outside `prompts/` and is **never visible to the
benchmarked model**: each run's `claude -p` subprocess is sandboxed to its own
`workspace/<mode>/<task>/` (subprocess cwd), so test files, expected answers
and rubrics cannot leak into the model's context.

Re-score retroactively without re-running the model:

```powershell
python verify.py --mode sonnet_bare --task code/01_circuit_breaker
```


---

## CONSILIUM SEQUENTIAL

```powershell
cd benchmark   # from the Consilium repo root
python run_task.py --mode consilium_sequential --task code/01_circuit_breaker
python run_task.py --mode consilium_sequential --task reasoning/01_transport_choice
python run_task.py --mode consilium_sequential --task reasoning/02_rule_of_three
```

---

## CONSILIUM TRIAS

```powershell
python run_task.py --mode consilium_trias --task code/01_circuit_breaker
python run_task.py --mode consilium_trias --task reasoning/01_transport_choice
python run_task.py --mode consilium_trias --task reasoning/02_rule_of_three
```

---

## CONSILIUM DIALECTIC

```powershell
python run_task.py --mode consilium_dialectic --task code/01_circuit_breaker
python run_task.py --mode consilium_dialectic --task reasoning/01_transport_choice
python run_task.py --mode consilium_dialectic --task reasoning/02_rule_of_three
```

---

## SUPERPOWERS

Runs in `--auto` like every other mode. The `superpowers:*` skills auto-load
via the SessionStart hook in `claude -p`, so no browser / paste is needed.
The runner prepends a structured prefix that:
- includes a per-task cache-buster token (prevents Anthropic prompt-cache from
  dropping task content on consecutive runs)
- blocks interactive skills: `superpowers:brainstorming`, `superpowers:writing-plans`,
  `superpowers:receiving-code-review`
- encourages non-interactive skills: TDD, consilium, verification-before-completion,
  systematic-debugging

```powershell
python run_task.py --mode superpowers --task code/01_circuit_breaker
python run_task.py --mode superpowers --task reasoning/01_transport_choice
python run_task.py --mode superpowers --task reasoning/02_rule_of_three
```

---

## RE-RUN A SINGLE TASK FROM SCRATCH

```powershell
# Single fresh run, one cell:
python scripts/run.py single --mode sonnet_bare --task code/01_circuit_breaker --clean

# Multiple fresh replicates, one cell:
python scripts/run.py single --mode sonnet_bare --task code/01_circuit_breaker --reps 3 --clean

# All modes, one task, fresh batch (use after editing the task prompt):
python scripts/run.py task --task reasoning/01_transport_choice --reps 3 --clean

# Wipe just one task without running anything:
python scripts/run.py clean --task reasoning/01_transport_choice
```

`--clean` wipes `workspace/<mode>/<task>/` (default slot + all `rep_*` dirs)
before invoking claude. Without `--clean`, the wrapper appends new runs to
the next free `rep_N` slot.

---

## TUNING

- Bigger budget for a heavier task:
  ```powershell
  python run_task.py --mode consilium_dialectic --task code/01_circuit_breaker --budget 8
  ```
- Lower effort to compare quality vs cost:
  ```powershell
  python run_task.py --mode sonnet_bare --task code/01_circuit_breaker --effort medium
  ```
- Different model (e.g. Haiku for smoke test):
  ```powershell
  python run_task.py --mode sonnet_bare --task code/01_circuit_breaker --model haiku --budget 1
  ```

---

## EXHAUSTION SIGNALS

If a run halts, RESULT.md is still written and stamped with the cause. Look for:

| subtype                | meaning                                 |
|------------------------|-----------------------------------------|
| `error_max_budget_usd` | `--max-budget-usd` cap hit              |
| `error_max_turns`      | model used too many tool turns          |
| `error_max_duration`   | wall time exceeded                      |
| `error_during_execution` | something else crashed (see stderr)   |

`claude_raw.json` in each workspace contains the full raw response for postmortem.
(Note: `workspace/` is gitignored — runs no longer auto-commit. Inspect locally.)

---

## AFTER ALL RUNS

Results live under `workspace/` (gitignored). Open each `RESULT.md` to fill in
scoring per `SCORING_RUBRIC.md`. Generate the cross-mode HTML report with:

```powershell
python analyze.py
```

---

## TOTAL

5 modes × 3 tasks = 15 runs. Budget cap @ $5/task → maximum spend ~$75.
Reasoning-only tasks typically cost well under $1 each.

---

## AFTER CONSILIUM RUNS

Each `consilium_*` run creates a PEND entry in `.consilium/FEEDBACK.html`.
`run_task.py` converts these automatically to `PEND_HEADLESS` after each run
(blind benchmark — entries are excluded from pend_pressure). No manual step needed.
In practice most runs land below $1; consilium modes are the heaviest.
