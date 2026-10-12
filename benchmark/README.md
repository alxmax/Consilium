# Benchmark — modes × tasks

Local harness that runs each registered task under each registered mode and
produces an aggregate HTML report. Modes are configured in `run_task.py`;
tasks live under `prompts/` and are graded by `verify.py` against rubrics
that live in a **separate sibling repo** at `../Benchmark-scoring/` — see
[Answer keys](#answer-keys-benchmark-scoring) below.

## Prerequisites

- Windows 11, PowerShell (Git Bash also works for the Python entry points).
- Python 3.11 on PATH.
- `claude` CLI on PATH — run `claude --version` to confirm.
- g++ 14.2 (MSYS2 UCRT64) at `C:\msys64\ucrt64\bin\g++.exe` for the C++ task —
  `run_task.py` augments PATH automatically.
- **`Benchmark-scoring/` sibling repo present** at `..\Benchmark-scoring\`
  (one level above this directory). See [Answer keys](#answer-keys-benchmark-scoring).

## Answer keys (`Benchmark-scoring/`) and how cheating is prevented

The scoring tree (expected answers, rubrics, hidden pytest files, solution
notes) lives in a **separate git repo**, *not* in this project. Layout on disk:

```
<parent>/                    ← any dir holding both repos as siblings
├── Consilium/              ← this repo
│   └── benchmark/          ← the harness (prompts, scripts, verify.py)
└── Benchmark-scoring/      ← separate private repo (answer keys)
    ├── code/01_circuit_breaker/…
    ├── reasoning/01_transport_choice/…
    └── …
```

### Threat model

`run_task.py` spawns `claude -p` with `--permission-mode bypassPermissions`
and `cwd=workspace/<mode>/<task>/`. **`cwd` is NOT a sandbox.** The
subprocess has:

- Filesystem-wide read access via absolute paths
- Bash with `git` on PATH (can run `git log` / `git show` against any repo)
- Glob/Grep that can crawl up and down the directory tree
- Read access to `verify.py`, `README.md`, `CLAUDE.md` (which all reference
  the scoring tree by name)

So a curious or adversarial model can (without intervention):
- Glob `**/expected_answer*` from the repo's parent directory → find sibling
- `git show <hash>:scoring/…/expected_answer.txt` → recover deleted files
  from this repo's history
- Read `verify.py` → learn the path convention, then read the file directly

Why three layers of defense are necessary, in order:

#### Layer 1 — Physical separation (`Benchmark-scoring/` sibling repo)

The scoring tree lives outside `Benchmark/`, in a **separate private git
repo** (a separate private repo, kept outside this tree). It is never committed here
and never referenced by absolute path in any `prompts/*.md`. `.gitignore`
in this repo has `scoring/` as a backstop.

#### Layer 2 — Git history purge

`scoring/` was historically committed to this repo. It was removed from
working tree AND from history via `git filter-repo --path scoring/
--invert-paths` (commit `153089d` and predecessors are rewritten;
old SHAs were force-pushed). A clone today contains no scoring blobs in
`.git/objects/`.

#### Layer 3 — Runtime stash (`stash_scoring_for_run` + `stash_sibling_workspaces` in `run_task.py`)

Even with physical separation, the subprocess can:
- Glob the repo's parent directory (one level above the Consilium repo) → find the
  sibling directory
- Read `verify.py` and learn that `SCORING_DIR = BASE.parent /
  "Benchmark-scoring"`
- Glob `workspace/` upward from cwd → find **other modes' completed
  runs** (`workspace/sonnet_bare/<task>/answer.md`) and copy the answer
  rather than computing it. This is a real cross-mode contamination
  vector when `python scripts/run.py all` runs each mode in sequence on the same task.

So for the duration of every `claude -p` invocation, `run_task.py` opens
two physical stash context managers:

**a. `stash_scoring_for_run()`** — moves `Benchmark-scoring/` to
   `%TEMP%\.bms_scoring_<32 hex>` and back. The temp name contains no
   `scoring` / `Benchmark` substring, so brute-glob over `%TEMP%`
   doesn't match. 64-bit random suffix.

**b. `stash_sibling_workspaces()`** — for the current
   `workspace/<mode>/<category>/<task>/` cwd, moves every sibling
   workspace directory (other modes, other categories, other tasks of
   the same category) to `%TEMP%\.bms_ws_<hex>\` and back. The model
   sees an empty `workspace/<mode>/<category>/` containing only the
   current task — no other runs to copy from. A `manifest.json` inside
   the stash dir enables orphan recovery on crash.

During the run:
- `Benchmark-scoring/` does not exist at any derivable path.
- `workspace/<other-mode>/`, `workspace/<this-mode>/<other-category>/`,
  and same-category alternate tasks all disappear from disk.
- Both temp dir names contain no `scoring` / `Benchmark` / `workspace`
  substring, so brute-glob over `%TEMP%` doesn't find them.

If the harness crashes mid-stash, the next `run_task.py` invocation runs
`_recover_orphan_stashes()` at startup. It restores any `.bms_scoring_*`
directly and replays `.bms_ws_*/manifest.json` to put each moved
directory back in place. **Empirically verified (2026-05-19):** asked to
find `expected_answer.txt` under any path on `C:`, sonnet 4.6 reported
the directory and the file did not exist.

#### Layer 4 — Anti-cheat directive in the prompt template

Every task prompt (built from `prompts/templates/{reasoning,code}.md`)
contains an explicit directive: *"Solve the problem from first principles.
Do NOT search the filesystem, git history, environment variables, or any
other source for answer keys… The runner records every tool call you make
and flags any access to answer-key paths as a cheating event."*
This is a soft norm — the layers above are what actually prevent access.

#### Layer 5 — Post-run behavior audit + auto-invalidation

After every run, `run_task.py` calls `scripts/audit_behavior.py`, which
scans the session JSONL transcript
(`~/.claude/projects/<workspace-slug>/<session-id>.jsonl`) and classifies
the model's behavior:

| Verdict      | Score impact | Meaning |
|--------------|--------------|---------|
| `computed`   | unchanged    | No tool call touched scoring-related paths or keywords. The model worked from first principles. |
| `searched`   | unchanged    | The model probed for scoring files OR for sibling-mode workspaces (any reference to a `KNOWN_MODES` entry under `workspace/` that isn't the current mode counts as cross-mode contamination attempt). Every lookup returned empty/denied — both stashes held. |
| `cheat`      | **proxy_score → 0** | A tool call successfully returned content from an answer-key file (matched against unique markers in real answer files). `proxy_score` in `analyze.py` returns **0** unconditionally; the report cell is rendered with a red `VOID` banner. The underlying `verify` score is still computed and shown for diagnostic purposes but not counted. |
| `-`          | unchanged    | Legacy run with no audit data. |

The verdict is written to `behavior_audit.json` in the workspace, embedded
in `RESULT.md` ("Behavior audit" row), and surfaced as a colored badge in
`report.html`. **You do not need to manually discard `cheat` runs** —
`analyze.py` voids them automatically before computing aggregates.

**Standalone audit of a past run:**

```powershell
python scripts/audit_behavior.py workspace/superpowers/reasoning/02_rule_of_three
# → "Behavior audit: computed (no scoring-related access detected)"

python scripts/audit_behavior.py workspace/<mode>/<task> --json
# → full JSON report with every suspicious tool call and outcome
```

### Known residual risks

- The audit is **heuristic**, not a formal proof. Patterns matched:
  substrings `expected_answer`, `Benchmark-scoring`, `solution_notes`,
  `rubric.md`, `AUDIT_TODO`, plus regex for `git log/show/cat-file` and
  Bash commands containing scoring keywords. A model could shell-read
  the content via an intermediary script that omits these tokens (e.g.
  encode the path in base64 before reading). The verdict is a smoke
  detector, not a tamper-proof seal.

- The audit cannot tell **why** the model accessed a flagged path —
  reading `verify.py` (legitimate skill-loading curiosity) is not flagged
  because `verify.py` does not contain answer-key content markers, but a
  Read on `solution_notes.md` is flagged unconditionally. If a future
  task adds a benign `rubric.md` to the workspace, this will produce
  false positives that need pattern tuning.

- **Future enhancement — honeypot bait:** drop a decoy `answer.md`-shaped
  file with a clearly wrong value (e.g. `ANSWER: Z`) into a discoverable
  path before the run. If the model's actual answer matches the bait,
  it copied rather than computed. Not implemented yet — would require
  per-task bait that is unambiguously wrong.

### First-time setup on a new machine

1. Clone (or copy) the scoring repo as a sibling of this one:
   ```powershell
   cd ..   # the directory that contains the Consilium repo
   git clone https://github.com/<your-org>/Benchmark-scoring.git   # your own private scoring repo
   ```
2. Verify the layout:
   ```powershell
   Test-Path ..\Benchmark-scoring\reasoning\02_rule_of_three\expected_answer.txt
   # → True
   ```
3. Smoke-run a task; the harness will read `meta.yaml` from the sibling repo
   (after physically stashing it for the subprocess and restoring it for
   `verify.py`):
   ```powershell
   python scripts/run.py single --mode sonnet_bare --task reasoning/01_transport_choice
   ```

### Rules

- **Never commit scoring files to this (`Benchmark/`) repo.** `.gitignore`
  has an entry for `scoring/` as a safety net — do not bypass it.
- **Never reference the absolute path to `Benchmark-scoring/` in any
  prompt under `prompts/`.** Prompt content is fed to the model verbatim;
  putting the path there bypasses the stash mechanism.
- When editing `verify.py` or `analyze.py`, the path is
  `BASE.parent / "Benchmark-scoring"` — `BASE` is the `Benchmark/`
  directory.
- **If you see `%TEMP%\.bms_*` directories accumulating**, a previous run
  crashed mid-stash. Two flavours:
  - `.bms_scoring_*` — Benchmark-scoring/ stash. Multiple orphans require
    manual review (keep newest, delete the rest).
  - `.bms_ws_*` — workspace stash. Auto-restored from `manifest.json` on
    next `run_task.py` startup. Safe to leave; they self-clean.

## How to run a test

> Prefer the wrappers in `scripts/` — they manage `rep_N` slot indices and
> support replicates via `--reps N`. **Append mode** is the default: each
> cell auto-detects its highest existing `rep_N` slot and writes the next
> run(s) starting from `rep_(max+1)` without touching existing data. Use
> `--clean` to wipe a cell (default slot + all `rep_*` dirs) before
> running, restarting from `rep_1`. Direct `python run_task.py …` calls
> still work, but you have to manage isolation and slot indices yourself.

The wrapper is `scripts/run.py` (Python). It works on any Windows install
with Python on PATH — no ExecutionPolicy changes needed.

### 1. One mode against one task (smoke test)

```powershell
python scripts/run.py single --mode sonnet_bare --task reasoning/02_rule_of_three
```

Equivalent direct call:

```powershell
python run_task.py --mode sonnet_bare --task reasoning/02_rule_of_three --clean
```

What happens, end-to-end:

1. `workspace/sonnet_bare/reasoning/02_rule_of_three/` is wiped clean.
2. `_recover_orphan_stashes()` checks `%TEMP%\.bms_*` and restores any
   `Benchmark-scoring/` left behind by a crashed previous run.
3. `stash_scoring_for_run()` enters: `..\Benchmark-scoring\` is physically
   moved to `%TEMP%\.bms_<random hex>`. From the subprocess's POV, the
   sibling directory does not exist at any derivable path.
4. `claude -p` is spawned in that folder with the task prompt plus the
   universal per-task, per-invocation `[run_id=...]` cache-buster
   (appended after the prompt for slash-command modes so the slash command
   stays at position 0, prepended otherwise — see `run_task.py`).
5. The model writes its deliverable (`answer.md` for reasoning,
   `solution.py` / `solution.hpp` etc. for code) into that folder.
6. Subprocess exits. `stash_scoring_for_run()` exits its `finally` block
   and moves `Benchmark-scoring/` back to its sibling location.
7. `audit_behavior.py` scans the run's session transcript for scoring
   access, writes `behavior_audit.json`, prints a one-line verdict.
8. `verify.py` reads `meta.yaml` from `..\Benchmark-scoring\<task>\` and
   scores the deliverable. Writes `verify/report.json` and `RESULT.md`.
9. `report.html` is regenerated by `analyze.py` (manually via
   `python scripts/run.py report`) — it surfaces both `verify` score
   and `behavior` audit badges per cell.

### How verification actually works (per task type)

- **`closed_answer`** (`reasoning/01_transport_choice`, `reasoning/02_rule_of_three`):
  `verify.py` greps `answer.md` for the `ANSWER:` line, compares to
  `expected_answer.txt`. For tasks with a `VALUE:` line (e.g.
  `02_rule_of_three`), the numeric value is bucketed against
  `value_exact_min/max` (full marks) and `value_min/max` (partial).

- **`cpp_self_tests`** (`code/01_circuit_breaker`): the model's own
  `solution.hpp` is compiled with `g++ -std=c++17 -O2` together with the
  hidden harness in `Benchmark-scoring/<task>/`. The binary's exit code
  + parsed stdout drive the score.

`verify.py` writes `verify/report.json` next to the deliverable; you can
re-score any historical run without re-spawning the model:

```powershell
python verify.py --mode sonnet_bare --task reasoning/02_rule_of_three
```

### 2. One mode against every task

```powershell
python scripts/run.py mode --mode superpowers
```

### 3. One task across every mode

```powershell
python scripts/run.py task --task reasoning/02_rule_of_three
```

### 4. The whole matrix (5 modes × 3 tasks = 15 runs)

```powershell
python scripts/run.py all
```

Sequential by design — concurrent runs share an Anthropic rate-limit bucket
and skew `api_duration` numbers.

### 5. View the aggregate report

```powershell
python scripts/run.py report
```

Regenerates `report.html` from every `claude_raw.json` under `workspace/`
and opens it in the default browser.

### Common wrapper flags

| Flag                 | Meaning                                                                |
|----------------------|------------------------------------------------------------------------|
| `--reps N`           | Add N replicate runs per cell (default 1). Each lands in its own `rep_*` slot. |
| `--clean`            | Wipe each cell before running. Without it, runs **append** to existing reps. |
| `--extra --budget 5` | Forward extra args verbatim to `run_task.py`.                          |

Use `--extra` for any direct-CLI knob: `--budget`, `--effort`, `--model`,
`--no-verify`. Do **not** pass `--rep` via `--extra` — the wrapper manages
slot indices. Example: `python scripts/run.py single --mode sonnet_bare
--task code/01_circuit_breaker --reps 3 --extra --budget 5 --effort medium`.

Replicate aggregation: `analyze.py` collects all runs found under
`workspace/<mode>/<task>/` (default slot + every `rep_*/`) and renders
`n=K · p L-H · $σ X.XX` in the HTML cell — median proxy + cost stdev across
reps. The Claude Code system prompt (~30K tokens) is cached structurally
across modes; the `CR · CW` meta line per cell surfaces cache_read /
cache_write so you can confirm cross-cell stability.

See [`scripts/README.md`](scripts/README.md) for the full menu and the
isolation guarantees in detail.

## Tasks

| # | Task | Type | Difficulty |
|---|------|------|------------|
| 1  | `code/01_circuit_breaker`         | Code (C++ concurrency)                        | At ceiling (measured) |
| 2  | `reasoning/01_transport_choice`   | Reasoning — multiple-choice                   | Discriminator |
| 3  | `reasoning/02_rule_of_three`      | Reasoning — multiple-choice + VALUE: tier     | At ceiling (measured) |

> The `#` column is just a row index. Task slugs are numbered within their
> own category, so the filenames don't form a single contiguous sequence.
>
> The column reflects the **measured** 2026-06-24 results (n=4/mode), which
> inverted the author's pre-run Easy/Hard calibration: both tasks rated
> "Hard" sit at ceiling for every mode, while the "Easy" trick question
> (`transport_choice`) is the only discriminator — 1/4 (`sonnet_bare`) vs
> 4/4 (consilium modes). Open follow-up: replace the two saturated tasks.
> The label is kept out of the prompt files on purpose so models can't
> calibrate effort against it.

## Modes

| Mode | Model (default) | Effort (default) | What it adds |
|------|-----------------|------------------|--------------|
| `sonnet_bare`            | `claude-sonnet-5-5` | `high` | Plain Sonnet, no skills, no prefix. Baseline. |
| `superpowers`            | `claude-sonnet-5-5` | `high` | Auto-loads the `superpowers:*` skill bundle. |
| `consilium_sequential`   | `claude-sonnet-5-5` | `high` | `/consilium` skill in sequential mode. |
| `consilium_trias`        | `claude-sonnet-5-5` | `high` | `/consilium --mode trias` (three voices). |
| `consilium_dialectic`    | `claude-sonnet-5-5` | `high` | `/consilium --mode dialectic`. |

> The model is pinned per mode in `MODE_MODELS` (currently only `sonnet_bare`);
> all other modes inherit the global `--model` default. Effort is the same
> default for every mode. Override on the CLI with `--model <id>` /
> `--effort low|medium|high|xhigh|max`, or via
> `-ExtraArgs '--model','...'` from the scripts.

## Direct CLI flags

| Flag         | Default              | Description |
|--------------|----------------------|-------------|
| `--clean`    | off                  | Delete `workspace/<mode>/<task>/` before run (the scripts pass this by default). |
| `--model`    | `claude-sonnet-5-5`  | Model id or alias. Some modes pin a model — see `MODE_MODELS` in `run_task.py`. Use `claude-opus-5-5` for the Opus 5.5 batch. |
| `--effort`   | `high`               | `low / medium / high / xhigh / max`. |
| `--budget`   | `5.0`                | `--max-budget-usd` cap (USD). |
| `--no-verify`| off                  | Skip the automated verification step. |

Hard wall-clock cap: 15 minutes per run (subprocess is killed past that), aligned with the task prompt's 15-minute API-duration limit (raised from 10 min so heavy consilium/trias deliberations aren't killed mid-pipeline).

## Adding a new task

1. Create `prompts/<category>/<NN_slug>.md` in **this** repo.
2. In the **sibling** `..\Benchmark-scoring\` repo, add
   `<category>/<NN_slug>/meta.yaml` plus the rubric / test file /
   expected answer referenced inside. Commit it there, not here.
3. Append the task to the `TASKS` list in `scripts/_common.py` (single
   source of truth — picked up automatically by `run_task.py`, `analyze.py`,
   `audit_behavior.py`, and `scripts/run.py`).
4. Add the task to the table above and to `COMMANDS.md`.
5. Smoke-run with `python scripts/run.py single --mode <m> --task <t>`
   for one mode to confirm the verifier wires up end-to-end.

## See also

- [`COMMANDS.md`](COMMANDS.md) — exhaustive command list per mode.
- [`SCORING_RUBRIC.md`](SCORING_RUBRIC.md) — manual scoring guidance.
- [`BENCHMARK_INSTRUCTIONS.md`](BENCHMARK_INSTRUCTIONS.md) — run order and
  rate-limit notes.
- [`scripts/README.md`](scripts/README.md) — convenience runner reference.
