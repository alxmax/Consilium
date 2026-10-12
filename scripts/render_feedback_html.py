"""Render entries + runs/*.json into a single dark-themed FEEDBACK.html.

Pure functions; no I/O except optional CLI shim. The HTML is self-contained
(inline <style> + <script>, no external assets). Drill-down content is
embedded statically per entry from the linked runs/*.json file.

CLI:
    python scripts/render_feedback_html.py < entries.json
    python scripts/render_feedback_html.py --feedback path/to/FEEDBACK.html
    < entries.json
"""
# implements: CONSILIUM-RENDER-FEEDBACK-HTML-001
from __future__ import annotations

import argparse
import html
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# This module is loaded via importlib from several entry points (priors,
# log_feedback, mark_outcome, audit_feedback), so scripts/ may not be on
# sys.path. Bootstrap it
# before importing the shared utils constants.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import RUNS_DIR, force_utf8_streams, load_json_stdin


@dataclass
class Entry:
    date: str
    context: str
    chosen: str
    outcome: str  # OK | BAD | OVR | PEND
    note: str
    # relative path to runs/*.json (or None for legacy)
    run_path: str | None = None
    vote_pattern: str = ""  # e.g. "2-1" for Trias mode; empty for non-Trias


CSS = (
    "\n"
    ":root{--bg:#16161a;--bg-alt:#1c1c22;--bg-row:#1a1a20;--bg-row-alt:#1e1e25;"
    "--bg-drill:#121216;--fg:#d6d6d6;--fg-dim:#8a8a92;--fg-soft:#b4b4bc;--borde"
    "r:#2a2a32;--border-soft:#23232b;--accent:#7fb3ff;--mono:#9fc7ff;--ok:#5ec2"
    "7a;--bad:#e36868;--ovr:#e0a85c;--pend:#787884;--valid:#5ec27a;--invalid:#e"
    "36868}\n"
    "*{box-sizing:border-box}\n"
    "body{font:13px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;margin:1.5e"
    "m;color:var(--fg);max-width:1400px;background:var(--bg)}\n"
    "h2{margin:0 0 .25em;font-size:18px;font-weight:600;color:#fff}\n"
    ".sub{color:var(--fg-dim);font-size:12px;margin-bottom:1.25em}\n"
    "table{border-collapse:collapse;width:100%}\n"
    "th,td{border-bottom:1px solid var(--border-soft);padding:7px 10px;text-ali"
    "gn:left;vertical-align:top}\n"
    "th{background:var(--bg-alt);font-weight:600;color:var(--fg-soft);white-spa"
    "ce:nowrap;font-size:12px;text-transform:uppercase;letter-spacing:.04em}\n"
    "tbody tr.entry{cursor:pointer;background:var(--bg-row);transition:backgrou"
    "nd .12s}\n"
    "tbody tr.entry:nth-child(4n+3){background:var(--bg-row-alt)}\n"
    "tbody tr.entry:hover{background:#252530}\n"
    "tbody tr.entry.open{background:#2b2b36}\n"
    "td.outcome{font-weight:600;text-align:center;white-space:nowrap;font-size:"
    "12px;letter-spacing:.05em}\n"
    ".OK{color:var(--ok)}.BAD{color:var(--bad)}.OVR{color:var(--ovr)}.PEND{colo"
    "r:var(--pend)}.PEND_HEADLESS{color:var(--pend);opacity:.65}.CLOSED_UNVERIF"
    "IED{color:var(--pend);opacity:.5}\n"
    "td.date{white-space:nowrap;color:var(--fg-dim);font-variant-numeric:tabula"
    "r-nums}\n"
    "td.chosen{font-family:Consolas,Menlo,monospace;font-size:12px;color:var(--"
    "mono)}\n"
    "td.note{color:var(--fg-soft);font-size:12px}\n"
    "td.tokens{font-family:Consolas,Menlo,monospace;font-size:12px;color:var(--"
    "fg-dim);text-align:right;font-variant-numeric:tabular-nums;white-space:now"
    "rap}\n"
    "td.tokens.na{color:var(--border)}\n"
    "td.tokens .calc{color:var(--border);font-size:10px;margin-left:3px;font-st"
    "yle:italic}\n"
    "td.chev{width:18px;color:var(--fg-dim);text-align:center;font-family:monos"
    "pace}\n"
    "tr.entry.open td.chev{color:var(--accent)}\n"
    "tr.drill{display:none;background:var(--bg-drill)}\n"
    "tr.drill.open{display:table-row}\n"
    "tr.drill td{border-bottom:1px solid var(--border);padding:14px 18px}\n"
    ".drill-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px}\n"
    ".voice{background:var(--bg-alt);border:1px solid var(--border-soft);border"
    "-radius:6px;padding:12px 14px}\n"
    ".voice h4{margin:0 0 8px;font-size:11px;text-transform:uppercase;letter-sp"
    "acing:.08em;color:var(--accent);font-weight:600}\n"
    ".voice h4 .count{color:var(--fg-dim);font-weight:400;margin-left:6px}\n"
    ".cand{padding:8px 0;border-top:1px dashed var(--border-soft)}\n"
    ".cand:first-of-type{border-top:none;padding-top:2px}\n"
    ".cand .cid{font-family:Consolas,Menlo,monospace;font-size:11px;color:var(-"
    "-mono);font-weight:600}\n"
    ".cand .csum{color:var(--fg);font-size:12px;margin:2px 0}\n"
    ".cand .csketch{color:var(--fg-dim);font-size:11px;font-style:italic;margin"
    "-top:2px}\n"
    ".badge{display:inline-block;padding:1px 6px;border-radius:3px;font-size:10"
    "px;font-weight:600;letter-spacing:.03em;margin-left:6px;vertical-align:mid"
    "dle}\n"
    ".badge.valid{background:rgba(94,194,122,.15);color:var(--valid)}\n"
    ".badge.invalid{background:rgba(227,104,104,.15);color:var(--invalid)}\n"
    ".issue{color:var(--bad);font-size:11px;margin-top:3px}\n"
    ".issue::before{content:\"\\2715 \";color:var(--bad)}\n"
    ".test{color:var(--fg-dim);font-size:11px;margin-top:2px;font-family:Consol"
    "as,Menlo,monospace}\n"
    ".test::before{content:\"\\2713 \";color:var(--ok)}\n"
    ".risk{font-family:Consolas,Menlo,monospace;font-size:13px;font-weight:600;"
    "float:right}\n"
    ".risk.low{color:var(--ok)}.risk.mid{color:var(--ovr)}.risk.high{color:var("
    "--bad)}\n"
    ".factors{display:grid;grid-template-columns:repeat(2,1fr);gap:1px 10px;fon"
    "t-size:10px;color:var(--fg-dim);margin-top:3px;font-family:Consolas,Menlo,"
    "monospace}\n"
    ".factors b{color:var(--fg-soft);font-weight:400}\n"
    ".stub{color:var(--fg-dim);font-style:italic;font-size:12px;text-align:cent"
    "er;padding:8px}\n"
    ".stub.error{color:var(--bad)}\n"
)

JS = """
function toggleDrill(row){
  var next = row.nextElementSibling;
  var chev = row.querySelector('.chev');
  if(next && next.classList.contains('drill')){
    var open = next.classList.toggle('open');
    row.classList.toggle('open', open);
    if(chev) chev.textContent = open ? '▾' : '▸';
  }
}
"""


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _row_html(
    e: Entry, drill_inner: str, tokens_html: str, tokens_kind: str
) -> str:
    chev = "▸"
    tokens_cls = "tokens" if tokens_kind != "na" else "tokens na"
    return (
        f'<tr class="entry" onclick="toggleDrill(this)">'
        f'<td class="chev">{chev}</td>'
        f'<td class="date" data-field="date">{_esc(e.date)}</td>'
        f'<td data-field="context">{_esc(e.context)}</td>'
        f'<td class="chosen" data-field="chosen">{_esc(e.chosen)}</td>'
        f'<td class="outcome {_esc(e.outcome)}" data-field="outcome">'
        f'{_esc(e.outcome)}</td>'
        f'<td class="{tokens_cls}" data-field="tokens">{tokens_html}</td>'
        f'<td class="note" data-field="note">{_esc(e.note)}</td>'
        f'<td data-field="vote_pattern">{_esc(e.vote_pattern)}</td>'
        f'</tr>\n'
        f'<tr class="drill"><td colspan="8">{drill_inner}</td></tr>\n'
    )


def _format_int_compact(total: int) -> str:
    if total < 1000:
        return str(total)
    formatted = f"{total/1000:.1f}"
    if formatted.endswith(".0"):
        formatted = formatted[:-2]
    return f"{formatted}k"


def _measured_tokens(run: dict | None) -> int:
    """Sum tokens_in + tokens_out across run.telemetry.voices. Returns
    0 if absent."""
    if not run:
        return 0
    voices = ((run.get("telemetry") or {}).get("voices") or {})
    total = 0
    for v in voices.values():
        if not isinstance(v, dict):
            continue
        ti = v.get("tokens_in") or 0
        to = v.get("tokens_out") or 0
        if isinstance(ti, (int, float)):
            total += int(ti)
        if isinstance(to, (int, float)):
            total += int(to)
    return total


def _candidate_count(run: dict | None) -> int:
    """Number of candidates in the generator step of the deliberation log."""
    if not run:
        return 0
    for step in run.get("deliberation_log") or []:
        if isinstance(step, dict) and step.get("step") == "generator":
            return len(step.get("candidates") or [])
    return 0


def _format_tokens(
    run: dict | None, avg_per_candidate: float | None
) -> tuple[str, str]:
    """Return (html_fragment, kind) where kind in {measured, calculated, na}.

    Measured: telemetry present and non-zero.
    Calculated: telemetry missing/empty, candidate count available, and
                avg_per_candidate derivable from peer runs — estimate
                marked (calc).
    na: nothing usable — render em-dash.
    """
    measured = _measured_tokens(run)
    if measured > 0:
        return _format_int_compact(measured), "measured"
    if avg_per_candidate is not None:
        nc = _candidate_count(run)
        if nc > 0:
            est = int(round(nc * avg_per_candidate))
            if est > 0:
                return (
                    f'{_format_int_compact(est)} '
                    f'<span class="calc">(calc)</span>'
                ), "calculated"
    return "—", "na"


def _risk_class(score: float) -> str:
    if score < 0.3:
        return "low"
    if score < 0.6:
        return "mid"
    return "high"


def _gen_panel(run: dict, chosen_id: str) -> str:
    log = run.get("deliberation_log") or []
    gen_step = next(
        (s for s in log
         if isinstance(s, dict) and s.get("step") == "generator"), {})
    cands = gen_step.get("candidates") or []
    parts = [
        f'<div class="voice"><h4>Generator '
        f'<span class="count">{len(cands)} candidates</span></h4>'
    ]
    for c in cands:
        # Some legacy runs encode bare candidates as a plain string
        # (e.g. "do_nothing").
        # Promote them to a minimal dict so panel rendering stays uniform.
        if isinstance(c, str):
            c = {"id": c, "summary": "", "sketch": ""}
        elif not isinstance(c, dict):
            continue
        cid = _esc(c.get("id", ""))
        chosen_badge = (
            ' <span class="badge valid">CHOSEN</span>'
            if c.get("id") == chosen_id else ""
        )
        summary = _esc(c.get("summary", ""))
        sketch = _esc(c.get("sketch", ""))
        parts.append(
            f'<div class="cand"><div><span class="cid">{cid}</span>'
            f'{chosen_badge}</div>'
            f'<div class="csum">{summary}</div>'
            f'<div class="csketch">{sketch}</div></div>'
        )
    parts.append("</div>")
    return "".join(parts)


def _ctrl_panel(run: dict) -> str:
    log = run.get("deliberation_log") or []
    ctrl_step = next(
        (s for s in log
         if isinstance(s, dict) and s.get("step") == "control"), {})
    verdicts = [
        v for v in (ctrl_step.get("verdicts") or []) if isinstance(v, dict)
    ]
    n_valid = sum(1 for v in verdicts if v.get("valid"))
    n_invalid = len(verdicts) - n_valid
    parts = [
        f'<div class="voice"><h4>Control '
        f'<span class="count">{n_valid} valid, {n_invalid} invalid</span>'
        f'</h4>'
    ]
    for v in verdicts:
        cid = _esc(v.get("id", ""))
        badge_cls = "valid" if v.get("valid") else "invalid"
        badge_txt = "valid" if v.get("valid") else "invalid"
        parts.append(
            f'<div class="cand"><div><span class="cid">{cid}</span> '
            f'<span class="badge {badge_cls}">{badge_txt}</span></div>'
        )
        # Older runs carry issues/tests as bare strings, not dicts —
        # render both.
        for issue in v.get("issues") or []:
            if isinstance(issue, dict):
                cat = _esc(issue.get("category", ""))
                detail = _esc(issue.get("detail", ""))
                parts.append(f'<div class="issue">{cat}: {detail}</div>')
            else:
                parts.append(f'<div class="issue">{_esc(str(issue))}</div>')
        for t in v.get("tests_to_write") or []:
            if isinstance(t, dict):
                name = _esc(t.get("name", ""))
                assertion = _esc(t.get("assert", ""))
                parts.append(f'<div class="test">{name}: {assertion}</div>')
            else:
                parts.append(f'<div class="test">{_esc(str(t))}</div>')
        parts.append("</div>")
    parts.append("</div>")
    return "".join(parts)


def _cons_panel(run: dict) -> str:
    log = run.get("deliberation_log") or []
    cons_step = next(
        (s for s in log
         if isinstance(s, dict) and s.get("step") == "conservator"), {})
    scores = [s for s in (cons_step.get("scores") or []) if isinstance(s, dict)]

    # Authoritative VETOED list: read from the aggregate step's `vetoed` list
    # — that's what aggregator.py actually used to drop candidates. Re-deriving
    # from a hard-coded risk_score threshold here used to drift (renderer used
    # `>= 0.7`, aggregator uses `> DEFAULT_VETO = 0.8`) and lied about every
    # candidate in the [0.7, 0.8] band. Falls back to empty set when missing
    # (older runs, manual constructs) — under-showing VETOED is preferable to
    # fabricating it.
    agg_step = next(
        (s for s in log
         if isinstance(s, dict) and s.get("step") == "aggregate"), {})
    agg_raw = agg_step.get("result")
    agg_result = agg_raw if isinstance(agg_raw, dict) else {}
    vetoed_ids = {
        v.get("id") for v in (agg_result.get("vetoed") or [])
        if isinstance(v, dict)
    }
    n_vetoed = sum(1 for s in scores if s.get("id") in vetoed_ids)
    parts = [
        f'<div class="voice"><h4>Conservator '
        f'<span class="count">{len(scores)} scored, '
        f'{n_vetoed} vetoed</span></h4>'
    ]
    for s in scores:
        cid_raw = s.get("id", "")
        cid = _esc(cid_raw)
        rs = s.get("risk_score") or 0.0
        rcls = _risk_class(rs)
        vetoed_badge = (
            ' <span class="badge invalid">VETOED</span>'
            if cid_raw in vetoed_ids else ""
        )
        f = s.get("factors") or {}
        parts.append(
            f'<div class="cand">'
            f'<span class="risk {rcls}">{rs:.2f}</span>'
            f'<div><span class="cid">{cid}</span>{vetoed_badge}</div>'
            f'<div class="factors">'
            f'<span><b>diff:</b> {(f.get("diff_size") or 0):.2f}</span>'
            f'<span><b>scope:</b> {(f.get("scope_drift") or 0):.2f}</span>'
            f'<span><b>regr:</b> {(f.get("regression_risk") or 0):.2f}</span>'
            f'<span><b>rev:</b> {(f.get("reversibility") or 0):.2f}</span>'
            f'</div></div>'
        )
    parts.append("</div>")
    return "".join(parts)


def render_drill(run: dict, chosen_id: str) -> str:
    return (
        '<div class="drill-grid">'
        + _gen_panel(run, chosen_id)
        + _ctrl_panel(run)
        + _cons_panel(run)
        + "</div>"
    )


def _legacy_stub() -> str:
    return (
        '<div class="stub">no detailed run data — older entry '
        'pre-runs/</div>'
    )


def _load_run_dict(run_path: str | None, runs_dir: Path) -> dict | None:
    if not run_path:
        return None
    run_file = (
        runs_dir.parent / run_path
        if not Path(run_path).is_absolute() else Path(run_path)
    )
    if not run_file.exists():
        run_file = runs_dir / Path(run_path).name
    if not run_file.exists():
        return None
    try:
        # utf-8-sig so a BOM-prefixed run (PS 5.1 pipe) keeps its drill-down
        # panel instead of silently degrading to the "no detailed run data"
        # stub — matches feedback.py/priors.py.
        return json.loads(run_file.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return None


def render(entries: list[Entry], runs_dir: Path) -> str:
    # First pass: load run dicts and derive median tokens/candidate
    # from measured runs.
    # Used to backfill a (calc) estimate for legacy runs without telemetry.
    run_dicts: list[dict | None] = [
        _load_run_dict(e.run_path, runs_dir) for e in entries
    ]
    per_cand_samples: list[float] = []
    for rd in run_dicts:
        tt = _measured_tokens(rd)
        nc = _candidate_count(rd)
        if tt > 0 and nc > 0:
            per_cand_samples.append(tt / nc)
    avg_per_candidate: float | None = None
    if per_cand_samples:
        per_cand_samples.sort()
        avg_per_candidate = per_cand_samples[len(per_cand_samples) // 2]

    rows = []
    for e, run_dict in zip(entries, run_dicts):
        drill = render_drill(run_dict, e.chosen) if run_dict else _legacy_stub()
        tokens_html, tokens_kind = _format_tokens(run_dict, avg_per_candidate)
        rows.append(_row_html(e, drill, tokens_html, tokens_kind))
    rows_html = "".join(rows)
    return (
        "<!doctype html>\n"
        "<meta charset=\"utf-8\">\n"
        "<title>Consilium feedback</title>\n"
        f"<style>{CSS}</style>\n"
        "<h2>Consilium feedback</h2>\n"
        f"<div class=\"sub\">{len(entries)} entries · "
        f".consilium/FEEDBACK.html · click a row for voice details</div>\n"
        "<table>\n"
        "<thead><tr><th></th><th>Data</th><th>Context</th><th>Chosen</th>"
        "<th>Outcome</th><th>Tokens</th><th>Note</th>"
        "<th>Vote Pattern</th></tr></thead>\n"
        f"<tbody>\n{rows_html}</tbody>\n"
        "</table>\n"
        f"<script>{JS}</script>\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs-dir", default=None)
    args = ap.parse_args(argv)
    force_utf8_streams()
    # BOM-strip + clean exit 2 on bad input
    data = load_json_stdin("render_feedback_html.py")
    entries = [Entry(**e) for e in data.get("entries", [])]
    runs_dir = Path(args.runs_dir) if args.runs_dir else RUNS_DIR
    sys.stdout.write(render(entries, runs_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
