/* efficiency-section.jsx — Usage & Efficiency section */

// Theoretical dispatch-cost multipliers (sub-agent count vs Sequential).
const MODES_DATA = [
  { mode: 'sequential',  costMultiplier: '1×',    dispatches: 0,  note: 'in-context baseline' },
  { mode: 'dialectic',   costMultiplier: '1.33×', dispatches: 1,  note: '+ 1 skeptic sub-agent' },
  { mode: 'trias',       costMultiplier: '2.67×', dispatches: 4,  note: '3 personality + 1 post-vote Skeptic sub-agent' },
  { mode: 'skeptic_on_chosen', costMultiplier: 'base +1', dispatches: 1, note: 'composable flag over any base' },
];

// SNAPSHOT 2026-05-29 (Consilium-Benchmark/RESULTS.md) — SUPERSEDED, see note below. These
// figures predate the 2026-06-23 fix that made the consilium modes actually run the
// deliberation pipeline; at capture time those modes had collapsed to a bare-model
// pass, so the consilium rows UNDERCOUNT real deliberation cost. A post-fix n=1
// spot-check puts real deliberation at ~$1–2 per reasoning task (≈8–10× these
// figures); a full n>=15 re-measurement is pending. sonnet_bare (baseline) is unaffected.
const MEASURED_COST = [
  { mode: 'sonnet_bare',          usd: '$0.148', vsBare: '1.0×', baseline: true, note: 'bare model · no Consilium' },
  { mode: 'superpowers',          usd: '$0.124', vsBare: '0.8×', note: 'generic agent-skill harness' },
  { mode: 'consilium_sequential', usd: '$0.189', vsBare: '1.3×', note: 'Consilium default' },
  { mode: 'consilium_dialectic',  usd: '$0.398', vsBare: '2.7×', note: '+ Skeptic + code context' },
  { mode: 'consilium_trias',      usd: '$0.612', vsBare: '4.1×', note: '3 personalities (benchmark, pre-redesign). The 4-spawn config token-measures at 0.67× the old 6-spawn (n=2) — confirms 2.67× vs 4×; $ re-benchmark pending' },
];

function BarChart({ data }) {
  const max = Math.max(...data.map(d => d.value));
  const colors = {
    sequential: 'var(--gen)',
    dialectic:  'var(--ctl)',
    trias:      'oklch(0.55 0.18 260)',
  };
  return (
    <svg viewBox={`0 0 640 ${data.length * 64 + 20}`} className="diagram" style={{ maxHeight: 360 }}>
      {data.map((d, i) => {
        const barW = max > 0 ? (d.value / max) * 420 : 0;
        const y = i * 64 + 10;
        const col = colors[d.mode] || 'var(--ink-2)';
        return (
          <g key={d.mode}>
            <text x="0" y={y + 16} style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fill: 'var(--ink)' }}>{d.mode}</text>
            <text x="0" y={y + 32} style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--ctl-ink)' }}>{d.model}</text>
            <rect x="160" y={y + 6} width={barW} height={28} rx="3" fill={col} opacity="0.8" />
            <text x={160 + barW + 8} y={y + 24} style={{ fontSize: 12, fill: 'var(--ink-2)', fontFamily: 'var(--font-mono)' }}>
              {d.label}
            </text>
          </g>
        );
      })}
      <text x="0" y={data.length * 64 + 16} style={{ fontSize: 11, fill: 'var(--ink-3)', fontVariantNumeric: 'tabular-nums' }}>
        measured tokens / voice dispatch · lower = cheaper per voice call
      </text>
    </svg>
  );
}

function ModeRow({ mode, costMultiplier, dispatches, note }) {
  return (
    <tr>
      <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, padding: '10px 16px 10px 0', borderBottom: '1px solid var(--rule)' }}>{mode}</td>
      <td style={{ padding: '10px 16px', borderBottom: '1px solid var(--rule)', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{costMultiplier}</td>
      <td style={{ padding: '10px 16px', borderBottom: '1px solid var(--rule)', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{dispatches}</td>
      <td style={{ padding: '10px 16px 10px 0', borderBottom: '1px solid var(--rule)', fontSize: 12, color: 'var(--ink-2)' }}>{note}</td>
    </tr>
  );
}

function MeasuredCostTable() {
  return (
    <div style={{ marginTop: 36 }}>
      <h3 style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-2)', marginBottom: 4 }}>Measured cost — bare vs the modes</h3>
      <p className="body-prose" style={{ color: 'var(--ink-2)', fontSize: 13.5, marginBottom: 14, maxWidth: 820 }}>
        A <strong>2026-05-29 snapshot</strong> over the 3-task benchmark — <strong>superseded</strong>. It was captured before the 2026-06-23 fix that made the consilium modes actually deliberate, so the consilium rows below reflect a bare-model pass, not real deliberation (a post-fix spot-check measures ~$1–2 per reasoning task, roughly 8–10× these figures). A full re-measurement at n≥15 is pending; the <code>sonnet_bare</code> baseline is unaffected. See <code>benchmark/RESULTS.md</code>.
      </p>
      <table style={{ width: '100%', maxWidth: 680, borderCollapse: 'collapse', fontSize: 13, fontFamily: 'var(--font-mono)' }}>
        <thead>
          <tr>
            {[['mode', 'left'], ['$ / run', 'right'], ['× bare', 'right'], ['', 'left']].map(([h, a], i) => (
              <th key={i} style={{ textAlign: a, padding: '6px 16px 6px 0', borderBottom: '2px solid var(--rule-2)', fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-2)' }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {MEASURED_COST.map((r) => (
            <tr key={r.mode} style={{ background: r.baseline ? 'var(--paper-2)' : 'transparent' }}>
              <td style={{ padding: '9px 16px 9px 0', borderBottom: '1px solid var(--rule)', fontWeight: r.baseline ? 600 : 400, color: 'var(--ink)' }}>{r.mode}{r.baseline ? '  ◀ baseline' : ''}</td>
              <td style={{ padding: '9px 16px', borderBottom: '1px solid var(--rule)', textAlign: 'right', color: 'var(--con-ink)', fontWeight: 600 }}>{r.usd}</td>
              <td style={{ padding: '9px 16px', borderBottom: '1px solid var(--rule)', textAlign: 'right', color: 'var(--ink-2)' }}>{r.vsBare}</td>
              <td style={{ padding: '9px 0', borderBottom: '1px solid var(--rule)', fontSize: 12, fontFamily: 'var(--font-sans)', color: 'var(--ink-3)' }}>{r.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-3)', marginTop: 8 }}>
        on this 3-task set the two harder tasks are solved by all five modes; the third is a trick question where the deliberation modes answered correctly and the single-pass baseline did not (single run — directional) — the modes buy an auditable decision process and, on that task, a better answer (RESULTS.md)
      </p>
    </div>
  );
}

function EfficiencySection() {
  // Measured by scripts/efficiency.py over runs/*.json telemetry (2026-05-30).
  // The rollup tool was retired in the 2026-06-04 dead-code triage — this is a
  // frozen snapshot, not a live feed. tokens_per_dispatch is outcome-independent
  // (no labelling needed), unlike tokens_per_OK which stayed gated on labels.
  const measured = [
    { mode: 'sequential', value: 1565, label: '1 565 tok · n=131', model: 'Sonnet 4.6' },
    { mode: 'dialectic',  value: 2313, label: '2 313 tok · n=20',  model: 'Sonnet 4.6' },
    { mode: 'trias',      value: 6346, label: '6 346 tok · n=37',  model: 'Sonnet 4.6' },
  ];

  return (
    <section className="section" id="efficiency">
      <div className="container">
        <SectionHead
          num="13"
          eyebrow="Usage & Efficiency"
          title="How much does each mode actually cost?"
          lede="The chart below is a frozen snapshot of measured tokens-per-dispatch, captured 2026-05-30 with scripts/efficiency.py — a rollup tool retired in the 2026-06-04 dead-code triage, so these are dated historical measurements, not a live feed. Per-run telemetry still accumulates in each repo's .consilium/runs/*.json. The stricter tokens_per_OK metric was held back until enough runs carry a confirmed OK/BAD label — honest measurement over a flattering one."
        />

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 32, marginTop: 32, alignItems: 'start' }}>
          <div>
            <h3 style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-2)', marginBottom: 4 }}>Mode cost multipliers <span style={{ color: 'var(--ink-3)', textTransform: 'none', letterSpacing: 0 }}>(dispatch count)</span></h3>
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-3)', marginBottom: 16 }}>1× = Sequential on Sonnet 4.6 · theoretical sub-agent dispatch ratio — measured $ below</p>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: '6px 16px 6px 0', borderBottom: '2px solid var(--rule-2)', fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-2)' }}>Mode</th>
                  <th style={{ textAlign: 'right', padding: '6px 16px', borderBottom: '2px solid var(--rule-2)', fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-2)' }}>Cost</th>
                  <th style={{ textAlign: 'right', padding: '6px 16px', borderBottom: '2px solid var(--rule-2)', fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-2)' }}>Sub-agents</th>
                  <th style={{ textAlign: 'left', padding: '6px 0', borderBottom: '2px solid var(--rule-2)', fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-2)' }}>Note</th>
                </tr>
              </thead>
              <tbody>
                {MODES_DATA.map(m => <ModeRow key={m.mode} {...m} />)}
              </tbody>
            </table>
          </div>

          <div>
            <h3 style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-2)', marginBottom: 4 }}>tokens / dispatch (measured)</h3>
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-3)', marginBottom: 16 }}>frozen snapshot · <strong style={{ color: 'var(--ctl-ink)' }}>Sonnet 4.6</strong> · captured 2026-05-30 · rollup tool retired 2026-06-04</p>
            <BarChart data={measured} />
          </div>
        </div>

        <MeasuredCostTable />

        <div style={{ marginTop: 32, display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
          {[
            { role: 'Orchestrator', model: 'your session model', color: 'var(--con)', note: 'the main Claude Code session that runs the workflow and dispatches sub-agents — on whatever model you launched Claude Code with (Opus or Sonnet). The skill does not pin it; Opus gives the strongest orchestration.' },
            { role: 'Voices & sub-agents', model: 'Sonnet 5.5', color: 'var(--ctl)', note: 'Generator · Control · Conservator · Skeptic · Trias personalities — pinned to model: "sonnet"; they do not inherit the session model.' },
            { role: 'Override', model: '→ Opus', color: 'var(--gen)', note: 'an opt-in that bumps the Generator from its pinned Sonnet up to Opus for high-stakes / ambiguous changes.' },
          ].map((m) => (
            <div key={m.role} style={{ padding: '14px 16px', border: '1px solid var(--rule)', borderTop: `3px solid ${m.color}`, borderRadius: 4, background: 'var(--paper)' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 4 }}>{m.role}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 15, fontWeight: 600, color: m.color, marginBottom: 6 }}>{m.model}</div>
              <p style={{ fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.5, margin: 0 }}>{m.note}</p>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 20, padding: '20px 24px', background: 'var(--paper-2)', border: '1px solid var(--rule)', borderRadius: 4 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-2)', marginBottom: 12 }}>Provenance</div>
          <p style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.7, margin: 0 }}>
            These numbers were produced by <code style={{ fontFamily: 'var(--font-mono)' }}>scripts/efficiency.py --by-mode</code> on 2026-05-30. The rollup script was retired in the 2026-06-04 dead-code triage, so the snapshot above is preserved as a dated measurement rather than recomputed. Per-run telemetry still accumulates in each repo's <code style={{ fontFamily: 'var(--font-mono)' }}>.consilium/runs/*.json</code>; live outcome statistics (OK/BAD/override rates — a different metric than tokens/dispatch) are available via <code style={{ fontFamily: 'var(--font-mono)' }}>python scripts/feedback.py --recent 10 --runs</code>.
          </p>
        </div>

        <div style={{ marginTop: 20, padding: '16px 24px', background: 'color-mix(in oklch, var(--con) 6%, var(--paper))', border: '1px solid color-mix(in oklch, var(--con) 20%, var(--rule))', borderRadius: 4 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--con)', marginBottom: 8 }}>Caveats</div>
          <ul style={{ fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.7, paddingLeft: 20 }}>
            <li>Token estimates use chars/4 (±10–20% error band), consistent across modes.</li>
            <li>This is cost <em>per dispatch</em>, not per run — total run cost ≈ dispatches × this, which the cost-multiplier column on the left captures (Sequential 1×, Trias 2.67×).</li>
            <li>`tokens_per_OK` (cost per confirmed-good outcome) is the stricter metric but was withheld from the snapshot — most runs at capture time were unlabeled, which would have inflated it.</li>
          </ul>
        </div>
      </div>
    </section>
  );
}

window.EfficiencySection = EfficiencySection;
