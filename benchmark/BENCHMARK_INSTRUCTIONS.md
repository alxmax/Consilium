# BENCHMARK INSTRUCTIONS

Read this file first. Find your mode below and follow ONLY that section.

## Tasks in this benchmark
| # | Task | Type |
|---|------|------|
| 1 | Circuit Breaker C++17 — `code/01_circuit_breaker` | Hard Code |
| 2 | Transport Choice — `reasoning/01_transport_choice` | Reasoning (Easy) |
| 3 | Rule of Three — `reasoning/02_rule_of_three` | Reasoning (Hard) |

## Environment (same for every mode — fair across the board)
- OS: Windows 11, PowerShell + Git Bash
- Python: 3.11 on PATH
- C++ compiler: `g++` (MSYS2 UCRT64, GCC 14.2.0) at `C:\msys64\ucrt64\bin\g++.exe` — `run_task.py` puts this on PATH before invoking `claude -p`, so `g++ -std=c++17 ...` works directly.
- Default model + effort: Sonnet 5.5 + `--effort high`. Budget cap: `$5/task`, uniform across modes. Override with `--budget`. Timeout: 15 min wall-clock per run.
- All runs go through `python run_task.py` (headless `claude -p`, including `superpowers`).

---

## CONSILIUM SEQUENTIAL
Invoke with `/consilium` — Sequential mode (Generator → Conservator → Control)
Workspace: `workspace/consilium_sequential/{category}/{task}/`

1. Create `PROCESS.md` — first line: `MODE: Consilium Sequential | START: [time]`
2. Work exclusively in your workspace folder
3. Log Conservator / Generator / Control phases in PROCESS.md
4. Write all deliverables in your workspace
5. Fill RESULT.md when done — run_task.py does this automatically

---

## CONSILIUM TRIAS
Invoke with `/consilium --mode trias`
Workspace: `workspace/consilium_trias/{category}/{task}/`

Same steps as Sequential. Three personalities (Essentialist/Verifier/Sentinel) each run
all three voices independently; final choice is democratic vote across the three.
Log each personality's outcome in PROCESS.md.

---

## CONSILIUM DIALECTIC
Invoke with `/consilium --mode dialectic`
Workspace: `workspace/consilium_dialectic/{category}/{task}/`

Same steps. Log Thesis / Antithesis / Synthesis in PROCESS.md.

---

## SUPERPOWERS
Run via `run_task.py --auto` (default — same as the other modes):
```
python run_task.py --mode superpowers --task code/01_circuit_breaker
```
Workspace: `workspace/superpowers/{category}/{task}/`

`run_task.py` injects a non-interactive benchmark preamble that activates
skills but blocks the ones that need user input (`brainstorming`,
`writing-plans`, `receiving-code-review`). A per-run cache-buster token
(task name + UTC timestamp) is prepended so Anthropic prompt-cache
doesn't drop the task content on consecutive invocations.

---

## SONNET BARE
No skill or plugin. Plain Sonnet 5.5 baseline. Run via Claude Code:
```
python run_task.py --mode sonnet_bare --task code/01_circuit_breaker
```
Script handles everything automatically.

---

## ISOLATION RULES
- Never read another mode's workspace folder
- Work as if you are the only one solving this problem
- PROCESS.md is your private log — write honestly
- If time limit approaches, deliver partial working code rather than nothing

---

## RUN ORDER

**Always run modes sequentially, never in parallel.**

Reason: Anthropic rate limits apply per account. Simultaneous runs cause API throttling that inflates `api_duration` for whichever run gets queued — making a slow model look slower than it actually is and a fast model look penalized. Since `api_duration` is a primary benchmark metric, any cross-run interference corrupts the comparison.

Recommended order per task:
1. `sonnet_bare` (baseline first, no skill overhead)
2. `consilium_sequential`
3. `consilium_trias`
4. `consilium_dialectic`
5. `superpowers`

Wait for each run to finish and write RESULT.md before starting the next.
