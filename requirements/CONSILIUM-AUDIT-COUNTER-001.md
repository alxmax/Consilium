---
id: CONSILIUM-AUDIT-COUNTER-001
status: deprecated
level: code
layer: feature
owner: auto
depends_on: [CONSILIUM-UTILS-001]
risk: 1
---

# Silent parallel audit counter

> Tracks sequential deliberation runs and determines when a silent parallel cross-check is due, implementing the adaptive-cadence claim from SKILL.md §"Silent parallel audit".

## WHAT — Contract

- Shall increment a persistent counter (`--increment`) after each sequential deliberation step 6 completes.
- Shall report whether the current run is due for a silent parallel cross-check (`--check`), returning `{"should_audit": bool, "sequential_count": int, "frequency": int, ...}`.
- Shall accept a divergence result (`--record-divergence 0|1`) and update the rolling 5-audit window; adapt frequency: if ≥2 divergences in the window and frequency=20, set frequency=5; if 0 divergences in a full window of 5 audits and frequency=5, restore to frequency=20.
- `--check` shall return `should_audit: false` in headless contexts (`CLAUDE_HEADLESS=1`) even if the run is numerically due.
- Prior-deliberation passthrough runs shall NOT increment the counter (they bypass both pipelines).
- State shall be stored in `.consilium/audit_state.json` (gitignored).
- The rolling window of 5 audits is intentionally fixed (not configurable) to maintain calibration stability across the follow-up audit cycle (SKILL.md §"Silent parallel audit").

## WHAT — Verify intent (open questions for the human)

- None — contract matches docstring and SKILL.md §"Silent parallel audit" exactly.

## HOW — Acceptance (= tests)

- Given a fresh state, after 20 `--increment` calls, `--check` returns `should_audit: true`.
- Given `should_audit: true` and `--record-divergence 1` twice (plus 3 zeros), frequency stays at 20 (needs ≥2 in window); given two more divergences, frequency flips to 5.
- Given `CLAUDE_HEADLESS=1`, `--check` returns `should_audit: false` regardless of count.
- Given `--status`, output contains `sequential_count`, `frequency`, `audit_count`, and `recent_divergences`.

## WHERE — Current implementation

- scripts/audit_counter.py
<!-- implements: CONSILIUM-AUDIT-COUNTER-001 -->
