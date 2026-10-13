---
id: CONSILIUM-VOTE-DEGENERACY-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: []
risk: 1
satisfies: [ARCH-CONSILIUM-MODES-001]
---

# Trias vote degeneracy measurement

> Empirically measures whether the Trias "democratic vote" carries signal by computing the 3-0 unanimity rate across Trias runs in the corpus — testing the hypothesis that 3 personality lenses on the same model are correlated and always agree (design audit 2026-05-26).

## WHAT — Contract

- `vote_degeneracy.py` scans `.consilium/runs/*.json` for genuine Trias runs (mode field = `"trias"` or `"trias_split"` exactly) and tallies vote-pattern distribution.
- `vote_degeneracy.py` reports `vote_degenerate: true` if the 3-0 unanimity rate exceeds the threshold (default 0.85) and n ≥ min-n (default 20); `"insufficient"` when n < min-n; `false` otherwise.
- A 2-0 pattern (one personality all-vetoed) is counted as `veto_rate`, not folded into unanimity.
- `vote_degeneracy.py` is read-only: it performs no modification to runs, prompts, or pipeline.
- With `--json`, `vote_degeneracy.py` emits machine-readable output.
- `--runs-dir` overrides the default corpus directory; `--min-n` and `--degenerate-threshold` are configurable.
- The default threshold of 0.85 is calibration-provisional; it is revisited once n ≥ min-n genuine Trias runs exist. The `insufficient` verdict already defers judgment until that corpus exists.

## WHAT — Verify intent (open questions for the human)

- None — contract matches script docstring and design audit 2026-05-26 intent exactly.

## HOW — Acceptance (= tests)

- Given 20+ Trias runs all with 3-0, `vote_degenerate: true` is returned.
- Given 20+ Trias runs with 50% 3-0, `vote_degenerate: false`.
- Given fewer than min-n Trias runs, result is `"insufficient"`.
- Given `--json`, output parses as valid JSON with `vote_degenerate`, `three_zero_rate`, `n` fields.
- Non-Trias runs are excluded even if they reference `vote_pattern` in their body.

## WHERE — Current implementation

- consilium/scripts/vote_degeneracy.py
<!-- implements: CONSILIUM-VOTE-DEGENERACY-001 -->
