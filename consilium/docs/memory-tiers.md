# Memory tiers

> Moved out of `SKILL.md` on 2026-06-10 to keep the runtime contract lean. Reference
> material — the contract keeps only the one-line summary and the `memory.py` CLI.

Consilium has 3 memory layers with different lifecycles. `scripts/memory.py` provides
a uniform read API over all three.

| Tier | Location | Lifetime | Content | Read by |
|---|---|---|---|---|
| **Short** | conversation window | session | bundle under construction (Steps 1–5b), clarity gate, current success_criterion | agent only (not persisted) |
| **Medium** | `.consilium/runs/*.json` | indefinite (gitignored) | one file per deliberation; episodic | `priors.py`, `feedback.py`, `memory.py`, `audit_feedback.py` |
| **Long** | `.consilium/FEEDBACK.html` + signals from `priors.py` | indefinite | one row per use; aggregated over time | `priors.py`, `feedback.py`, `memory.py`, `mark_outcome.py` |

Uniform CLI:

```bash
python scripts/memory.py --tier medium --n 5             # last 5 runs
python scripts/memory.py --tier long --query auth        # substring filter
python scripts/memory.py --tier all --query feedback     # union across 3 tiers
```

Note: `.consilium/` is **per-repo** — each project where the skill runs accumulates its
own runs and journal. There is no cross-repo aggregation layer.
