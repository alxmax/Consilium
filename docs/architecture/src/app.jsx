/* app.jsx — top-level layout (v2, with side nav + progress) */

const DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "light",
  "density": "comfortable"
}/*EDITMODE-END*/;

const SECTIONS = [
  { id: 'problem',      num: '01', name: 'Premise' },
  { id: 'voices',       num: '02', name: 'Voices' },
  { id: 'architecture', num: '03', name: 'Layers' },
  { id: 'pipeline',     num: '04', name: 'Pipeline' },
  { id: 'cascade',      num: '05', name: 'Cascade' },
  { id: 'voting',       num: '06', name: 'Aggregation' },
  { id: 'modes',        num: '07', name: 'Modes' },
  { id: 'trias',        num: '08', name: 'Trias' },
  { id: 'benchmark',    num: '09', name: 'Benchmark' },
  { id: 'loop',         num: '10', name: 'Calibration' },
  { id: 'implement',    num: '11', name: 'Integration' },
  { id: 'gate',         num: '12', name: 'Green gate' },
  { id: 'efficiency',   num: '13', name: 'Efficiency' },
];

function App() {
  const [t, setTweak] = useTweaks(DEFAULTS);

  React.useEffect(() => {
    document.documentElement.setAttribute('data-theme', t.theme);
    document.documentElement.setAttribute('data-density', t.density);
  }, [t.theme, t.density]);

  return (
    <div className="page">
      <ScrollProgress />
      <Topbar />
      <MobileNav />
      <SideNav />
      <Hero />
      <ProblemSection />
      <VoicesSection />
      <TwoLayerSection />
      <PipelineSection />
      <CascadeSection />
      <VotingSection />
      <ModesSection />
      <TriasSection />
      <BenchmarkSection />
      <LoopSection />
      <ImplementSection />
      <GreenGateSection />
      <EfficiencySection />
      <Footer />
      <Tweaks t={t} setTweak={setTweak} />
    </div>
  );
}

function useActiveSection() {
  const [active, setActive] = React.useState(SECTIONS[0].id);
  React.useEffect(() => {
    const onScroll = () => {
      const middle = window.scrollY + window.innerHeight * 0.35;
      let current = SECTIONS[0].id;
      for (const s of SECTIONS) {
        const el = document.getElementById(s.id);
        if (el && el.offsetTop <= middle) current = s.id;
      }
      setActive(current);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  return active;
}

function ScrollProgress() {
  const [pct, setPct] = React.useState(0);
  React.useEffect(() => {
    const onScroll = () => {
      const docH = document.documentElement.scrollHeight - window.innerHeight;
      const p = docH > 0 ? (window.scrollY / docH) * 100 : 0;
      setPct(Math.max(0, Math.min(100, p)));
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  return <div className="scroll-progress" style={{ width: `${pct}%` }} aria-hidden="true" />;
}

function SideNav() {
  const active = useActiveSection();
  const handleJump = (id) => {
    const el = document.getElementById(id);
    if (el) {
      const top = el.getBoundingClientRect().top + window.scrollY - 80;
      window.scrollTo({ top, behavior: 'smooth' });
    }
  };
  return (
    <nav className="side-nav" aria-label="Section navigation">
      <div className="side-nav__label">contents</div>
      <ul className="side-nav__list">
        {SECTIONS.map((s) => (
          <li key={s.id} className="side-nav__item">
            <button
              className="side-nav__link"
              data-active={s.id === active}
              onClick={() => handleJump(s.id)}
            >
              <span className="side-nav__num">{s.num}</span>
              <span>{s.name}</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function MobileNav() {
  const active = useActiveSection();
  return (
    <nav className="mobile-nav" aria-label="Section navigation">
      {SECTIONS.map((s) => (
        <a key={s.id} href={`#${s.id}`} className="mobile-nav__link" data-active={s.id === active}>
          <span className="mobile-nav__num">{s.num}</span>
          {s.name}
        </a>
      ))}
    </nav>
  );
}

function Topbar() {
  return (
    <div className="topbar">
      <div className="topbar__brand">
        <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
          <circle cx="7" cy="8" r="3.2" fill="var(--gen)" />
          <circle cx="15" cy="8" r="3.2" fill="var(--ctl)" />
          <circle cx="11" cy="15" r="3.2" fill="var(--con)" />
        </svg>
        consilium
      </div>
      <div className="topbar__actions">
        <a
          className="topbar__repo"
          href="requirements-map.html"
          target="_blank"
          rel="noopener noreferrer"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" style={{ flexShrink: 0 }}>
            <path
              fill="currentColor"
              d="M3 1a1 1 0 00-1 1v12a1 1 0 001 1h10a1 1 0 001-1V2a1 1 0 00-1-1H3zm1 3h8v1H4V4zm0 3h8v1H4V7zm0 3h5v1H4v-1z"
            />
          </svg>
          <span>Requirements</span>
          <span style={{ opacity: 0.5, marginLeft: 'auto' }}>↗</span>
        </a>
        <a
          className="topbar__repo"
          href="consilium_full.html"
          target="_blank"
          rel="noopener noreferrer"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" style={{ flexShrink: 0 }}>
            <path
              fill="currentColor"
              d="M1 1h6v6H1V1zm0 8h6v6H1V9zm8-8h6v6H9V1zm0 8h6v6H9V9z"
            />
          </svg>
          <span>Full diagram</span>
          <span style={{ opacity: 0.5, marginLeft: 'auto' }}>↗</span>
        </a>
        <a
          className="topbar__repo"
          href="https://github.com/alxmax/Consilium"
          target="_blank"
          rel="noopener noreferrer"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" style={{ flexShrink: 0 }}>
            <path
              fill="currentColor"
              d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
            />
          </svg>
          <span>View repository</span>
          <span style={{ opacity: 0.5, marginLeft: 'auto' }}>↗</span>
        </a>
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="hero">
      <div className="container">
        <div className="hero__meta">
          <span className="hero__dot" />
          <span>CLAUDE CODE SKILL</span>
          <span style={{ opacity: 0.4 }}>·</span>
          <span>2026</span>
        </div>
        <h1 className="h-display">
          A second opinion,
          <br />
          structured.
        </h1>
        <p className="hero__lede">
          Before a risky code change ships, Consilium gets three independent reviewers to weigh in — one hunts for what could break, one proposes bold fixes, one checks it actually works. Their opinions are combined into a single decision, and the disagreement is kept on the record.
        </p>
        <div className="hero__chips">
          <span className="chip"><span className="chip__swatch" style={{ background: 'var(--con)' }} />Conservator</span>
          <span className="chip"><span className="chip__swatch" style={{ background: 'var(--gen)' }} />Generator</span>
          <span className="chip"><span className="chip__swatch" style={{ background: 'var(--ctl)' }} />Control</span>
          <span className="chip"><span className="chip__swatch" style={{ background: 'oklch(0.55 0.16 320)' }} />Skeptic</span>
          <span className="chip">3 review modes + 1 flag + 1 auto</span>
          <span className="chip">3 ways to combine the scores</span>
          <span className="chip">8-step decision cascade</span>
          <span className="chip">learns from past runs</span>
        </div>
      </div>
    </section>
  );
}

function ProblemSection() {
  return (
    <section className="section section--inked" id="problem">
      <div className="container">
        <div className="divider-num" style={{ color: 'var(--ink-3)' }}>
          <span className="divider-num__id">01</span> <span>·</span> The premise
        </div>
        <h2 className="h-section" style={{ maxWidth: 840 }}>
          One agent's verdict on a risky change is one agent's verdict.
        </h2>
        <p className="lede" style={{ color: 'var(--paper-3)' }}>
          Ask one AI to review a risky change and you get one opinion: confident, but unchecked. For changes where a mistake is expensive — touching the database, security, or code the whole project depends on — you want it pulled apart by separate reviewers working in a relay, each unaware of the others' reasoning, so no single judgment goes unchecked.
        </p>
        <p className="lede" style={{ color: 'var(--paper-3)', maxWidth: 720 }}>
          Consilium is that structure, automated. It runs as a single command inside Claude Code, and every decision — with the reasons behind it — is saved, so the next review starts smarter than the last.
        </p>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="footer">
      <div className="container">
        <div className="footer__row">
          <span>Consilium · multi-perspective deliberation for Claude Code</span>
          <span>v2 architecture · explainer</span>
        </div>
      </div>
    </footer>
  );
}

function Tweaks({ t, setTweak }) {
  return (
    <TweaksPanel title="Tweaks">
      <TweakSection label="Appearance" />
      <TweakRadio
        label="Theme"
        value={t.theme}
        options={[{ value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }]}
        onChange={(v) => setTweak('theme', v)}
      />
      <TweakRadio
        label="Density"
        value={t.density}
        options={[{ value: 'comfortable', label: 'Comfy' }, { value: 'compact', label: 'Compact' }]}
        onChange={(v) => setTweak('density', v)}
      />
    </TweaksPanel>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
