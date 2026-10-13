---
name: run-consilium
description: Run, launch, build, test, smoke-test, or screenshot the Consilium skill repo. Drives its deterministic Python surface (test suites, doc-drift gate, voice->report pipeline) and screenshots the architecture explainer. Use when asked to run/verify Consilium, confirm a change works, or capture the architecture page.
---

# Run Consilium

Consilium is a **stdlib-only Python skill repo** (the source of the `/consilium`
deliberation skill). It is not a server or a GUI app — a live deliberation is
LLM-orchestrated and can't be driven headlessly. What *can* be driven
deterministically, without an LLM, is everything around it:

- the unit-test suites (all `scripts/test_*.py`) + the doc-drift gate,
- the voice→report **pipeline** (`aggregator`→`confidence`, `build_report`→`validate_report`),
- a static React **architecture explainer** (`docs/architecture.html`) you can screenshot.

The driver below exercises all of it. **Paths are relative to the repo root**
(the Consilium checkout); run everything from there.

> Environment note: this was authored and verified on **Windows 11 / PowerShell**,
> not a Linux container. There is no `apt-get`/`xvfb`/`chromium-cli` here — the
> driver screenshots via local **Chrome/Edge headless** instead.

## Prerequisites

- **Python 3.11** (verified `3.11.1`). **No `pip install`** — every script is stdlib-only.
- For `shot` only: **Google Chrome or Microsoft Edge** installed (auto-detected),
  plus **internet** (the explainer loads React/Babel/fonts from a CDN).

## Run (agent path) — the driver

`.claude/skills/run-consilium/driver.py` is the harness. Three subcommands:

```bash
python .claude/skills/run-consilium/driver.py smoke      # tests + drift + pipeline (default)
python .claude/skills/run-consilium/driver.py pipeline   # voice->report pipeline, prints each stage
python .claude/skills/run-consilium/driver.py shot       # screenshot docs/architecture.html
```

`smoke` is what you run to confirm a change didn't break anything. Verified output:

```
[PASS] test_round2.py  (exit 0)
[PASS] test_feedback_html.py  (exit 0)
[PASS] test_lens_bias.py  (exit 0)
[PASS] test_vote_degeneracy.py  (exit 0)
[PASS] test_implement_mode.py  (exit 0)
[PASS] test_implement_pipeline.py  (exit 0)
[... every scripts/test_*.py suite — abbreviated; the drift gate keeps the full list in lockstep ...]
[PASS] check_doc_drift.py  (exit 0)
[PASS] check_public_leak.py  (exit 0)
[PASS] reqmap gate --strict  (exit 0)
[PASS] architecture build --check  (exit 0)
[PASS] run_evals.py (regression scenarios)  (exit 0)
[PASS] build_report.py | validate_report.py  (exit 0)

OK - all green
```

**`smoke` exits 0 when nothing regressed past the known baseline** (`BASELINE_EVAL_FAILURES`,
currently `0` — the suite is fully green). If you see *any* `[FAIL]`, or more eval
failures than the baseline, that's *your* change — `smoke` exits 1 and names it.

`shot` writes to `.consilium/shots/architecture.png` (gitignored) and prints the byte size:

```
[PASS] screenshot (235248 bytes)
```

Open that PNG to confirm the explainer rendered (hero "A second opinion, structured.",
nav tabs PREMISE/VOICES/LAYERS/...). A blank/tiny PNG means the CDN didn't load — check internet.

## Run individual pieces

Each script is a standalone CLI with JSON over stdin/stdout. Verified commands:

```bash
python scripts/test_round2.py                     # 25 ROUND2 unit tests -> OK
python scripts/test_feedback_html.py              # feedback tests -> "12/12 passed"
python -X utf8 scripts/run_evals.py               # regression scenarios: 72 passed, 0 failed
python -X utf8 scripts/check_doc_drift.py         # "doc-drift OK: all invariants hold"
python docs/architecture/build.py --check         # "outputs up to date" (exit 1 if src/*.jsx unbuilt)
```

The full deterministic pipeline, end to end:

```bash
cat bundle_smoke_tests.json | python consilium/scripts/build_report.py | python consilium/scripts/validate_report.py
```

Exit 0 = the assembled report satisfies the Constitution gate. `bundle_smoke_tests.json`,
`bundle_min.json`, `bundle_veto_op.json`, `bundle_high_priority.json` (repo root) are ready-made inputs.

The aggregator and confidence scripts take their **own** shape (a `candidates` list,
**not** a `build_report` bundle):

```bash
echo '{"candidates":[{"id":"a","scores":{"generator":0.9,"control":0.9,"conservator":0.2}},{"id":"b","scores":{"generator":0.5,"control":0.5,"conservator":0.5}}]}' | python consilium/scripts/aggregator.py --scheme conservative_override
```

## Architecture explainer (human path)

`docs/architecture.html` is built React source. To **edit** it, change
`docs/architecture/src/*.jsx` and regenerate with `python docs/architecture/build.py`.
`smoke` runs `build.py --check`, which exits 1 if you edited the source but forgot to
rebuild — so a stale build shows up as a `[FAIL] architecture build --check`. To just
**view** the page, open the file in a browser (needs internet), or use `driver.py shot`
to capture it headlessly.

## Gotchas

- **`validate_report.py` requires `pipeline_executed` (bool) on non-skipped reports**
  (since `7176f11`), and **bypass templates must set it `false`** — `chosen_approach`
  of `trivial-direct` or `prior-deliberation` with `pipeline_executed: true` is rejected
  as inconsistent (`validate_report.py:236`). New `evals/scenarios.json` fixtures must
  honor this, or `run_evals` goes red. (The driver's `BASELINE_EVAL_FAILURES` records
  how many such failures are pre-existing vs. your regression — currently `0`.)
- **`run_evals.py` prints its `N passed, M failed` summary to *stderr*,** not stdout.
  Capture both if you parse it (the driver does).
- **`check_doc_drift.py` needs `python -X utf8` on Windows** —
  it reads UTF-8 files and crashes on the default cp1252 console encoding. The driver
  forces this via `PYTHONUTF8=1` for every child process.
- **`docs/architecture.html` is not offline-safe.** It pulls React 18, Babel, and
  Google Fonts from a CDN, so `file://` rendering (and the screenshot) needs internet.
  The other repo HTML (`experiments/*.html`, `.consilium/FEEDBACK.html`)
  *is* self-contained.
- **No `chromium-cli` on this box.** The driver looks for Chrome then Edge at their
  standard Windows install paths and shells out with `--headless=new --screenshot=...`.
- **Aggregator input ≠ build_report bundle.** Feeding a `bundle_*.json` to
  `aggregator.py` throws — it wants `{"candidates":[{"id","scores":{...}}]}`.

## Troubleshooting

- `UnicodeDecodeError` / `UnicodeEncodeError` from a script run by hand → prefix with
  `python -X utf8` (or set `PYTHONUTF8=1`). The driver already does.
- `smoke` exits 1 with "**> baseline**" → you regressed `run_evals` (or it can't parse
  the summary). Run `python -X utf8 scripts/run_evals.py` and read the `FAIL` lines.
- `shot` prints `FAIL: no Chrome/Edge found` → install one, or add its path to
  `BROWSERS` in `driver.py`.
- `shot` produces a 0-byte / blank PNG → no internet; the CDN assets didn't load.
- `aggregator.py` traceback about missing `scores` → you fed it a `build_report`
  bundle. Use the `candidates` shape shown above.
