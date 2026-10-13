---
milestone: v1.1
id: CONSILIUM-VALIDATE-SKEPTIC-001
status: confirmed
level: code
layer: bus
owner: alxmax
depends_on: [CONSILIUM-VOICE-SKEPTIC-001, CONSILIUM-UTILS-001]
risk: 2
satisfies: [ARCH-CONSILIUM-REPORT-001]
distinct_from: [CONSILIUM-MODE-DIALECTIC-001, CONSILIUM-MODE-SKEPTIC-ON-CHOSEN-001]
---

# validate_skeptic

> Describes observed behavior, verified against consilium/scripts/validate_skeptic.py source.

## Description

Every line in this section is binding.

- `validate_skeptic.py` reads a Skeptic voice output JSON from stdin, produced by the Skeptic voice per `prompts/voices/skeptic.md`.
- `validate_skeptic.py` is a structural validation gate for Skeptic output, enforcing the machine-checkable subset of the gate described in `prompts/voices/skeptic.md` and `modes/skeptic_on_chosen.md` — shape and evidence rules only, not semantic correctness.
- A verdict that fails this gate is discarded, and the original `chosen` candidate ships unchallenged.
- `can_object` is validated as a bool; the gate exits 1 if it is missing or non-bool.
- `can_object=false` requires `objection` to be null or absent; a non-null `objection` is an error.
- `can_object=true` requires `objection` to be an object with `concrete_concerns` (a list of strings) and `quoted_scenario` (a string or null).
- The evidence gate rejects the verdict unless it has at least 2 non-empty `concrete_concerns`, or a non-empty `quoted_scenario`.
- `failure_mode` is validated against the allowed set `{correctness, goal_fit, verification_inadequate, meta_scope_mismatch}`.
- `addressable` is validated against the allowed set `{in_place, requires_redesign, unaddressable}`.
- `failure_mode=goal_fit` requires at least one `concrete_concern` to reference the substring `"success_criterion"`.
- Exit 0 means the verdict is well-formed and the orchestrator may apply it; exit 1 means the verdict is invalid, with each problem printed to stderr and the orchestrator shipping the original `chosen`; exit 2 means the JSON input is malformed.

## Verify intent

- None — all questions resolved.

## Cases

- **CASE-1** — Given `can_object=false` with a null `objection`, when `validate_skeptic.py` runs, then it exits 0.
- **CASE-2** — Given `can_object=true` with 2 or more `concrete_concerns`, when `validate_skeptic.py` runs, then it exits 0.
- **CASE-3** — Given `can_object=true` with only a non-empty `quoted_scenario`, when `validate_skeptic.py` runs, then it exits 0.
- **CASE-4** — Given `can_object=true` with 0 `concrete_concerns` and a null `quoted_scenario`, when `validate_skeptic.py` runs, then it exits 1 (evidence gate).
- **CASE-5** — Given `failure_mode=goal_fit` without `"success_criterion"` referenced in any concern, when `validate_skeptic.py` runs, then it exits 1.
- **CASE-6** — Given an unknown `failure_mode` value, when `validate_skeptic.py` runs, then it exits 1.
- **CASE-7** — Given malformed JSON input, when `validate_skeptic.py` runs, then it exits 2.

## Context (non-binding)

**Current implementation** — `consilium/scripts/validate_skeptic.py`.

**Not a duplicate** — CONSILIUM-MODE-DIALECTIC-001 and
CONSILIUM-MODE-SKEPTIC-ON-CHOSEN-001 are the modes that dispatch a Skeptic;
this requirement is the script that validates the verdict they get back.
They share the Skeptic's vocabulary, not a capability.
