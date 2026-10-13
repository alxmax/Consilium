---
milestone: v1.0
id: CONSILIUM-PERSONALITIES-001
status: confirmed
level: code
layer: bus
owner: alxmax
depends_on: []
risk: 1
satisfies: [ARCH-CONSILIUM-VOICES-001]
---

# personalities

> Canonical registry of the three fixed Trias personalities (Essentialist/Verifier/Sentinel) and their voice weights.

## Description

Every line in this section is binding.

- `personalities.py` is the canonical registry of the three fixed Trias-mode personalities (Essentialist, Verifier, Sentinel), each defined by a named set of voice-weighting coefficients and a path to a lens prompt file.
- `personalities.py` replaces the old random-sampling Ensemble approach (legacy `personalities.py <N>`) with deterministic, named characters, so Trias deliberations are reproducible and auditable.
- Each personality biases the weighted aggregation of Generator, Control, and Conservator scores differently:
  - Essentialist: `generator 0.49 / control 0.30 / conservator 0.21` — first-principles minimalism, generator-heavy.
  - Verifier: `generator 0.30 / control 0.40 / conservator 0.30` — operational/testable clarity, balances around Control.
  - Sentinel: `generator 0.30 / control 0.30 / conservator 0.40` — stress / silent-failure / counterparty, conservator-heavy.
- Each personality dict carries a `name`, the `weights` dict, and a `lens` path; all three weight vectors sum to 1.0 and differ meaningfully across personalities.
- The script is also imported as a library by the Trias orchestration layer via `get_by_name()`.
- `get_by_name()` uses `copy.deepcopy()` to return a deep copy of the personality dict, preventing mutation of the module-level `PERSONALITIES` list at runtime — this guards against nested-dict mutation, not just reference aliasing, so runtime mutations never affect subsequent calls.
- With no `--name` flag, a JSON array of all three personality dicts is emitted to stdout; with `--name`, a JSON object for the single matching personality is emitted.
- Exit code is 0 on success, and 2 when a legacy positional N argument is detected, with a human-readable migration message on stderr naming the three valid personality names.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given no CLI arguments, when `personalities.py` runs, then it emits a JSON array of exactly 3 objects, each containing `name`, `weights` (keys `generator`, `control`, `conservator` summing to 1.0), and `lens` (a path string).
- **CASE-2** — Given `--name essentialist`, when `personalities.py` runs, then it emits a single JSON object matching the Essentialist entry, and the returned dict is a deep copy whose mutations do not affect subsequent calls.
- **CASE-3** — Given a positional integer argument, when `personalities.py` runs, then it exits with code 2 and prints a migration message referencing the three valid personality names.
- **CASE-4** — Given `get_by_name('unknown')`, when it is called, then it raises `KeyError` with a message listing valid names.
- **CASE-5** — Given the three personalities' weights, when checked, then `generator + control + conservator == 1.0` for each (within floating-point tolerance).

## Context (non-binding)

**Notes** — Input: `--name` optional filter (`essentialist | verifier | sentinel`); a legacy positional argument N is rejected (see exit code 2 above).

**Current implementation** — `consilium/scripts/personalities.py`.
