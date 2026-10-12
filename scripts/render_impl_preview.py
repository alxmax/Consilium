"""Render a deliberation report (+ optional unified diff) as a static
HTML review page.

Opt-in Step 7 companion: after a deliberation (and optionally after the code
is written but before it is committed), produce one self-contained,
shareable HTML page bundling the spec (success_criterion, chosen approach,
rationale, alternatives, verification) with the multi-file diff under
review. The page is a plain file on disk — it survives the session and can
be attached to a run report for handoff review, unlike session-bound
Artifact URLs or ephemeral Plan Mode. Never part of the dispatch control
flow. Interactive orchestrators publish the generated page as an Artifact
by default (the file on disk stays the durable source; headless runs have
no Artifact surface). Origin: user request 2026-07-03, deliberation
runs/2026-07-03_1443_html-preview-impl-step.json (chosen
``preview_script_standalone``).

The HTML is self-contained: inline CSS, no external assets, every piece of
report/diff content escaped via ``html.escape``. Light/dark theme follows
``prefers-color-scheme`` (paper/ink palette, design-audit artifact style).

CLI:
    python scripts/render_impl_preview.py --input .consilium/runs/<file>.json
    git diff | python scripts/render_impl_preview.py --input <report.json>
        --diff-file -
    python scripts/render_impl_preview.py --input <report.json>
        --diff-file changes.diff --output review.html

Exits 0 on success (prints the output path), 1 on a missing required report
field or unreadable input, 2 on malformed JSON.
"""
# implements: CONSILIUM-RENDER-IMPL-PREVIEW-001
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import DATA_DIR, atomic_write_text, force_utf8_streams

PREVIEW_DIR = DATA_DIR / "preview"

REQUIRED_FIELDS = ("success_criterion", "chosen_approach", "verification")

CSS = ("""
:root {
  --paper: #F7F4EE; --paper-raised: #FFFFFF;
  --ink: #1E1B16; --ink-dim: #6B6255;
  --line: #DCD5C6; --line-strong: #C7BEA9;
  --accent: #96742F; --accent-ink: #FFFFFF;
  --go: #327A5D; --go-bg: #E4F0E9;
  --stop: #A5372F; --stop-bg: #F5E1DE;
  --warn: #B0621E; --warn-bg: #F5E9DA;
  --shadow: 0 1px 2px rgba(30,27,22,0.06), 0 8px 24px -12px rgba(30,27,22,0.18);
  --radius: 10px;
  --font-display: "Iowan Old Style", "Palatino Linotype", Palatino, "Book """
"""Antiqua", Georgia, serif;
  --font-body: -apple-system, "Segoe UI", "Helvetica Neue", Helvetica, """
"""Arial, sans-serif;
  --font-mono: ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #201E25; --paper-raised: #2A272F;
    --ink: #ECE6D8; --ink-dim: #A69C8B;
    --line: #332F38; --line-strong: #443F4B;
    --accent: #D2AA5E; --accent-ink: #201E25;
    --go: #6FBB9A; --go-bg: #1B2E28;
    --stop: #E07A72; --stop-bg: #35201D;
    --warn: #E39A4C; --warn-bg: #33261A;
    --shadow: 0 1px 2px rgba(0,0,0,0.4), 0 12px 32px -14px rgba(0,0,0,0.6);
  }
}
:root[data-theme="dark"] {
  --paper: #201E25; --paper-raised: #2A272F;
  --ink: #ECE6D8; --ink-dim: #A69C8B;
  --line: #332F38; --line-strong: #443F4B;
  --accent: #D2AA5E; --accent-ink: #201E25;
  --go: #6FBB9A; --go-bg: #1B2E28;
  --stop: #E07A72; --stop-bg: #35201D;
  --warn: #E39A4C; --warn-bg: #33261A;
  --shadow: 0 1px 2px rgba(0,0,0,0.4), 0 12px 32px -14px rgba(0,0,0,0.6);
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--paper); color: var(--ink);
  font-family: var(--font-body); font-size: 15.5px; line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}
::selection { background: var(--accent); color: var(--accent-ink); }
.wrap { max-width: 880px; margin: 0 auto; padding: 56px 24px 96px;
  display: flex; flex-direction: column; gap: 44px; }

header { display: flex; flex-direction: column; gap: 14px;
  border-bottom: 1px solid var(--line); padding-bottom: 32px; }
.eyebrow { font-family: var(--font-mono); font-size: 11.5px; letter-spacing: """
""".14em;
  text-transform: uppercase; color: var(--accent); display: flex; """
"""align-items: center; gap: 10px; }
.eyebrow::before { content: ""; width: 18px; height: 1px; background: """
"""var(--accent); display: inline-block; }
h1 { font-family: var(--font-display); font-weight: 600;
  font-size: clamp(28px, 4vw, 38px); line-height: 1.15; margin: 0;
  text-wrap: balance; letter-spacing: -0.01em; }
.proposal-line { color: var(--ink-dim); max-width: 62ch; font-size: 15px; }
.meta-row { display: flex; flex-wrap: wrap; gap: 6px 22px;
  font-family: var(--font-mono); font-size: 12px; color: var(--ink-dim); """
"""margin-top: 4px; }
.meta-row b { color: var(--ink); font-weight: 500; }

.verdict-band { background: var(--paper-raised); border: 1px solid var(--line);
  border-radius: var(--radius); box-shadow: var(--shadow); padding: 28px 30px;
  display: grid; grid-template-columns: auto 1fr; gap: 28px; align-items: """
"""center; }
.verdict-badge { display: flex; flex-direction: column; align-items: """
"""flex-start; gap: 4px; }
.verdict-word { font-family: var(--font-mono); font-weight: 600; font-size: """
"""24px;
  color: var(--go); line-height: 1.1; word-break: break-word; }
.verdict-sub { font-size: 12.5px; color: var(--ink-dim); font-family: """
"""var(--font-mono); }
.tally { display: flex; flex-direction: column; gap: 8px; }
.conf-bar { display: flex; height: 10px; border-radius: 6px; overflow: """
"""hidden; background: var(--line); }
.conf-bar span { display: block; height: 100%; }
.conf-hi { background: var(--go); } .conf-mid { background: var(--warn); } """
""".conf-lo { background: var(--stop); }
.tally-legend { display: flex; gap: 18px; font-family: var(--font-mono); """
"""font-size: 12.5px;
  font-variant-numeric: tabular-nums; color: var(--ink-dim); flex-wrap: wrap; }
.tally-legend b { color: var(--ink); font-weight: 600; }

.section { display: flex; flex-direction: column; gap: 18px; }
.section-heading { display: flex; align-items: baseline; gap: 12px; }
.section-heading h2 { font-family: var(--font-display); font-size: 20px; """
"""font-weight: 600; margin: 0; }
.section-heading .note { font-size: 12.5px; color: var(--ink-dim); }

.card-grid { display: grid; grid-template-columns: repeat(auto-fill, """
"""minmax(260px, 1fr)); gap: 14px; }
.card { background: var(--paper-raised); border: 1px solid var(--line);
  border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; }
.card summary { list-style: none; cursor: pointer; padding: 16px 18px;
  display: flex; flex-direction: column; gap: 10px; }
.card summary::-webkit-details-marker { display: none; }
.card-top { display: flex; justify-content: space-between; align-items: """
"""flex-start; gap: 10px; }
.card-name { font-family: var(--font-mono); font-weight: 600; font-size: """
"""14px; word-break: break-word; }
.pill { font-family: var(--font-mono); font-size: 11px; font-weight: 600;
  letter-spacing: .04em; padding: 3px 9px; border-radius: 20px;
  white-space: nowrap; text-transform: uppercase; }
.pill-stop { background: var(--stop-bg); color: var(--stop); }
.snip { font-size: 13.5px; color: var(--ink); line-height: 1.5; margin: 0; }
.expand-hint { font-family: var(--font-mono); font-size: 10.5px; color: """
"""var(--accent);
  text-transform: uppercase; letter-spacing: .06em; }
.card[open] .expand-hint::after { content: " \\2212"; }
.card:not([open]) .expand-hint::after { content: " +"; }
.card-body { padding: 0 18px 18px; border-top: 1px solid var(--line);
  margin-top: 2px; padding-top: 14px; }
.card-body .label { font-family: var(--font-mono); font-size: 10.5px;
  text-transform: uppercase; letter-spacing: .08em; color: var(--accent);
  margin-bottom: 5px; display: block; }
.card-body p { margin: 0; font-size: 13.5px; color: var(--ink-dim); }

.panel { background: var(--paper-raised); border: 1px solid var(--line);
  border-radius: var(--radius); box-shadow: var(--shadow); padding: 24px 30px; }
.panel code, .meta-row code, .card-body code {
  font-family: var(--font-mono); font-size: 12.5px;
  background: var(--paper); padding: 1px 5px; border-radius: 4px; }

.diff-card { background: var(--paper-raised); border: 1px solid var(--line);
  border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; }
.diff-card summary { list-style: none; cursor: pointer; padding: 12px 18px;
  display: flex; justify-content: space-between; align-items: center; gap: 10px;
  border-bottom: 1px solid var(--line); }
.diff-card summary::-webkit-details-marker { display: none; }
.diff-card .fname { font-family: var(--font-mono); font-weight: 600; """
"""font-size: 13px; word-break: break-word; }
.diff-card .stat { font-family: var(--font-mono); font-size: 11.5px; """
"""white-space: nowrap; }
.diff-card .stat .plus { color: var(--go); } .diff-card .stat .minus { """
"""color: var(--stop); }
.diff { overflow-x: auto; }
.diff pre { margin: 0; padding: 10px 0; font: 12px/1.5 var(--font-mono); }
.diff .ln { display: block; padding: 0 16px; white-space: pre; }
.diff .add { background: var(--go-bg); color: var(--go); }
.diff .del { background: var(--stop-bg); color: var(--stop); }
.diff .hunk { color: var(--accent); }
.diff .ctx { color: var(--ink-dim); }
.placeholder { color: var(--ink-dim); font-style: italic; }

footer { border-top: 1px solid var(--line); padding-top: 20px;
  font-family: var(--font-mono); font-size: 12px; color: var(--ink-dim);
  display: flex; flex-wrap: wrap; gap: 6px 24px; overflow-x: auto; }
footer b { color: var(--ink); }
@media (max-width: 560px) { .verdict-band { grid-template-columns: 1fr; } }

#theme-toggle { position: fixed; top: 16px; right: max(16px, calc(50% - """
"""470px)); z-index: 10;
  width: 38px; height: 38px; border-radius: 50%; cursor: pointer;
  border: 1px solid var(--line-strong); background: var(--paper-raised);
  color: var(--ink); box-shadow: var(--shadow); font-size: 17px; line-height: 1;
  display: flex; align-items: center; justify-content: center; padding: 0; }
#theme-toggle:hover { border-color: var(--accent); color: var(--accent); }
#theme-toggle .sun { display: none; }
:root[data-theme="dark"] #theme-toggle .sun { display: inline; }
:root[data-theme="dark"] #theme-toggle .moon { display: none; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) #theme-toggle .sun { display: inline; }
  :root:not([data-theme="light"]) #theme-toggle .moon { display: none; }
}
""")

THEME_JS = ("""
(function () {
  var root = document.documentElement;
  try {
    var saved = localStorage.getItem("consilium-preview-theme");
    if (saved === "light" || saved === "dark") root.dataset.theme = saved;
  } catch (e) {}
  document.getElementById("theme-toggle").addEventListener("click", """
"""function () {
    var dark = root.dataset.theme
      ? root.dataset.theme === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
    var next = dark ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem("consilium-preview-theme", next); } catch (e) {}
  });
})();
""")


def _esc(text: object) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def split_diff_sections(diff_text: str) -> list[tuple[str, list[str]]]:
    """Split a unified diff into (filename, lines) sections.

    Sections open on ``diff --git a/x b/y`` headers; text before the first
    header (or a headerless diff) becomes a single ``(diff)`` section.
    """
    sections: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            # `line.split()[-1]` mis-labels paths containing spaces (git
            # does not quote plain spaces). Anchor on the `a/… b/…`
            # shape and take the b/ path; fall back to the post-prefix
            # remainder on an odd header.
            m = re.match(r"^diff --git a/(.*) b/(.*)$", line)
            name = m.group(2) if m else line[len("diff --git "):]
            current = [line]
            sections.append((name, current))
        elif current is not None:
            current.append(line)
        elif line.strip():
            current = [line]
            sections.append(("(diff)", current))
    return sections


def _diff_line_class(line: str) -> str:
    if line.startswith("@@"):
        return "hunk"
    if line.startswith("+") and not line.startswith("+++"):
        return "add"
    if line.startswith("-") and not line.startswith("---"):
        return "del"
    return "ctx"


def _render_diff(diff_text: str | None) -> str:
    if not diff_text or not diff_text.strip():
        return (
            '<p class="placeholder">No diff provided — spec-only '
            'preview.</p>'
        )
    out = []
    for name, lines in split_diff_sections(diff_text):
        adds = sum(1 for ln in lines if _diff_line_class(ln) == "add")
        dels = sum(1 for ln in lines if _diff_line_class(ln) == "del")
        body = "".join(
            f'<span class="ln {_diff_line_class(ln)}">{_esc(ln) or " "}</span>'
            for ln in lines
        )
        out.append(
            f'<details class="diff-card" open><summary>'
            f'<span class="fname">{_esc(name)}</span>'
            f'<span class="stat"><span class="plus">+{adds}</span> '
            f'<span class="minus">&minus;{dels}</span></span>'
            f'</summary><div class="diff"><pre>{body}</pre></div></details>'
        )
    return "".join(out)


def _conf_class(conf: object) -> str:
    if not isinstance(conf, (int, float)):
        return "mid"
    return "hi" if conf >= 0.7 else ("mid" if conf >= 0.6 else "lo")


def _render_alternatives(alternatives: object) -> str:
    if not isinstance(alternatives, list) or not alternatives:
        return '<p class="placeholder">No alternatives recorded.</p>'
    cards = []
    for alt in alternatives:
        if not isinstance(alt, dict):
            continue
        cards.append(
            f'<details class="card"><summary>'
            f'<div class="card-top"><span class="card-name">'
            f'{_esc(alt.get("id"))}</span>'
            f'<span class="pill pill-stop">rejected</span></div>'
            f'<p class="snip">{_esc(alt.get("summary"))}</p>'
            f'<span class="expand-hint">why not</span>'
            f'</summary><div class="card-body">'
            f'<span class="label">Why not</span>'
            f'<p>{_esc(alt.get("why_not"))}</p>'
            f'</div></details>'
        )
    if not cards:
        return '<p class="placeholder">No alternatives recorded.</p>'
    return f'<div class="card-grid">{"".join(cards)}</div>'


def _conf_display(conf: object) -> tuple[str, str]:
    """Confidence as (label text, bar-width percent)."""
    if not isinstance(conf, (int, float)):
        return "n/a", "0"
    return f"{conf:.3f}", f"{conf * 100:.1f}"


def _render_legend(scores: object) -> str:
    if isinstance(scores, dict) and scores:
        return "".join(
            f"<span>{_esc(k)} <b>{_esc(v)}</b></span>"
            for k, v in scores.items()
        )
    return "<span>voice scores <b>n/a</b></span>"


def render_preview_html(
    report: dict, diff_text: str | None, title: str | None = None
) -> str:
    """Pure renderer: validated report dict + optional unified diff ->
    HTML page."""
    chosen = report.get("chosen_approach")
    tele = report.get("telemetry") or {}
    conf = report.get("confidence")
    conf_txt, conf_pct = _conf_display(conf)
    page_title = title or f"Implementation preview — {chosen}"
    legend = _render_legend(report.get("voice_scores") or {})
    n_alts = len(report.get("alternatives") or [])
    return (f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(page_title)}</title><style>{CSS}</style></head><body>
<button id="theme-toggle" title="Toggle light/dark theme" aria-label="Toggle """
f"""light/dark theme"><span class="moon">&#9789;</span><span class="sun">"""
f"""&#9788;</span></button>
<div class="wrap">

<header>
  <div class="eyebrow">Consilium &middot; implementation preview &middot; """
f"""{_esc(tele.get("mode", "n/a"))}</div>
  <h1>{_esc(page_title)}</h1>
  <p class="proposal-line">{_esc(report.get("success_criterion"))}</p>
  <div class="meta-row">
    <span>confidence <b>{_esc(conf_txt)}</b></span>
    <span>consilium <b>{_esc(tele.get("consilium_version", "n/a"))}</b></span>
    <span>alternatives <b>{n_alts}</b></span>
  </div>
</header>

<section class="verdict-band">
  <div class="verdict-badge">
    <div class="verdict-word">{_esc(chosen)}</div>
    <div class="verdict-sub">chosen approach</div>
  </div>
  <div class="tally">
    <div class="conf-bar"><span class="conf-{_conf_class(conf)}" """
f"""style="width:{conf_pct}%"></span></div>
    <div class="tally-legend"><span>confidence <b>{_esc(conf_txt)}</b>"""
f"""</span>{legend}</div>
  </div>
</section>

<section class="section">
  <div class="section-heading"><h2>Alternatives considered</h2>
  <span class="note">rejected by the deliberation — click a card for the """
f"""why-not</span></div>
  {_render_alternatives(report.get("alternatives"))}
</section>

<section class="section">
  <div class="section-heading"><h2>Verification</h2>
  <span class="note">the binary success check for this change</span></div>
  <div class="panel"><code>{_esc(report.get("verification"))}</code></div>
</section>

<section class="section">
  <div class="section-heading"><h2>Proposed changes</h2>
  <span class="note">the diff under review, per file</span></div>
  {_render_diff(diff_text)}
</section>

<footer>
  <span>generated by <b>scripts/render_impl_preview.py</b></span>
  <span>consilium <b>{_esc(tele.get("consilium_version", "n/a"))}</b></span>
  <span>self-contained &middot; safe to attach or share</span>
</footer>

</div>
<script>{THEME_JS}</script>
</body></html>
""")


def _load_report(input_path: str) -> tuple[dict | None, int]:
    """Read + validate the report; returns (report, 0) or (None, exit code)
    after printing the error."""
    try:
        raw = Path(input_path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        print(
            f"render_impl_preview: cannot read report: {exc}",
            file=sys.stderr,
        )
        return None, 1
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(
            f"render_impl_preview: malformed JSON in {input_path}: {exc}",
            file=sys.stderr,
        )
        return None, 2
    if not isinstance(report, dict):
        print(
            "render_impl_preview: report root must be a JSON object",
            file=sys.stderr,
        )
        return None, 2
    missing = [f for f in REQUIRED_FIELDS if not report.get(f)]
    if missing:
        print(
            f"render_impl_preview: report missing required field(s): "
            f"{', '.join(missing)}",
            file=sys.stderr,
        )
        return None, 1
    return report, 0


def main(argv: list[str] | None = None) -> int:
    force_utf8_streams()
    parser = argparse.ArgumentParser(
        description=(
            "Render a deliberation report (+ optional unified diff) as "
            "a static HTML review page."
        )
    )
    parser.add_argument(
        "--input", required=True,
        help="path to a runs/<file>.json deliberation report"
    )
    parser.add_argument(
        "--diff-file",
        help="unified diff to render ('-' for stdin); omit for "
             "spec-only preview"
    )
    parser.add_argument(
        "--output",
        help=f"output HTML path (default: {PREVIEW_DIR}/<input-stem>.html)"
    )
    parser.add_argument("--title", help="page title override")
    args = parser.parse_args(argv)

    report, rc = _load_report(args.input)
    if report is None:
        return rc

    diff_text: str | None = None
    if args.diff_file == "-":
        # PowerShell 5.1 pipes prepend a UTF-8 BOM that survives
        # force_utf8_streams (stdin is plain utf-8, not utf-8-sig). A
        # leading U+FEFF defeats the `diff --git ` header match,
        # mislabeling the first file's card. Same idiom as
        # utils.load_json_stdin / confidence.py / strip_context.py.
        diff_text = sys.stdin.read().lstrip("﻿")
    elif args.diff_file:
        try:
            diff_text = Path(args.diff_file).read_text(encoding="utf-8-sig")
        except OSError as exc:
            print(
                f"render_impl_preview: cannot read diff: {exc}",
                file=sys.stderr,
            )
            return 1

    out_path = (
        Path(args.output) if args.output
        else PREVIEW_DIR / f"{Path(args.input).stem}.html"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out_path, render_preview_html(report, diff_text, args.title)
    )
    print(f"preview: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
