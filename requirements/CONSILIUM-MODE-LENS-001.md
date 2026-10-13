---
milestone: v1.8
id: CONSILIUM-MODE-LENS-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: [CONSILIUM-LENS-ESSENTIALIST-001, CONSILIUM-LENS-VERIFIER-001, CONSILIUM-MODE-SEQUENTIAL-001, CONSILIUM-MODE-DIALECTIC-001, CONSILIUM-VALIDATE-REPORT-001]
satisfies: [ARCH-CONSILIUM-MODES-001]
---

# opt-in personality-lens ladder (`--lens`)

> WHY: lets a caller graduate the cheaper modes toward Trias's lens structure without paying the cost on every run. Off by default so the default path's cost is unchanged (lens text adds ~18% per-voice prompt tokens); lens value over lens-free deliberation is empirically unproven (Trias 0/6 on a saturated corpus), so default-on is withheld pending a discriminator pilot. Shipped opt-in over two 2026-07-07 internal design-review rounds (verdict MODIFY).

## WHAT — Contract (normative)
- The `--lens <name>` flag is composable over Sequential and Dialectic, and is **OFF by default**.
- A run without `--lens` applies no lens; its cost is unchanged.
- On **Sequential**, `--lens essentialist` prepends `prompts/voices/essentialist_lens.md` over Generator → Conservator → Control.
- On **Dialectic**, `--lens essentialist` puts the Essentialist lens on the decider (the Sequential voices) and **tints the Skeptic with the Verifier lens** via the Verifier lens's Skeptic carve-out — complementary roles, not a vote. No new prompt file is introduced (the "B / tint" mechanism); the two lenses differ (`decider != skeptic`).
- A lensed run records `telemetry.lens_applied` as `{decider: <name>, skeptic?: <name>}`; a default (no-lens) run omits the field.
- `validate_report.py` rejects a report whose `telemetry.lens_applied` is malformed, names a lens that is not a known personality, or (Dialectic) has `decider == skeptic`.
- The mechanism does not change any voice's return schema, the sub-agent dispatch count, or the `cost_multiplier` of either mode.

## WHAT — Verify intent (open questions for the human)
- None — default-on is intentionally out of scope until a discriminator pilot (n≥10–20, non-saturated oracle-validated corpus) shows a win.

## HOW — Acceptance (= tests)
AC-1
  Given  a Dialectic report whose telemetry.lens_applied has decider == skeptic (e.g. both "verifier")
  When   validate_report._validate_telemetry runs
  Then   it returns a problem stating decider and skeptic must differ

AC-2
  Given  prompts/voices/verifier_lens.md
  When   scripts/test_lens_bias.py runs
  Then   it asserts the "skeptic carve-out" keyword is present (the Verifier lens is coherent when tinted onto the Skeptic voice)

AC-3
  Given  a telemetry.lens_applied naming a lens that is not a known personality (e.g. "essentailist")
  When   validate_report._validate_telemetry runs
  Then   it returns a problem naming the valid personality lenses

## WHERE — Current implementation
- modes/sequential.md
- modes/dialectic.md
- prompts/voices/verifier_lens.md
- consilium/scripts/validate_report.py
- scripts/test_lens_bias.py
