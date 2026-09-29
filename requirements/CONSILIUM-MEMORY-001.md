---
milestone: v1.0
id: CONSILIUM-MEMORY-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: [CONSILIUM-FEEDBACK-001, CONSILIUM-UTILS-001]
risk: 1
satisfies: [ARCH-CONSILIUM-LEARNING-001]
---

# memory

> Unified read API over Consilium's three memory tiers (short / medium / long).

## Description

Every line in this section is binding.

- `memory.py` provides a unified read API over Consilium's three memory tiers, through a single CLI and importable surface: short (current session, stub only), medium (per-run episodic JSON files in `runs/`), and long (aggregate FEEDBACK.html parsed via `feedback.py`).
- `memory.py` exists so an orchestrating agent can ask "what does Consilium remember about X" without knowing which tier holds the relevant data.
- The `--query` flag applies a substring filter uniformly across medium and long tiers.
- The short tier is represented by a descriptive stub, because its content (the deliberation bundle being assembled) is only accessible inside the active agent context window.
- Confirmed-outcome rows (those carrying `[confirmed]` in their note, written by `mark_outcome.py`) are flagged in long-tier output so callers can apply higher trust weights to them.
- JSON is emitted to stdout: for a single tier, a dict with `tier`, `entries`, and `total` keys; for `--tier all`, a dict with `short`, `medium`, and `long` sub-objects.
- Exit code is 0 always (no error paths beyond missing files, which return empty entry lists).
- The short tier stub is permanently fixed: `read_short()` is a hardcoded function returning `{"tier": "short", "note": "...", "entries": []}` with no file-based population path. There is no session-file mechanism and no design provision for one.
- Case-insensitivity is guaranteed for both tiers via `_matches(text, q) -> q.lower() in text.lower()`.
- The long-tier query filter searches `context`, `chosen`, and `note`.
- `--n` applies independently per tier: `read_all` passes `n` to both `read_medium` and `read_long` separately, so `--tier all --n N` can return up to `2N` entries (short always returns 0 entries).
- There is no global cap on entries returned.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given `--tier medium`, when `memory.py` runs, then it returns a JSON object whose `entries` array contains at most `--n` items, each with `run`, `date`, `success_criterion`, `chosen`, and `confidence` fields drawn from `runs/*.json` files.
- **CASE-2** — Given `--tier long --query <term>`, when `memory.py` runs, then it returns only rows whose `context`, `chosen`, or `note` contains the query term (case-insensitive), each entry including a `confirmed` boolean reflecting presence of `[confirmed]` in the note.
- **CASE-3** — Given `--tier short`, when `memory.py` runs, then it returns a stub dict with `entries: []` and a descriptive `note` explaining session-local scope.
- **CASE-4** — Given `--tier all`, when `memory.py` runs, then it returns a dict with exactly three keys (`short`, `medium`, `long`), each containing valid tier output.
- **CASE-5** — Given `--feedback-file` and `--runs-dir` are passed, when `memory.py` runs, then it overrides the default `.consilium/` paths so the script can operate on arbitrary copies of the data.

## Context (non-binding)

**Notes** — Input: `--tier` one of `short | medium | long | all` (default `all`); `--n` maximum entries per tier (default 10); `--query` optional substring filter; `--feedback-file` / `--runs-dir` override paths. Reads `.consilium/runs/*.json` for the medium tier and `.consilium/FEEDBACK.html` for the long tier. Contract derived from code, 2026-06-04.

**Current implementation** — `scripts/memory.py`.
