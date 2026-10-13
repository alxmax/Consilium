---
milestone: v1.1
id: SYS-CONSILIUM-INTEGRITY-001
status: confirmed
level: system
layer: need
depends_on: []
owner: alxmax
risk: 1
---

# A repository that stays consistent with itself

> The skill's docs, diagrams, manifests and public tree stay in step with the code that defines its behaviour, so a reader of any of them is not misled.

## Description

Every line in this section is binding.

- CI fails when the mode docs or the architecture explainer contradict `SKILL.md` or `consilium/scripts/confidence.py`.
- CI fails when a tracked file names the private repository or a local developer path.
- CI fails when the plugin manifests disagree on the version, or a version bump ships without a CHANGELOG entry.
- The regression scenarios and every unit suite run on each push, and a single local command reproduces what CI checks.

## Verify intent

- None - contract confirmed by the owner on 2026-09-21.

## Cases

- **CASE-1** — Given a mode doc edited to contradict `confidence.py`, when `check_doc_drift.py` runs, then it exits 1 and names the violated invariant.
- **CASE-2** — Given a tracked file containing a local path, when `check_public_leak.py` runs, then it exits non-zero.
- **CASE-3** — Given a clean checkout of `main`, when `driver.py smoke` runs, then it reports every CI gate it mirrors as passing.
