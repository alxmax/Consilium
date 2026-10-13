---
milestone: v1.0
id: CONSILIUM-STRIP-CONTEXT-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: [CONSILIUM-UTILS-001]
risk: 1
satisfies: [ARCH-CONSILIUM-REPORT-001]
---

# strip_context

> Projects each voice's output down to the minimum fields the next voice needs (anti-contamination).

## Description

Every line in this section is binding.

- `strip_context.py` reduces cross-voice context contamination in the sequential deliberation pipeline by projecting each voice's output down to the minimum fields the next voice needs.
- Input is stdin by default, or `--input <file>`; it expects JSON for `--for control` / `--for conservator` modes, and plain text for `--truncate-text` mode.
- `--for control` expects Generator output JSON with a `candidates` array. It strips candidates to `id`, `summary`, and `sketch` only, removing rationale fields that would rhetorically bias Control's technical validation.
- `--for conservator` expects combined JSON with `candidates` (Generator) and `verdicts` (Control) arrays. It intersects valid Control verdicts with Generator candidates, dropping candidates with no valid Control verdict.
- `--for conservator` output contains only `id`, `summary`, and `sketch`; Control's `issues` and `notes` fields are excluded so they cannot bias Conservator's risk scoring.
- `--truncate-text <MAX_TOKENS>` caps raw text to a token budget (an integer), approximated as 4 chars/token.
- `--truncate-text` is used by Trias orchestration to cap raw conversation context sent to each personality sub-agent.
- `--truncate-text` truncates text to `MAX_TOKENS x 4` characters and appends the truncation marker `_TRUNCATION_MARKER` when the text is cut; text under budget is returned unchanged.
- Output for `--for control` / `--for conservator` is a JSON object to stdout: the stripped candidate or verdict list.
- Output for `--truncate-text` is plain text to stdout: the possibly truncated text with the optional marker appended.
- Exit code is 0 on success; non-zero on argument or JSON parse errors.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given a Generator output JSON, when `--for control` runs, then the `rationale` field is stripped from all candidates and only `id`, `summary`, and `sketch` remain.
- **CASE-2** — Given a candidate whose matching Control verdict has `valid=false` or has no matching Control verdict, when `--for conservator` runs, then that candidate is dropped (excluded, not an error).
- **CASE-3** — Given a Control verdict with `issues` and `notes` fields, when `--for conservator` runs, then those fields are excluded from the output.
- **CASE-4** — Given text shorter than 60000 characters, when `--truncate-text 15000` runs, then the text is returned unchanged with no marker.
- **CASE-5** — Given text exceeding 60000 characters, when `--truncate-text 15000` runs, then the text is truncated at 60000 characters and the marker `"\n\n[... context truncated to ~{tokens} tokens for Trias sub-agent ...]"` (`_TRUNCATION_MARKER`, defined in `strip_context.py`, not shared with other scripts) is appended.

## Context (non-binding)

**Notes** — None beyond the Description above.

**Current implementation** — `consilium/scripts/strip_context.py`
