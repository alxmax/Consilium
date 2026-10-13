---
milestone: v1.1
id: ARCH-CONSILIUM-VOICES-001
status: confirmed
level: architecture
layer: aggregate
depends_on: [CONSILIUM-VOICE-GENERATOR-001, CONSILIUM-VOICE-CONTROL-001, CONSILIUM-VOICE-CONSERVATOR-001, CONSILIUM-VOICE-SKEPTIC-001, CONSILIUM-LENS-ESSENTIALIST-001, CONSILIUM-LENS-VERIFIER-001, CONSILIUM-LENS-SENTINEL-001, CONSILIUM-PERSONALITIES-001]
satisfies: [SYS-CONSILIUM-VERDICT-001]
owner: alxmax
risk: 1
---

# Deliberation voices and personality lenses

> The fixed cast that argues about a change: three core voices, a focal Skeptic, and three personality lenses that bias them.

## Description

Every line in this section is binding.

- Generator proposes the candidate approaches, Conservator scores each candidate's risk, and Control validates each candidate's correctness and goal-fit. [[CONSILIUM-VOICE-GENERATOR-001]] [[CONSILIUM-VOICE-CONSERVATOR-001]] [[CONSILIUM-VOICE-CONTROL-001]]
- The Skeptic challenges only the chosen candidate, after selection, and never proposes a new one. [[CONSILIUM-VOICE-SKEPTIC-001]]
- Each voice reads its prompt from `prompts/voices/<name>.md` and emits JSON in the shape its requirement defines.
- The three Trias personalities (Essentialist, Verifier, Sentinel) are defined once in `consilium/scripts/personalities.py`, and each lens is prepended to the core voices, never substituted for them. [[CONSILIUM-PERSONALITIES-001]] [[CONSILIUM-LENS-ESSENTIALIST-001]] [[CONSILIUM-LENS-VERIFIER-001]] [[CONSILIUM-LENS-SENTINEL-001]]

## Verify intent

- None - contract confirmed by the owner on 2026-09-21.

## Cases

- **CASE-1** — Given any mode, when a deliberation runs, then Generator, Conservator and Control each emit their JSON before aggregation.
- **CASE-2** — Given a chosen candidate, when the Skeptic runs, then its output passes `validate_skeptic.py` and names no new candidate.
- **CASE-3** — Given a Trias run, when the Verifier personality deliberates, then its voices receive the Verifier lens text ahead of their core prompts.
