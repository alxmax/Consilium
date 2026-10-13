---
milestone: v1.2
id: CONSILIUM-RENDER-IMPL-PREVIEW-001
status: confirmed
level: code
layer: bus
owner: alxmax
depends_on: [CONSILIUM-UTILS-001]
risk: 1
satisfies: [ARCH-CONSILIUM-IMPLEMENT-001]
---

# render_impl_preview

> Opt-in Step 7 companion: deliberation report (+ optional unified diff) -> one self-contained static HTML review page for pre-commit handoff.

## Description

Every line in this section is binding.

- `render_impl_preview.py` renders a completed deliberation report together with an optional multi-file unified diff into a single self-contained HTML page.
- Rendered report fields: success criterion, chosen approach with voice scores, alternatives with why_not, verification command, confidence, and mode.
- `render_impl_preview.py` exists for handoff review outside the live CLI session: unlike session-bound Artifact URLs or ephemeral Plan Mode, the page is a plain file on disk that survives the session and can be attached to the run report it renders.
- The script is never part of the Step 7 dispatch control flow; invocation is always explicit. Deliberation `runs/2026-07-03_1443_html-preview-impl-step.json` decided this, rejecting a prose-enforced pipeline checkpoint as the self-enforced-guard anti-pattern.
- The script never dispatches, blocks, or gates any Step 7 stage; it only reads its inputs and writes one HTML file.
- `--input` (required) is a path to a `runs/<file>.json` deliberation report, read with `utf-8-sig` so BOM-stamped files parse.
- `--diff-file` (optional) is unified diff text to render; `-` reads stdin, e.g. piped from `git diff`. When omitted, the page is spec-only.
- `--output` (optional) sets the output HTML path; the default is `.consilium/preview/<input-stem>.html`.
- `--title` (optional) overrides the page title.
- `render_preview_html(report, diff_text, title)` and `split_diff_sections(diff_text)` are pure functions exposed as a programmatic surface with no I/O.
- Diff text is split into per-file sections on `diff --git` headers; headerless input falls back to a single `(diff)` section.
- Every line of report and diff content passes through `html.escape` before it reaches the page; hostile input (`</script>`, inline event handlers) never appears unescaped in the output.
- The page follows the viewer's light/dark preference (`prefers-color-scheme`) and includes an inline theme-toggle button (`id="theme-toggle"`) that overrides it, persisting the choice in `localStorage`.
- The output is a self-contained page: no `<link>`, `<script src>`, or `<img src>` references to external URLs.
- The HTML file is written atomically via `utils.atomic_write_text` to `--output` or the default preview path.
- Each `diff --git` section of the supplied diff renders as its own titled block; with no diff supplied, a spec-only placeholder renders instead and the script still exits 0.
- On success, stdout prints `preview: <path>`.
- Exit code is 0 on success; 1 on unreadable input or a missing required report field (one of: `success_criterion`, `chosen_approach`, `verification`); 2 on malformed JSON.

## Verify intent

- None - the default output directory `.consilium/preview/` inherits the gitignore on `.consilium/`, so preview pages cannot enter the tree; no separate ignore rule is asserted by tests.
- None - `--diff-file -` consumes stdin exactly once; combining it with a stdin-based report is unsupported by construction (the report always comes from `--input`).

## Cases

- **CASE-1** — Given a report plus a two-file unified diff, when the page renders, then it contains the success criterion, the chosen id, and one section per `diff --git` header (`scripts/test_render_impl_preview.py`).
- **CASE-2** — Given a diff containing `</script><script>alert(1)</script>` and `<img onerror=...>`, when the page renders, then the raw sequences are absent and the escaped forms are present.
- **CASE-3** — Given no `--diff-file`, when the page renders, then it contains the placeholder and no diff blocks, and the CLI exits 0.
- **CASE-4** — Given a report missing `chosen_approach`, malformed JSON input, or an absent report path, when the CLI runs, then it exits 1 naming the field on stderr, exits 2, or exits 1, respectively.
- **CASE-5** — Given the rendered page, when it is inspected, then it contains the `theme-toggle` button element.

<!-- verified-by: scripts/test_render_impl_preview.py -->

## Context (non-binding)

**Notes** — None beyond the Description above.

**Current implementation** — `consilium/scripts/render_impl_preview.py`
