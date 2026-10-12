# benchmark-modes

Local benchmark harness. Each task is solved by a single subprocess and graded by an automated verifier. Refer to `COMMANDS.md` for the full task list, defaults (Sonnet 5.5, effort=high, budget $5, 15-minute wall-clock cap — aligned with the task prompt's 15-minute API-duration limit) and how to run each one.

## How to run

Direct CLI:

```powershell
python run_task.py --mode <mode> --task <task>
```

Convenience wrapper at `scripts/run.py` (recommended — runs in **append mode** by default: new runs land in the next free `rep_N` slot without touching existing data. Pass `--clean` to wipe a cell, `--reps N` to add N replicates):

```powershell
python scripts/run.py all                                          # all modes x all tasks, 1 rep appended
python scripts/run.py all --reps 3 --clean                         # fresh 3-rep batch over the matrix
python scripts/run.py task --task reasoning/02_rule_of_three --reps 3 --clean
python scripts/run.py clean --task reasoning/01_transport_choice           # wipe one task across all modes
python scripts/run.py report                                       # regenerate report.html + open
```

See `scripts/README.md` for the full menu and isolation guarantees.

After all runs:

```powershell
python analyze.py
```

## Environment

- Windows 11, PowerShell
- Python 3.11 on PATH
- g++ 14.2 (MSYS2 UCRT64) on PATH — `run_task.py` augments PATH automatically
- `claude` CLI on PATH

## Answer-key isolation (maintainer notes)

- Answer keys live in **`../Benchmark-scoring/`**, a separate sibling git repo *outside* this project root. The benchmark subprocess runs with `cwd=workspace/<mode>/<task>/` and `--permission-mode bypassPermissions`, so file access is unrestricted by absolute path; the only real isolation is physical (Benchmark-scoring is outside any Glob path the model knows). Keep it that way: never copy files from `../Benchmark-scoring/` into this repo, never reference its absolute path in prompts, and never re-commit `scoring/` here.
