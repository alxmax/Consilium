---
milestone: v1.0
id: CONSILIUM-VOCABULARY-MAP-001
status: confirmed
level: code
layer: bus
owner: alxmax
depends_on: []
risk: 0
satisfies: [ARCH-CONSILIUM-REPORT-001]
---

# vocabulary_map

> Single source of truth for field-value translations and the per-voice token budget table.

## Description

Every line in this section is binding.

- `scripts/vocabulary_map.py` is the single source of truth for all user-facing natural-language translations of structured deliberation field values, and for the per-voice token budget table.
- `VOCABULARY_MAP` maps categories (`reversibility`, `magnitude`, `meta_recommendation`, `verdict`) to their human-readable labels, used by the renderer and aggregator to produce consistent output strings.
- `translate` falls back silently: an unknown category or value returns `str(value)`, with no logging; callers cannot assume a human-readable label is always returned.
- All `VOCABULARY_MAP` labels are hardcoded Romanian strings, except `meta_recommendation` values, which are English; no i18n hook exists or is planned.
- `compute_tokens_budget` derives a per-voice token allocation from the Conservator's Q1 (`magnitude`) and Q2 (`reversibility`) outputs, scaling down to 300 for trivial questions.
- `compute_tokens_budget` applies `meta_recommendation` modifiers: `scale_down` sets the budget to 300, `scale_up` multiplies it by 1.5 and caps it at 4000.
- With `meta='scale_up'`, the base value is `TOKENS_BUDGET.get((magnitude, reversibility), 800)`; the 4000 cap binds only for `("critical", "irreversible")` (base 4000 → 4000 after cap); every other pair produces an uncapped result (for example, base 2000 → 3000, base 800 → 1200).
- `vocabulary_map.py` is bus-layer because it carries no pipeline logic: it is a pure lookup table consumed by feature scripts.
- The CLI takes a positional category (e.g. `reversibility`, `magnitude`, `verdict`) and optional value (e.g. `complete`, `critical`), and prints the translated human-readable string to stdout with exit code 0 always.
- `compute_tokens_budget` returns a dict with `generator` and `control` keys.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given `translate('reversibility', 'complete')`, when it runs, then it returns the Romanian string `ușor de anulat`.
- **CASE-2** — Given `translate('verdict', 'GO')`, when it runs, then it returns `aprobat de majoritate`.
- **CASE-3** — Given `compute_tokens_budget('critical', 'irreversible')`, when it runs, then it returns `{'generator': 4000, 'control': 4000}`.
- **CASE-4** — Given `compute_tokens_budget` with `meta='scale_down'`, when it runs, then it always returns `{'generator': 300, 'control': 300}` regardless of magnitude or reversibility.
- **CASE-5** — Given `translate` for an unknown category or value, when it runs, then it returns `str(value)` without raising.

## Context (non-binding)

**Current implementation** — `scripts/vocabulary_map.py`.
