---
milestone: v1.1
id: CONSILIUM-TRIAS-MODEL-SCHEMA-001
status: confirmed
level: code
layer: bus
owner: alxmax
depends_on: [CONSILIUM-PERSONALITIES-001, CONSILIUM-MODE-TRIAS-001]
risk: 1
satisfies: [ARCH-CONSILIUM-MODES-001]
---

# trias-model-assignment

> Trias uniform model assignment: all 3 personalities (essentialist, verifier, sentinel) use sonnet. No per-personality schema workarounds needed.

## WHAT — Contract (normative)
- `consilium/scripts/personalities.py` exposes a `PERSONALITIES` list where every entry carries a `model` field whose value controls which Claude model tier the Trias orchestrator dispatches for that sub-agent.
- Model assignments are uniform: essentialist → `sonnet`, verifier → `sonnet`, sentinel → `sonnet`.
- No personality entry carries `schema_less: True`; all personalities use standard StructuredOutput dispatch.
- The `personalities.py` CLI emits a valid JSON array of exactly 3 objects, each with at minimum a `model` field, for use by the Trias orchestrator at runtime.

## WHAT — Verify intent
- None — all questions resolved.

## HOW — Acceptance (= tests)
- All three personalities emit a `model` field (test_model_fields_present).
- All assignments are sonnet (test_model_assignments, test_all_models_sonnet).
- No personality carries `schema_less` (test_no_schema_less_any_personality).
- CLI emits valid JSON array with `model` field on each entry (test_cli_output_valid_json).
