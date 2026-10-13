/* extras.jsx — Why-3-voices Venn, Cost scatter, Collapsible, Benchmark */

/* === Generic collapsible — for hiding dense technical detail === */
function Collapsible({ label = 'Show technical detail', children, defaultOpen = false }) {
  const [open, setOpen] = React.useState(defaultOpen);
  const [hover, setHover] = React.useState(false);
  return (
    <div style={{ marginTop: 18 }}>
      <button
        className="collapsible-btn"
        data-open={open}
        onClick={() => setOpen(!open)}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        style={{
          appearance: 'none',
          background: open
            ? 'var(--paper-2)'
            : (hover
              ? 'color-mix(in oklch, var(--signal) 14%, var(--paper))'
              : 'color-mix(in oklch, var(--signal) 8%, var(--paper))'),
          border: `1px solid ${open ? 'var(--rule-2)' : 'var(--signal)'}`,
          color: 'var(--ink)',
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          padding: '10px 16px',
          borderRadius: 2,
          cursor: 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 10,
          transition: 'all 0.2s',
          fontWeight: 500,
          position: 'relative',
          overflow: 'hidden',
          animation: open ? 'none' : 'collapsible-pulse 2.4s ease-in-out infinite',
        }}
      >
        <span style={{
          display: 'inline-grid',
          placeItems: 'center',
          width: 18,
          height: 18,
          borderRadius: 2,
          background: 'var(--signal)',
          color: 'var(--paper)',
          fontSize: 13,
          fontWeight: 600,
          flexShrink: 0,
        }}>{open ? '−' : '+'}</span>
        {open ? `Hide ${label.toLowerCase().replace(/^show /, '')}` : label}
      </button>
      <div
        style={{
          maxHeight: open ? 5000 : 0,
          overflow: 'hidden',
          opacity: open ? 1 : 0,
          transition: 'max-height 0.5s ease, opacity 0.3s ease',
          marginTop: open ? 18 : 0,
        }}
        aria-hidden={!open}
      >
        {children}
      </div>
    </div>
  );
}

/* === Why three voices, not one? — Venn diagram (simplified) === */
function WhyThreeVoices() {
  return (
    <div style={{ margin: '18px 0 28px', padding: '24px 0' }}>
      <h3 className="h-sub" style={{ marginBottom: 6, fontSize: 22 }}>Why three voices, not one?</h3>
      <p className="body-prose" style={{ color: 'var(--ink-2)', marginBottom: 22, maxWidth: 720 }}>
        One LLM evaluating its own proposal has predictable blind spots — it generates ideas and validates them from the same perspective. Three voices with disjoint mandates (creative · analytical · risk) cross-validate before aggregation.
      </p>

      <svg viewBox="0 0 480 280" className="diagram" style={{ maxHeight: 320, maxWidth: 520, margin: '0 auto', display: 'block' }}>
        {/* Three overlapping circles — centered */}
        <circle cx="190" cy="120" r="78" fill="var(--gen-soft)" stroke="var(--gen)" strokeWidth="1.6" opacity="0.78" />
        <circle cx="290" cy="120" r="78" fill="var(--ctl-soft)" stroke="var(--ctl)" strokeWidth="1.6" opacity="0.78" />
        <circle cx="240" cy="195" r="78" fill="var(--con-soft)" stroke="var(--con)" strokeWidth="1.6" opacity="0.78" />

        <text x="155" y="92" textAnchor="middle" style={{ fontFamily: 'var(--font-sans)', fontSize: 15, fontWeight: 600, fill: 'var(--gen-ink)' }}>Generator</text>
        <text x="155" y="108" textAnchor="middle" style={{ fontFamily: 'var(--font-sans)', fontSize: 12, fill: 'var(--gen-ink)' }}>creative</text>

        <text x="325" y="92" textAnchor="middle" style={{ fontFamily: 'var(--font-sans)', fontSize: 15, fontWeight: 600, fill: 'var(--ctl-ink)' }}>Control</text>
        <text x="325" y="108" textAnchor="middle" style={{ fontFamily: 'var(--font-sans)', fontSize: 12, fill: 'var(--ctl-ink)' }}>verify</text>

        <text x="240" y="232" textAnchor="middle" style={{ fontFamily: 'var(--font-sans)', fontSize: 15, fontWeight: 600, fill: 'var(--con-ink)' }}>Conservator</text>
        <text x="240" y="248" textAnchor="middle" style={{ fontFamily: 'var(--font-sans)', fontSize: 12, fill: 'var(--con-ink)' }}>risk</text>

        {/* center label */}
        <text x="240" y="150" textAnchor="middle" style={{ fontFamily: 'var(--font-sans)', fontSize: 11, fill: 'var(--ink-2)', fontStyle: 'italic' }}>cross-validated</text>
      </svg>
    </div>
  );
}

/* === Cost vs Independence scatter for the Modes section === */
function CostScatter() {
  // x = independence (0 = shared context, 1 = full sub-agent isolation)
  // y = cost multiplier of Sequential
  const MODES_PLOT = [
    { id: 'BARE', x: 0.02, y: 0.78, label: 'sonnet_bare', cost: 'baseline · $0.148', model: 'Sonnet 4.6', sub: 'bare model · no Consilium', color: 'var(--ink-3)' },
    { id: 'SEQ',  x: 0.20, y: 1.00, label: 'Sequential', cost: '1× · $0.189', model: 'Sonnet 4.6', sub: 'default · 0 sub-agents', color: 'var(--con)' },
    { id: 'DIAL', x: 0.40, y: 1.33, label: 'Dialectic', cost: '1.33×', model: 'Sonnet 4.6', sub: 'seq + 1 Skeptic', color: 'var(--ctl)' },
    { id: 'TRI',  x: 0.90, y: 2.67, label: 'Trias', cost: '2.67×', model: 'Sonnet (all 3)', sub: '4 sub-agents · 3 personality + 1 Skeptic', color: 'oklch(0.55 0.16 320)' },
  ];

  const W = 720, H = 360;
  const padL = 70, padR = 50, padT = 30, padB = 60;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const maxY = 4.5;
  const xScale = (v) => padL + v * plotW;
  const yScale = (v) => padT + plotH - (v / maxY) * plotH;

  return (
    <div style={{ margin: '24px 0' }}>
      <h3 className="h-sub" style={{ fontSize: 20, marginBottom: 6 }}>Cost vs voice independence</h3>
      <p className="body-prose" style={{ color: 'var(--ink-2)', fontSize: 14, marginBottom: 14, maxWidth: 720 }}>
        Where each mode lands on the cost / isolation map. <code>BARE</code> (<code>sonnet_bare</code>, no Consilium) is the measured baseline — it sits below 1×; the deliberation modes cost more for the auditable process they add. <code>SEQ</code> is cheap but shared-context; <code>TRI</code> spends 4× for fully isolated sub-agents. Dispatched voices are pinned to <strong>Sonnet 5.5</strong> — including all three Trias personalities (per <code>personalities.py</code>); divergence comes from lens re-weighting, not model tier. The orchestrator runs on <strong>your session model</strong>, with an opt-in <strong>Opus</strong> override on the Generator for high-stakes changes.
      </p>

      <svg viewBox={`0 0 ${W} ${H}`} className="diagram">
        {/* Y-axis grid */}
        {[1, 2, 3, 4].map((v) => (
          <g key={v}>
            <line x1={padL} y1={yScale(v)} x2={W - padR} y2={yScale(v)} stroke="var(--rule)" strokeWidth="0.5" strokeDasharray="2 4" />
            <text x={padL - 10} y={yScale(v) + 4} textAnchor="end" style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fill: 'var(--ink-3)' }}>{v}×</text>
          </g>
        ))}

        {/* X-axis ticks */}
        <line x1={padL} y1={padT + plotH} x2={W - padR} y2={padT + plotH} stroke="var(--ink-3)" strokeWidth="1" />
        <line x1={padL} y1={padT} x2={padL} y2={padT + plotH} stroke="var(--ink-3)" strokeWidth="1" />

        {/* Axis labels */}
        <text x={padL + plotW / 2} y={H - 18} textAnchor="middle" style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fill: 'var(--ink-2)' }}>
          voice independence →
        </text>
        <text x={20} y={padT + plotH / 2} textAnchor="middle" transform={`rotate(-90 20 ${padT + plotH / 2})`} style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fill: 'var(--ink-2)' }}>
          cost (× Sequential) ↑
        </text>

        {/* Quadrant guide text */}
        <text x={padL + 20} y={padT + 20} style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--ink-3)' }}>
          expensive + isolated
        </text>
        <text x={W - padR - 20} y={padT + plotH - 10} textAnchor="end" style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--ink-3)' }}>
          cheap + isolated
        </text>

        {/* Points */}
        {MODES_PLOT.map((m, i) => {
          const cx = xScale(m.x);
          const cy = yScale(m.y);
          return (
            <g key={m.id} className="scatter-point" style={{ ['--vib-delay']: `${i * 0.4}s`, transformOrigin: `${cx}px ${cy}px` }}>
              <circle cx={cx} cy={cy} r="22" fill={m.color} opacity="0.18" />
              <circle cx={cx} cy={cy} r="14" fill={m.color} stroke="var(--paper)" strokeWidth="2" />
              <text x={cx} y={cy + 4} textAnchor="middle" style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700, fill: 'var(--paper)' }}>{m.id}</text>

              {/* label above */}
              <text x={cx} y={cy - 26} textAnchor="middle" style={{ fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 500, fill: 'var(--ink)' }}>{m.label}</text>
              <text x={cx} y={cy - 14} textAnchor="middle" style={{ fontFamily: 'var(--font-mono)', fontSize: 10, fill: 'var(--ink-3)' }}>{m.cost}</text>
              {/* model below */}
              <text x={cx} y={cy + 32} textAnchor="middle" style={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: 'var(--ctl-ink)' }}>{m.model}</text>
            </g>
          );
        })}

      </svg>
    </div>
  );
}

/* === Cost relative bar chart + table === */
function CostBars() {
  const ROWS = [
    { name: 'sequential', cost: 1.0, label: '1×', sub: 'default', color: 'var(--con)', subagents: 0 },
    { name: 'dialectic', cost: 1.33, label: '1.33×', sub: 'seq + skeptic', color: 'var(--ctl)', subagents: 1 },
    { name: 'trias', cost: 2.67, label: '2.67×', sub: '4 sub-agents', color: 'oklch(0.55 0.16 320)', subagents: 4 },
  ];

  const maxCost = 3.0;

  return (
    <div style={{ marginTop: 24 }}>
      <h3 className="h-sub" style={{ fontSize: 20, marginBottom: 6 }}>Relative cost — baseline = Sequential 1×</h3>
      <p className="body-prose" style={{ color: 'var(--ink-2)', fontSize: 14, marginBottom: 18, maxWidth: 720 }}>
        Each bar is the API cost of a single deliberation relative to Sequential. Independence comes at a multiplicative cost — three sub-agents cost three Claude invocations.
      </p>

      <div style={{ border: '1px solid var(--rule)', borderRadius: 2, background: 'var(--paper)', overflow: 'hidden' }}>
        {ROWS.map((r, i) => {
          const pct = (r.cost / maxCost) * 100;
          return (
            <div key={r.name} style={{
              display: 'grid',
              gridTemplateColumns: '140px 1fr 90px 80px',
              gap: 14,
              alignItems: 'center',
              padding: '14px 18px',
              borderBottom: i === ROWS.length - 1 ? 0 : '1px solid var(--rule)',
            }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: r.color }}>{r.name}</span>
              <div style={{ background: 'var(--paper-2)', height: 18, borderRadius: 2, position: 'relative' }}>
                <div style={{
                  height: '100%',
                  width: `${pct}%`,
                  background: r.color,
                  borderRadius: 2,
                  transition: 'width 0.6s cubic-bezier(0.4, 0, 0.2, 1)',
                }} />
              </div>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: r.color, fontWeight: 500 }}>{r.label}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-3)' }}>{r.subagents} sub</span>
            </div>
          );
        })}
      </div>
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-3)', marginTop: 10 }}>
        + <code>skeptic_on_chosen</code> adds +1 sub-agent to any base mode (advisory by default).
      </p>
    </div>
  );
}

/* === Benchmark section === */

const BENCH_TASKS = [
  {
    id: 'circuit_breaker',
    name: 'Circuit Breaker',
    kind: 'Code',
    lang: 'C++17',
    difficulty: 'Hard',
    summary: 'Implement a three-state circuit breaker (CLOSED → OPEN → HALF_OPEN) header-only in C++17. No threading, no callable wrapper — just state and transitions. Sharp edges on the half-open path.',
    prompt: `class CircuitBreaker {
public:
    enum class State { CLOSED, OPEN, HALF_OPEN };
    CircuitBreaker(int failure_threshold,
                   int recovery_timeout_sec,
                   int success_threshold);
    void record_success();
    void record_failure();
    bool is_open() const;
    State state() const;
};`,
    grading: 'Two-phase: the model\'s own tests_self.cpp (~20 pts) plus a hidden suite it never sees, compiled against a reference solution (~40 pts). Both must compile and exit 0; the hidden suite carries most of the weight.',
  },
  {
    id: 'rule_of_three',
    name: 'Rule of Three',
    kind: 'Reasoning',
    lang: '—',
    difficulty: 'Hard',
    summary: 'Day 1: 57 workers produce 100 pieces in 3 hours. Day 2: 100 scheduled, 4 sick, 2 injured. How long does the day-2 crew take to produce 20 pieces? The trap: status-quo workforce math distracts from per-worker rate.',
    prompt: `Day 1: 57 workers · 100 pieces · 3 hours
Day 2: 100 - 4 (sick) - 2 (injured) = 94 active
Output 20 pieces. How long?
  A) 0.3 hours
  B) 18 min 45 s
  C) Something else
  D) 0.5 hours`,
    grading: 'answer.md first line must be `ANSWER: <letter>`. VALUE in decimal minutes, 3–4 decimals. Mathematically correct → full credit.',
  },
  {
    id: 'transport_choice',
    name: 'Transport Choice',
    kind: 'Reasoning',
    lang: '—',
    difficulty: 'Trick',
    summary: 'You want to wash your car 50 meters away. Walk / something else / train / fly? Looks trivial — but the obvious choice quietly fails the actual goal. The one task in the corpus that separates the modes.',
    prompt: `Wash car · 50 meters away.
  A) Walk there
  B) Something else
  C) Go by train
  D) Fly there
Pick one. Justify.`,
    grading: 'answer.md first line must be `ANSWER: <letter>`. Justification must cover the other 3 options and state the key assumption.',
  },
];

const MODES_TESTED = [
  { id: 'sonnet_bare',   name: 'sonnet_bare',        tag: 'baseline', desc: 'Single Sonnet invocation, no orchestration.' },
  { id: 'superpowers',   name: 'superpowers',        tag: 'baseline', desc: 'Sonnet + tool harness, no Consilium.' },
  { id: 'seq',           name: 'consilium_sequential', tag: 'consilium', desc: 'Default mode — 3 voices in single context.' },
  { id: 'dial',          name: 'consilium_dialectic', tag: 'consilium', desc: 'Sequential + Skeptic sub-agent on chosen.' },
  { id: 'tri',           name: 'consilium_trias',    tag: 'consilium', desc: '3 personalities, each runs Sequential blind, majority vote, then one post-vote Skeptic on the winner — 4 sub-agents.' },
];

function BenchmarkSection() {
  const [activeTask, setActiveTask] = React.useState('circuit_breaker');
  const task = BENCH_TASKS.find((t) => t.id === activeTask);

  return (
    <section className="section" id="benchmark">
      <div className="container">
        <SectionHead
          num="09"
          eyebrow="Benchmark"
          title="How the modes are tested."
          lede="A local harness runs each Consilium mode against a three-task corpus via Claude Code in headless mode. Each call is fire-and-forget; grading is fully deterministic — exact-answer and keyword checks against a hidden answer key, compilation for the code task. No AI grades another AI."
        />

        <div className="tldr">
          <span className="tldr__label">In plain words</span>
          <div>
            <p>Three problems, five modes per problem, several graded tries each. Each run is sandboxed in its own workspace. The model has 15 minutes, no internet, no access to answer keys — solve from first principles or fail. Cost, correctness, and wall-clock are all recorded, and every consilium run is verified to have actually deliberated (no silent fallback to a plain answer).</p>
          </div>
        </div>

        <h3 className="h-sub" style={{ marginTop: 16, fontSize: 20 }}>Test parameters</h3>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 12,
          marginTop: 12,
          marginBottom: 28,
        }}>
          <StatCell label="Model" value="Sonnet 4.6" sub="--effort high" />
          <StatCell label="Time limit" value="15 min" sub="API duration · 10 min wall-clock cap" />
          <StatCell label="Budget" value="$3.00" sub="cap · per task" />
          <StatCell label="Isolation" value="workspace/" sub="sibling folders blocked" />
        </div>

        <h3 className="h-sub" style={{ fontSize: 20 }}>Tasks</h3>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-3)', margin: '4px 0 0' }}>The full corpus — one Code task and two Reasoning tasks. An earlier 12-task corpus was retired: Sonnet solved every task in it, so it could not discriminate between the modes.</p>
        <div className="bench-tabs" style={{ display: 'flex', gap: 6, flexWrap: 'wrap', margin: '14px 0 16px' }}>
          {BENCH_TASKS.map((t) => (
            <button
              key={t.id}
              className="mode-tab"
              data-active={t.id === activeTask}
              onClick={() => setActiveTask(t.id)}
            >
              {t.name}
              <span className="mode-tab__tag">{t.kind}</span>
            </button>
          ))}
        </div>

        <div className="mode-panel" style={{ alignItems: 'start' }}>
          <div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
              <span className="chip"><span className="chip__swatch" style={{ background: task.kind === 'Code' ? 'var(--ctl)' : 'var(--gen)' }} />{task.kind}</span>
              <span className="chip">{task.lang}</span>
              <span className="chip">{task.difficulty}</span>
            </div>
            <h4 className="mode-panel__title" style={{ marginBottom: 12 }}>{task.name}</h4>
            <p className="mode-panel__desc">{task.summary}</p>
            <dl className="mode-panel__meta" style={{ gridTemplateColumns: '1fr' }}>
              <dt>Grading</dt><dd style={{ fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.5 }}>{task.grading}</dd>
            </dl>
          </div>
          <div>
            <div style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--ink-3)',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              marginBottom: 8,
            }}>Prompt excerpt</div>
            <pre style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              lineHeight: 1.5,
              background: 'var(--paper-2)',
              border: '1px solid var(--rule)',
              padding: '14px 16px',
              margin: 0,
              borderRadius: 2,
              overflowX: 'auto',
              color: 'var(--ink-2)',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}>{task.prompt}</pre>
          </div>
        </div>

        <h3 className="h-sub" style={{ marginTop: 40, fontSize: 20 }}>Modes tested per task</h3>
        <p className="body-prose" style={{ color: 'var(--ink-2)', fontSize: 14, marginBottom: 16, maxWidth: 740 }}>
          Each task is run through five modes — two baselines without Consilium, three Consilium modes. Results are graded by the same automated verifier, and per-mode averages accumulate in <code>FEEDBACK.html</code>.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 32 }}>
          {MODES_TESTED.map((m) => (
            <div key={m.id} style={{
              padding: '16px 16px 18px',
              border: '1px solid var(--rule)',
              background: 'var(--paper)',
              borderRadius: 4,
              borderTop: `3px solid ${m.tag === 'baseline' ? 'var(--ink-3)' : 'var(--signal)'}`,
            }}>
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                color: m.tag === 'baseline' ? 'var(--ink-3)' : 'var(--signal)',
                marginBottom: 8,
              }}>{m.tag}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 500, color: 'var(--ink)', marginBottom: 8, wordBreak: 'break-word' }}>{m.name}</div>
              <div style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.5 }}>{m.desc}</div>
            </div>
          ))}
        </div>

        <h3 className="h-sub" style={{ fontSize: 20 }}>Delivery contract</h3>
        <p className="body-prose" style={{ color: 'var(--ink-2)', fontSize: 14, marginBottom: 14, maxWidth: 740 }}>
          A few rules every mode must satisfy. Violations invalidate the run before grading even starts.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
          {[
            { tag: 'WRITE', body: <>The model must call <code>Write</code> to save outputs to its assigned <code>workspace/</code>. Posting only in chat is not delivery.</> },
            { tag: 'ISOLATE', body: <>Sibling folders under <code>../</code> belong to other modes. Access is logged and flagged as a cheating event.</> },
            { tag: 'NO PEEK', body: <>No filesystem, git history, or env-var search for answer keys. A <code>cheat</code> verdict invalidates the result.</> },
            { tag: 'SELF-EST.', body: <>Reply must end with a <code>## Self-estimate</code> block — deliverable lines + reasoning use. Grader parses these; missing scores 0/10 on calibration.</> },
          ].map((r) => (
            <div key={r.tag} style={{
              padding: '16px 18px',
              border: '1px solid var(--rule)',
              background: 'var(--paper)',
              borderRadius: 4,
              display: 'grid',
              gridTemplateColumns: '88px 1fr',
              gap: 14,
              alignItems: 'start',
            }}>
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                letterSpacing: '0.1em',
                color: 'var(--signal)',
                fontWeight: 500,
              }}>{r.tag}</div>
              <div style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.55 }}>{r.body}</div>
            </div>
          ))}
        </div>

        <BenchResults />
      </div>
    </section>
  );
}

/* === Measured benchmark results (2026-06-24 snapshot, deterministic grading) === */

const BENCH_OK = 'oklch(0.55 0.14 150)';
const BENCH_BAD = 'oklch(0.55 0.19 25)';

const TRICK_RESULTS = [
  { name: 'consilium_sequential', tag: 'consilium', tries: [1, 1, 1, 1] },
  { name: 'consilium_dialectic',  tag: 'consilium', tries: [1, 1, 1, 1] },
  { name: 'consilium_trias',      tag: 'consilium', tries: [1, 1, 1, 0] },
  { name: 'superpowers',          tag: 'baseline',  tries: [0, 1, 0, 1] },
  { name: 'sonnet_bare',          tag: 'baseline',  tries: [0, 0, 0, 1] },
];

const SCORECARD = [
  { name: 'consilium_sequential', code: '✓ 60/60', trick: '✗ wrong', math: '~2.8 min' },
  { name: 'consilium_dialectic',  code: '— budget exhausted', trick: '✓ 100', math: '~5.1 min' },
  { name: 'consilium_trias',      code: '✓ 60/60', trick: '✓ 100', math: '~6.6 min' },
  { name: 'superpowers',          code: '✓ 60/60', trick: '✗ wrong', math: '~42 s' },
  { name: 'sonnet_bare',          code: '✓ 60/60', trick: '✗ wrong', math: '~38 s' },
];

const COST_ROWS = [
  { name: 'consilium_trias',      cost: 2.49, tag: 'consilium' },
  { name: 'consilium_dialectic',  cost: 2.35, tag: 'consilium' },
  { name: 'consilium_sequential', cost: 2.26, tag: 'consilium' },
  { name: 'superpowers',          cost: 0.30, tag: 'baseline' },
  { name: 'sonnet_bare',          cost: 0.30, tag: 'baseline' },
];

function BenchResults() {
  return (
    <div style={{ marginTop: 40 }}>
      <h3 className="h-sub" style={{ fontSize: 20 }}>Measured results — Consilium rows: 2026-07-08 · baseline rows: 2026-06-24 snapshot</h3>
      <p className="body-prose" style={{ color: 'var(--ink-2)', fontSize: 14, margin: '6px 0 18px', maxWidth: 760 }}>
        Two of the three tasks are at ceiling — every mode solves them — so correctness only separates the modes on the trick question, where the obvious answer is a trap. There, the same model flips from mostly-wrong to almost-always-right purely by deliberating. The price is cost and wall-clock.
      </p>

      {/* Trick question — per-try dots */}
      <h4 style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-3)', margin: '0 0 10px' }}>
        Trick question · 4 graded tries per mode
      </h4>
      <div style={{ border: '1px solid var(--rule)', borderRadius: 2, background: 'var(--paper)', overflow: 'hidden', marginBottom: 22 }}>
        {TRICK_RESULTS.map((m, i) => {
          const ok = m.tries.filter(Boolean).length;
          return (
            <div key={m.name} style={{
              display: 'grid',
              gridTemplateColumns: '190px 1fr 110px 64px',
              gap: 14,
              alignItems: 'center',
              padding: '11px 18px',
              borderBottom: i === TRICK_RESULTS.length - 1 ? 0 : '1px solid var(--rule)',
            }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, color: m.tag === 'consilium' ? 'var(--ink)' : 'var(--ink-3)' }}>{m.name}</span>
              <span style={{ display: 'flex', gap: 7 }}>
                {m.tries.map((t, j) => (
                  <span key={j} style={{
                    width: 13, height: 13, borderRadius: '50%',
                    background: t ? BENCH_OK : 'transparent',
                    border: `2px solid ${t ? BENCH_OK : BENCH_BAD}`,
                    display: 'inline-block',
                  }} />
                ))}
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: m.tag === 'consilium' ? 'var(--signal)' : 'var(--ink-3)' }}>{m.tag}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, color: ok >= 3 ? BENCH_OK : BENCH_BAD, textAlign: 'right' }}>{ok}/4</span>
            </div>
          );
        })}
      </div>

      {/* Scorecard across all three tasks */}
      <h4 style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-3)', margin: '0 0 10px' }}>
        All three tasks
      </h4>
      <div style={{ border: '1px solid var(--rule)', borderRadius: 2, background: 'var(--paper)', overflow: 'hidden', marginBottom: 8 }}>
        <div style={{
          display: 'grid', gridTemplateColumns: '190px 1fr 1fr 1fr', gap: 14,
          padding: '9px 18px', borderBottom: '1px solid var(--rule)',
          fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-3)',
        }}>
          <span>Mode</span><span>Coding task (C++)</span><span>Trick question</span><span>Math puzzle — time (all correct)</span>
        </div>
        {SCORECARD.map((m, i) => (
          <div key={m.name} style={{
            display: 'grid', gridTemplateColumns: '190px 1fr 1fr 1fr', gap: 14,
            padding: '10px 18px',
            borderBottom: i === SCORECARD.length - 1 ? 0 : '1px solid var(--rule)',
            fontFamily: 'var(--font-mono)', fontSize: 12.5,
          }}>
            <span style={{ color: 'var(--ink)' }}>{m.name}</span>
            <span style={{ color: m.code.startsWith('✓') ? BENCH_OK : 'var(--ink-3)' }}>{m.code}</span>
            <span style={{ color: m.trick.startsWith('✓') ? BENCH_OK : BENCH_BAD }}>{m.trick}</span>
            <span style={{ color: 'var(--ink-2)' }}>{m.math}</span>
          </div>
        ))}
      </div>
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-3)', margin: '0 0 22px' }}>
        ✓ = solved · ✗ = wrong answer (graded identically for every mode) · — = halted before finishing. Dialectic hit the $3/task budget cap mid-run on the coding task in the 2026-07-08 spot-check — a real cost limit, not a quality result; Trias finished the same task cleanly this time.
      </p>

      {/* Cost */}
      <h4 style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-3)', margin: '0 0 10px' }}>
        Average cost per task
      </h4>
      <div style={{ border: '1px solid var(--rule)', borderRadius: 2, background: 'var(--paper)', overflow: 'hidden', marginBottom: 8 }}>
        {COST_ROWS.map((r, i) => (
          <div key={r.name} style={{
            display: 'grid', gridTemplateColumns: '190px 1fr 70px', gap: 14, alignItems: 'center',
            padding: '11px 18px',
            borderBottom: i === COST_ROWS.length - 1 ? 0 : '1px solid var(--rule)',
          }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, color: r.tag === 'consilium' ? 'var(--ink)' : 'var(--ink-3)' }}>{r.name}</span>
            <div style={{ background: 'var(--paper-2)', height: 16, borderRadius: 2 }}>
              <div style={{
                height: '100%', width: `${(r.cost / Math.max(...COST_ROWS.map((x) => x.cost))) * 100}%`,
                background: r.tag === 'consilium' ? 'var(--signal)' : 'var(--ink-3)',
                opacity: r.tag === 'consilium' ? 1 : 0.45,
                borderRadius: 2,
              }} />
            </div>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 500, color: 'var(--ink)', textAlign: 'right' }}>${r.cost.toFixed(2)}</span>
          </div>
        ))}
      </div>
      <p className="body-prose" style={{ color: 'var(--ink-2)', fontSize: 14, margin: '0 0 22px', maxWidth: 760 }}>
        <strong>Deliberation costs ~7.5–8.3× the single-pass baselines</strong> ($2.26–$2.49 vs $0.30 per task) and takes minutes where a plain answer takes seconds. Worth it where a quick answer quietly slips; overkill on tasks the base model already solves — which is exactly why the skill defaults to the cheapest mode and a scope gate, escalating on stake rather than difficulty. (These per-task ratios compress section 07's pure dispatch multipliers — e.g. Trias ≈ 2.67× Sequential per <em>deliberation</em>: every benchmark task also carries the same task-solving work in every mode, and deliberation is the increment on top.)
      </p>

      <div className="note">
        <span className="note__label">Honest limits</span>
        <span>
          Small n — the trick-question dot matrix above is still the 2026-06-24 snapshot (4 tries per mode); the scorecard and cost rows for the three consilium modes are a fresher but single-rep (n=1) spot-check from 2026-07-08, so treat those three numbers as directional, not averaged. Baseline rows (superpowers, sonnet_bare) are unchanged from 2026-06-24. Only one task is hard enough to discriminate; the other two sit at ceiling. One model (Sonnet 4.6, high effort) throughout — the benchmark isolates the <em>process</em>, not the model. These figures are a hand-transcribed snapshot of the benchmark report — the CI drift gate (section 12) pins this page's mode invariants, not this snapshot.
        </span>
      </div>
    </div>
  );
}

function StatCell({ label, value, sub }) {
  return (
    <div style={{
      padding: '14px 16px',
      border: '1px solid var(--rule)',
      background: 'var(--paper)',
      borderRadius: 2,
    }}>
      <div style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        color: 'var(--ink-3)',
        marginBottom: 6,
      }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 500, color: 'var(--ink)' }}>{value}</div>
      {sub && <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-3)', marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function ImplementSection() {
  const ROLES = [
    {
      id: 'coder',
      name: 'Coder',
      color: 'var(--gen)',
      lane: 'implementation files',
      model: 'Sonnet 5.5',
      desc: 'Reads chosen_approach + success_criterion. Writes all implementation files. Returns a strict JSON manifest. Skipped if chosen_approach is do_nothing or skipped.',
    },
    {
      id: 'test_writer',
      name: 'Test Writer',
      color: 'var(--ctl)',
      lane: 'test_* files only',
      model: 'Sonnet 5.5',
      desc: 'Runs in parallel with Reviewer. Reads spec + files_written. Writes test_* files only. Tests must be RED against a stub and GREEN against the implementation (red→green gate).',
    },
    {
      id: 'reviewer',
      name: 'Reviewer',
      color: 'var(--con)',
      lane: 'read-only',
      model: 'Sonnet 5.5',
      desc: 'Runs in parallel with Test Writer. Inlines prompts/voices/control.md against the actual written code as a single synthetic candidate. Goal-fit → types → logic → tests → style. Writes nothing.',
    },
  ];

  const GATE_ITEMS = [
    { label: 'Status', value: 'default for regression-risk', note: 'promoted 2026-05-25 (user decision)' },
    { label: 'Cost', value: '3 sub-agents · ~1.1× tokens', note: '3–7× wall-clock (Coder, then Test Writer ∥ Reviewer)' },
    { label: 'Model', value: 'Sonnet sub-agents', note: 'Coder · Test Writer · Reviewer all on Sonnet' },
    { label: 'Routing', value: 'pipeline vs single-shot', note: 'regression-risk → pipeline; greenfield → single-shot' },
    { label: 'Promotion gate', value: '≥2/3 wins', note: 'criterion not met — promoted anyway' },
    { label: 'Signal (R1+R2)', value: 'n=6: 1 win / 5 ties / 0 losses', note: 'pipeline vs single-shot — both Sonnet 4.6 (see experiments/pipeline-bench/)' },
  ];

  return (
    <section className="section section--tinted" id="implement">
      <div className="container">
        <SectionHead
          num="11"
          eyebrow="Post-deliberation"
          title="Code integration pipeline."
          lede="After a GO verdict, a sub-agent pipeline (default for regression-risk changes) writes, tests, and reviews the chosen approach without re-deliberating. The report is the spec."
        />

        <div className="tldr">
          <span className="tldr__label">DEFAULT · REGRESSION-RISK</span>
          <div>
            <p>Default for regression-risk changes (refactor / bugfix); single-shot for greenfield. Dispatches <strong>Coder</strong> first (code must exist before tests), then <strong>Test Writer</strong> and <strong>Reviewer</strong> in parallel. A red→green gate rejects tests that pass against a stub. Returns a file manifest + Control verdict.</p>
          </div>
        </div>

        {/* Pipeline flow diagram */}
        <div style={{ margin: '28px 0', overflowX: 'auto' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 0,
            minWidth: 680,
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
          }}>
            <div style={{ padding: '14px 18px', border: '1px solid var(--rule)', borderRadius: 2, background: 'var(--paper)', textAlign: 'center', minWidth: 100 }}>
              <div style={{ fontSize: 10, color: 'var(--ink-3)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Input</div>
              <div style={{ fontWeight: 600, color: 'var(--ink)' }}>report.json</div>
              <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 2 }}>GO verdict</div>
            </div>
            <div style={{ flex: '0 0 28px', height: 1, background: 'var(--ink-3)', position: 'relative' }}>
              <span style={{ position: 'absolute', right: -2, top: -6, color: 'var(--ink-3)', fontSize: 10 }}>▶</span>
            </div>
            <div style={{ padding: '14px 18px', border: '1px solid var(--gen)', borderRadius: 2, background: 'color-mix(in oklch, var(--gen) 10%, var(--paper))', textAlign: 'center', minWidth: 90 }}>
              <div style={{ fontSize: 10, color: 'var(--gen)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Step 1</div>
              <div style={{ fontWeight: 600, color: 'var(--gen)' }}>Coder</div>
              <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 2 }}>alone first</div>
            </div>
            <div style={{ flex: '0 0 28px', height: 1, background: 'var(--ink-3)', position: 'relative' }}>
              <span style={{ position: 'absolute', right: -2, top: -6, color: 'var(--ink-3)', fontSize: 10 }}>▶</span>
            </div>
            <div style={{ border: '1px dashed var(--rule-2)', borderRadius: 2, padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 8, background: 'var(--paper)' }}>
              <div style={{ fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 2 }}>Step 2 — parallel</div>
              <div style={{ padding: '10px 14px', border: '1px solid var(--ctl)', borderRadius: 2, background: 'color-mix(in oklch, var(--ctl) 10%, var(--paper))', textAlign: 'center' }}>
                <div style={{ fontWeight: 600, color: 'var(--ctl)', fontSize: 12 }}>Test Writer</div>
                <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 2 }}>test_* only</div>
              </div>
              <div style={{ padding: '10px 14px', border: '1px solid var(--con)', borderRadius: 2, background: 'color-mix(in oklch, var(--con) 10%, var(--paper))', textAlign: 'center' }}>
                <div style={{ fontWeight: 600, color: 'var(--con)', fontSize: 12 }}>Reviewer</div>
                <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 2 }}>read-only</div>
              </div>
            </div>
            <div style={{ flex: '0 0 28px', height: 1, background: 'var(--ink-3)', position: 'relative' }}>
              <span style={{ position: 'absolute', right: -2, top: -6, color: 'var(--ink-3)', fontSize: 10 }}>▶</span>
            </div>
            <div style={{ padding: '14px 18px', border: '1px solid oklch(0.55 0.16 320)', borderRadius: 2, background: 'color-mix(in oklch, oklch(0.55 0.16 320) 10%, var(--paper))', textAlign: 'center', minWidth: 90 }}>
              <div style={{ fontSize: 10, color: 'oklch(0.55 0.16 320)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Step 3</div>
              <div style={{ fontWeight: 600, color: 'oklch(0.55 0.16 320)' }}>Gate</div>
              <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 2 }}>red→green</div>
            </div>
            <div style={{ flex: '0 0 28px', height: 1, background: 'var(--ink-3)', position: 'relative' }}>
              <span style={{ position: 'absolute', right: -2, top: -6, color: 'var(--ink-3)', fontSize: 10 }}>▶</span>
            </div>
            <div style={{ padding: '14px 18px', border: '1px solid var(--rule)', borderRadius: 2, background: 'var(--paper)', textAlign: 'center', minWidth: 100 }}>
              <div style={{ fontSize: 10, color: 'var(--ink-3)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Output</div>
              <div style={{ fontWeight: 600, color: 'var(--ink)' }}>manifest</div>
              <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 2 }}>+ Control verdict</div>
            </div>
          </div>
        </div>

        {/* Worked example */}
        <h3 className="h-sub" style={{ fontSize: 20, marginBottom: 6, marginTop: 8 }}>Worked example</h3>
        <p className="body-prose" style={{ color: 'var(--ink-2)', fontSize: 14, marginBottom: 14, maxWidth: 760 }}>
          Illustrative — a small null-guard bugfix. The deliberation's report is the <em>only</em> input; the subagent returns a strict JSON manifest of what it wrote, tested, and reviewed.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'stretch' }}>
          <div style={{ border: '1px solid var(--rule)', borderTop: '3px solid var(--ink-3)', borderRadius: 4, background: 'var(--paper)', padding: '14px 16px' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 8 }}>IN · report.json (the spec)</div>
            <pre style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: 11.5, lineHeight: 1.6, color: 'var(--ink-2)', whiteSpace: 'pre-wrap' }}>{`chosen_approach: "guard_then_divide"
success_criterion: "safe_divide(a, b)
  returns None when b == 0 instead of
  raising; normal division unchanged"
verification: "pytest tests/test_math.py"
magnitude: moderate · reversibility: irreversible
  → routes to the 3-role pipeline`}</pre>
          </div>
          <div style={{ border: '1px solid var(--rule)', borderTop: '3px solid var(--gen)', borderRadius: 4, background: 'var(--paper)', padding: '14px 16px' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 8 }}>OUT · manifest (returned)</div>
            <pre style={{ margin: 0, fontFamily: 'var(--font-mono)', fontSize: 11.5, lineHeight: 1.6, color: 'var(--ink-2)', whiteSpace: 'pre-wrap' }}>{`files_written:
  mathutils.py        → safe_divide
test_files_written:
  tests/test_math.py  → b==0 → None,
    normal division, negatives
gate:   red ✓  green ✓  passed ✓
review (Control on written code):
  implemented → valid ✓  · no issues
blocked: false`}</pre>
          </div>
        </div>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-3)', marginTop: 8, maxWidth: 820 }}>
          ↳ Coder wrote <code>mathutils.py</code> · Test Writer wrote the <code>test_*</code> file · Reviewer re-ran the Control voice on the written code · the red→green gate confirmed the tests fail against a stub and pass against the real implementation.
        </p>

        {/* Roles */}
        <h3 className="h-sub" style={{ fontSize: 20, marginBottom: 12, marginTop: 36 }}>Roles and lane rules</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 28 }}>
          {ROLES.map((r) => (
            <div key={r.id} style={{
              padding: '16px 18px',
              border: '1px solid var(--rule)',
              borderTop: `3px solid ${r.color}`,
              background: 'var(--paper)',
              borderRadius: 4,
            }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, color: r.color, marginBottom: 6 }}>{r.name}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>lane: {r.lane}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--ctl-ink)', marginBottom: 10 }}>{r.model}</div>
              <p style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.55, margin: 0 }}>{r.desc}</p>
            </div>
          ))}
        </div>

        {/* Empirical gate */}
        <h3 className="h-sub" style={{ fontSize: 20, marginBottom: 12 }}>Empirical gate</h3>
        <div style={{ border: '1px solid var(--rule)', borderRadius: 2, background: 'var(--paper)', overflow: 'hidden', marginBottom: 24 }}>
          {GATE_ITEMS.map((item, i) => (
            <div key={item.label} style={{
              display: 'grid',
              gridTemplateColumns: '160px 1fr 1fr',
              gap: 16,
              padding: '12px 18px',
              borderBottom: i === GATE_ITEMS.length - 1 ? 0 : '1px solid var(--rule)',
              alignItems: 'baseline',
            }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{item.label}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink)', fontWeight: 500 }}>{item.value}</span>
              <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>{item.note}</span>
            </div>
          ))}
        </div>

        <Collapsible label="Show optional fan-out (parallel Coders)">
          <div style={{ padding: '16px 18px', border: '1px solid var(--rule)', borderRadius: 2, background: 'var(--paper)' }}>
            <p style={{ fontSize: 13, color: 'var(--ink-2)', lineHeight: 1.6, margin: '0 0 12px' }}>
              By default one Coder writes all files. For genuinely independent files from <code>chosen_approach.files_touched[]</code>, the orchestrator may dispatch 3–5 Coders in parallel — one per file.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
              {[
                { tag: 'PRECONDITION', body: 'Target files must be mutually independent — no file defines a symbol another relies on. If unsure, use a single Coder.' },
                { tag: 'MERGE ANCHOR', body: 'Interface contract (signatures + types) must be fixed in the spec before dispatch. With independent files + pinned contract, merge = collect the files.' },
                { tag: 'AFTER COLLECT', body: 'Test Writer ∥ Reviewer run on the merged whole, exactly as in the single-Coder path.' },
                { tag: 'DEFAULT', body: 'Fan-out is a speed optimization for genuinely independent work. One Coder is always the correct default — never required.' },
              ].map((r) => (
                <div key={r.tag} style={{ padding: '12px 14px', border: '1px solid var(--rule)', borderRadius: 2, display: 'grid', gridTemplateColumns: '106px 1fr', gap: 12, alignItems: 'start' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.08em', color: 'var(--signal)', fontWeight: 500 }}>{r.tag}</span>
                  <span style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.5 }}>{r.body}</span>
                </div>
              ))}
            </div>
          </div>
        </Collapsible>
      </div>
    </section>
  );
}

/* === Green gate — the layered quality gates that keep main green === */

function GreenGateSection() {
  const CI_CHECKS = [
    {
      name: 'Unit suites',
      cmd: 'scripts/test_*.py',
      desc: 'Every test suite in scripts/ runs on every push and PR — aggregator cascade, confidence, scope gate, consent gate, Skeptic, Trias vote, implement pipeline, and more. A drift invariant fails CI if any test_*.py is missing from the gate, so a suite cannot silently fall out of coverage.',
    },
    {
      name: 'Regression scenarios',
      cmd: 'run_evals.py',
      desc: 'Deterministic subprocess scenarios from evals/scenarios.json exercise the scripts end-to-end — real CLI invocations with pinned inputs and expected outputs, not LLM evals. All scenarios run; any failure is a non-zero exit.',
    },
    {
      name: 'Doc-drift invariants',
      cmd: 'check_doc_drift.py',
      desc: 'Parses modes/*.md, scripts/confidence.py — and the JSX source of this very page — and fails if they disagree: Trias vote-confidence values, dispatch counts, cost multipliers, scale-down behavior. Those invariants cannot silently drift from the code they describe (dated measurement snapshots are outside the gate).',
    },
    {
      name: 'Explainer build sync',
      cmd: 'build.py --check',
      desc: 'The committed one-file architecture.html must byte-match a fresh build from the React source. Edit the source without rebuilding and CI goes red.',
    },
    {
      name: 'Public-leak guard',
      cmd: 'check_public_leak.py',
      desc: 'Blocks private-repo names and local filesystem paths from reaching the public tree.',
    },
    {
      name: 'Requirements gate',
      cmd: 'reqmap.py gate --strict',
      desc: 'Every requirement in requirements/ is checked against the code that claims to implement it (member-file hashes), and the published requirement map must be fresh — stale map or lock fails the gate.',
    },
    {
      name: 'Manifest & changelog gate',
      cmd: 'check_versions.py + CHANGELOG entry check',
      desc: 'plugin.json and marketplace.json semver must stay coherent, and a plugin.json version bump must ship with a matching CHANGELOG.md entry — manifests that drift apart, or a bump with no changelog note, fail CI.',
    },
    {
      name: 'Automatic release',
      cmd: 'changelog_notes.py → gh release create',
      desc: 'On a push to main that carries a plugin.json version with no release yet, CI tags vX.Y.Z and publishes a GitHub release whose notes are that version’s CHANGELOG.md section — the same reader the changelog gate uses, so every bump that passes CI has notes to publish.',
    },
  ];

  return (
    <section className="section section--tinted" id="gate">
      <div className="container">
        <SectionHead
          num="12"
          eyebrow="Quality gates"
          title="The green gate."
          lede="Nothing merges red. The CI job is literally named green-gate: a stdlib-only wall of deterministic checks that every push and pull request must pass — and the same discipline is applied per deliberation report and per written test."
        />

        <div className="tldr">
          <span className="tldr__label">In plain words</span>
          <div>
            <p>Three layers. Per <strong>report</strong>: <code>validate_report.py</code> — no deliberation lands on disk without passing the Constitution's output contract. Per <strong>implementation</strong>: the red→green test gate — a test that passes against an empty stub is rejected. Per <strong>commit</strong>: CI runs every unit suite, the regression scenarios, and drift/leak/requirements guards. Even this page is partly gated — a script parses its source and fails CI if its mode invariants (vote confidences, dispatch counts, cost multipliers) drift from the code. The dated benchmark snapshot in section 09 is transcribed by hand and sits outside that gate.</p>
          </div>
        </div>

        {/* Layer strip */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, margin: '26px 0 34px' }}>
          {[
            { tag: 'PER REPORT', name: 'validate_report.py', color: 'var(--con)', body: <>Constitution Principle #4 — schema, mode enum, confidence floors, deliberation log. The final gate before a run is written to <code>.consilium/runs/</code>.</> },
            { tag: 'PER IMPLEMENTATION', name: 'red→green gate', color: 'var(--ctl)', body: <>Step 7's Test Writer output must be RED against a <code>NotImplementedError</code> stub and GREEN against the real code — tests that don't pin behavior are rejected (section 11).</> },
            { tag: 'PER COMMIT', name: 'CI green-gate', color: 'var(--signal)', body: <>The <code>.github/workflows/ci.yml</code> job below — no pip install step by design; everything it runs is stdlib Python.</> },
          ].map((l) => (
            <div key={l.tag} style={{
              padding: '16px 18px',
              border: '1px solid var(--rule)',
              borderTop: `3px solid ${l.color}`,
              background: 'var(--paper)',
              borderRadius: 4,
            }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em', color: 'var(--ink-3)', marginBottom: 6 }}>{l.tag}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, color: l.color, marginBottom: 8 }}>{l.name}</div>
              <p style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55, margin: 0 }}>{l.body}</p>
            </div>
          ))}
        </div>

        {/* CI checks */}
        <h3 className="h-sub" style={{ fontSize: 20, marginBottom: 12 }}>What the CI green-gate runs</h3>
        <div style={{ border: '1px solid var(--rule)', borderRadius: 2, background: 'var(--paper)', overflow: 'hidden' }}>
          {CI_CHECKS.map((c, i) => (
            <div key={c.name} style={{
              display: 'grid',
              gridTemplateColumns: '170px 230px 1fr',
              gap: 16,
              padding: '13px 18px',
              borderBottom: i === CI_CHECKS.length - 1 ? 0 : '1px solid var(--rule)',
              alignItems: 'baseline',
            }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{c.name}</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--signal)', fontWeight: 500, wordBreak: 'break-word' }}>{c.cmd}</span>
              <span style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55 }}>{c.desc}</span>
            </div>
          ))}
        </div>

        <div className="note" style={{ marginTop: 24 }}>
          <span className="note__label">Why it matters</span>
          <span>
            A skill whose contract lives in prose (prompts, mode docs, an explainer page) drifts by default — someone edits the code and the story stops being true. The green gate turns that prose into checked invariants: docs, diagrams, requirements, and tests are all verified against the code on every commit, with zero external dependencies.
          </span>
        </div>
      </div>
    </section>
  );
}

Object.assign(window, { Collapsible, WhyThreeVoices, CostScatter, CostBars, BenchmarkSection, ImplementSection, GreenGateSection });
