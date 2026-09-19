import "@fontsource-variable/outfit";
import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import "./styles.css";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const coverArt = "/atlas-cover.png";

const navItems = [
  { id: "projects", label: "Projects", helper: "Library" },
  { id: "studio", label: "Studio", helper: "Working set" },
  { id: "usage", label: "Usage", helper: "Accounts" },
  { id: "settings", label: "Settings", helper: "Connections" },
];

const projects = [
  {
    title: "The Atlas of Quiet Places",
    kind: "Nonfiction",
    status: "In review",
    detail: "A short field guide to attention, place, and the spaces between tasks.",
    chapters: "6 sections",
    updated: "Saved 18 min ago",
  },
  {
    title: "Salt in the Weather",
    kind: "Fiction",
    status: "Brief ready",
    detail: "A coastal novella with a small cast and a long memory.",
    chapters: "4 sections",
    updated: "Saved yesterday",
  },
  {
    title: "Notes for a Smaller Internet",
    kind: "Essay",
    status: "Idea",
    detail: "Fragments on tools, taste, and choosing a slower default.",
    chapters: "Draft outline",
    updated: "Saved 4 days ago",
  },
];

const runCards = [
  {
    name: "Claim register",
    copy: "Facts are linked to captured sources before prose gets a final pass.",
    state: "Complete",
    tone: "done",
  },
  {
    name: "Chapter rhythm",
    copy: "The editor is checking repeated openings and uneven section weight.",
    state: "Working",
    tone: "active",
  },
  {
    name: "Owner review",
    copy: "Two notes are waiting. Nothing is merged into the accepted revision yet.",
    state: "Waiting",
    tone: "waiting",
  },
];

const reviewNotes = [
  {
    quote: "The central promise arrives early and the examples keep earning their space.",
    author: "Editorial pass",
    detail: "Coherence",
  },
  {
    quote: "The voice is clear. Let the final section land with one fewer explanation.",
    author: "Owner note",
    detail: "Revision 06",
  },
  {
    quote: "The source trail is readable and the unresolved claim is visible instead of hidden.",
    author: "Review pass",
    detail: "Evidence",
  },
];

function App() {
  const [activeView, setActiveView] = useState("studio");
  const [theme, setTheme] = useState(() => {
    if (typeof window === "undefined") return "dark";
    return window.localStorage.getItem("ebook-factory-theme") || "dark";
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("ebook-factory-theme", theme);
  }, [theme]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [activeView]);

  const activeLabel = navItems.find((item) => item.id === activeView)?.label;

  return (
    <div className="app-shell">
      <Sidebar activeView={activeView} onNavigate={setActiveView} />
      <div className="workspace">
        <Topbar
          activeLabel={activeLabel}
          theme={theme}
          onToggleTheme={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
        />
        <main id="content" className="page-content">
          {activeView === "studio" && <StudioView onNavigate={setActiveView} />}
          {activeView === "projects" && <ProjectsView onNavigate={setActiveView} />}
          {activeView === "usage" && <UsageView />}
          {activeView === "settings" && <SettingsView />}
        </main>
      </div>
    </div>
  );
}

function Sidebar({ activeView, onNavigate }) {
  return (
    <aside className="sidebar" aria-label="Primary navigation">
      <div className="brand-lockup">
        <span className="brand-mark" aria-hidden="true">
          ef
        </span>
        <span>
          <strong>Ebook Factory</strong>
          <small>Private studio</small>
        </span>
      </div>

      <nav className="primary-nav">
        <span className="nav-heading">Workspace</span>
        {navItems.map((item) => (
          <button
            className={`nav-item ${activeView === item.id ? "is-active" : ""}`}
            key={item.id}
            type="button"
            aria-current={activeView === item.id ? "page" : undefined}
            onClick={() => onNavigate(item.id)}
          >
            <span>{item.label}</span>
            <small>{item.helper}</small>
          </button>
        ))}
      </nav>

      <div className="sidebar-bottom">
        <div className="sync-note">
          <span className="status-mark" aria-hidden="true" />
          <span>
            <strong>Local workspace</strong>
            <small>Ready for a real API</small>
          </span>
        </div>
        <button className="profile-strip" type="button" onClick={() => onNavigate("settings")}>
          <span className="profile-avatar">Z</span>
          <span>
            <strong>Owner account</strong>
            <small>Personal use</small>
          </span>
          <span className="profile-arrow" aria-hidden="true">
            ↗
          </span>
        </button>
      </div>
    </aside>
  );
}

function Topbar({ activeLabel, theme, onToggleTheme }) {
  return (
    <header className="topbar">
      <div className="topbar-context">
        <span className="topbar-kicker">Ebook Factory</span>
        <span className="topbar-divider" aria-hidden="true" />
        <span>{activeLabel}</span>
      </div>
      <div className="topbar-actions">
        <span className="environment-label">Preview workspace</span>
        <button className="theme-switch" type="button" onClick={onToggleTheme}>
          <span className="theme-switch-icon" aria-hidden="true">
            {theme === "dark" ? "○" : "●"}
          </span>
          {theme === "dark" ? "Light surface" : "Night surface"}
        </button>
      </div>
    </header>
  );
}

function StudioView({ onNavigate }) {
  const pageRef = useRef(null);

  useGSAP(
    () => {
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduced) return;

      const intro = gsap.timeline({ defaults: { ease: "power3.out" } });
      intro
        .from(".hero-copy > *", { y: 34, opacity: 0, duration: 0.85, stagger: 0.1 })
        .from(".hero-image-frame", { y: 28, opacity: 0, duration: 0.8 }, "-=0.75");

      gsap.to(
        ".hero-cover",
        {
          scale: 1.04,
          opacity: 0.24,
          ease: "none",
          scrollTrigger: {
            trigger: ".hero",
            start: "top top",
            end: "bottom top",
            scrub: true,
          },
        },
      );

      gsap.utils.toArray(".reveal-block").forEach((element) => {
        gsap.fromTo(
          element,
          { y: 38, opacity: 0 },
          {
            y: 0,
            opacity: 1,
            duration: 0.8,
            ease: "power3.out",
            scrollTrigger: {
              trigger: element,
              start: "top 82%",
              once: true,
            },
          },
        );
      });
    },
    { scope: pageRef },
  );

  return (
    <div ref={pageRef} className="studio-page">
      <section className="hero" aria-labelledby="hero-title">
        <img className="hero-cover" src={coverArt} alt="Abstract cover artwork for The Atlas of Quiet Places" />
        <div className="hero-wash" aria-hidden="true" />
        <div className="hero-copy">
          <p className="eyebrow">Studio preview</p>
          <h1 id="hero-title">
            Make room for <span className="inline-cover"><img src={coverArt} alt="" /></span> the book.
          </h1>
          <p className="hero-description">
            A calm production surface for the brief, the draft, the hard questions, and the package at the end.
          </p>
          <div className="button-row">
            <button className="button button-primary" type="button" onClick={() => onNavigate("projects")}>
              Open library <span aria-hidden="true">↗</span>
            </button>
            <button className="button button-secondary" type="button" onClick={() => onNavigate("settings")}>
              New manuscript
            </button>
          </div>
        </div>
        <div className="hero-image-frame" aria-hidden="true">
          <span>Current cover study</span>
          <span>01</span>
        </div>
      </section>

      <section className="workspace-strip" aria-label="Current project summary">
        <div>
          <span className="strip-label">Current project</span>
          <strong>The Atlas of Quiet Places</strong>
        </div>
        <div>
          <span className="strip-label">Working state</span>
          <strong>Editorial review</strong>
        </div>
        <div>
          <span className="strip-label">Owner action</span>
          <strong>2 notes to resolve</strong>
        </div>
        <button className="text-link" type="button" onClick={() => onNavigate("projects")}>
          View project <span aria-hidden="true">↗</span>
        </button>
      </section>

      <BentoOverview onNavigate={onNavigate} />
      <RunStack />
      <ReviewCarousel />
      <ActionSection onNavigate={onNavigate} />
    </div>
  );
}

function BentoOverview({ onNavigate }) {
  return (
    <section className="studio-section reveal-block" aria-labelledby="overview-title">
      <div className="section-heading">
        <h2 id="overview-title">The factory has a shape.</h2>
        <p>Every decision has a home. Every accepted revision leaves a trail.</p>
      </div>

      <div className="bento-grid grid-flow-dense">
        <article className="bento-card bento-brief">
          <div className="card-topline">
            <span>Brief</span>
            <span className="card-index">01</span>
          </div>
          <div>
            <h3>Start with the promise.</h3>
            <p>Audience, tone, sources, length, and the things the book must not claim.</p>
          </div>
          <button className="card-link" type="button" onClick={() => onNavigate("projects")}>
            Open brief <span aria-hidden="true">↗</span>
          </button>
        </article>

        <article className="bento-card bento-chapters">
          <div className="card-topline">
            <span>Draft map</span>
            <span className="card-index">02</span>
          </div>
          <div className="chapter-list" aria-label="Draft map sections">
            <div className="chapter-row is-current">
              <span>01</span>
              <strong>Attention is a place</strong>
              <small>Ready</small>
            </div>
            <div className="chapter-row">
              <span>02</span>
              <strong>What the room keeps</strong>
              <small>Review</small>
            </div>
            <div className="chapter-row">
              <span>03</span>
              <strong>The useful distance</strong>
              <small>Draft</small>
            </div>
          </div>
          <button className="card-link" type="button" onClick={() => onNavigate("projects")}>
            Browse sections <span aria-hidden="true">↗</span>
          </button>
        </article>

        <article className="bento-card bento-review">
          <img src={coverArt} alt="The Atlas of Quiet Places cover study" />
          <div className="image-card-wash" aria-hidden="true" />
          <div className="image-card-copy">
            <span className="card-topline">Review room <span className="card-index">03</span></span>
            <h3>Keep the useful friction.</h3>
            <p>Notes stay attached to the revision they changed.</p>
          </div>
        </article>

        <article className="bento-card bento-package">
          <div className="card-topline">
            <span>Package</span>
            <span className="card-index">04</span>
          </div>
          <div className="package-mark" aria-hidden="true">EPUB</div>
          <div>
            <h3>One source. Many formats.</h3>
            <p>EPUB, PDF, DOCX, and Markdown wait behind the accepted revision.</p>
          </div>
          <button className="card-link" type="button" onClick={() => onNavigate("usage")}>
            Inspect package <span aria-hidden="true">↗</span>
          </button>
        </article>
      </div>
    </section>
  );
}

function RunStack() {
  const stackRef = useRef(null);

  useGSAP(
    () => {
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduced) return;

      const cards = gsap.utils.toArray(".run-card", stackRef.current);
      cards.forEach((card, index) => {
        if (index === cards.length - 1) return;
        ScrollTrigger.create({
          trigger: card,
          start: "top top",
          endTrigger: cards[cards.length - 1],
          end: "top top",
          pin: true,
          pinSpacing: false,
        });
        gsap.to(card, {
          scale: 0.94,
          opacity: 0.5,
          ease: "none",
          scrollTrigger: {
            trigger: cards[index + 1],
            start: "top bottom",
            end: "top top",
            scrub: true,
          },
        });
      });
    },
    { scope: stackRef },
  );

  return (
    <section className="run-section" aria-labelledby="run-title">
      <div className="run-grid">
        <div className="run-intro">
          <p className="eyebrow">Production run</p>
          <h2 id="run-title">No fog between idea and page.</h2>
          <p>Progress is a set of accepted checkpoints, not a percentage guessed by an agent.</p>
          <div className="run-stat">
            <span className="status-mark" aria-hidden="true" />
            <span><strong>Run 04</strong><small>Working from brief revision 06</small></span>
          </div>
        </div>
        <div ref={stackRef} className="run-stack" aria-label="Production checkpoints">
          {runCards.map((card, index) => (
            <article className={`run-card run-card-${card.tone}`} key={card.name}>
              <div className="run-card-header">
                <span className="run-number">0{index + 1}</span>
                <span className="run-state">{card.state}</span>
              </div>
              <h3>{card.name}</h3>
              <p>{card.copy}</p>
              <div className="run-card-footer">
                <span>{index === 0 ? "Revision 06" : index === 1 ? "Checkpoint 03" : "Owner decision"}</span>
                <span aria-hidden="true">↗</span>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function ReviewCarousel() {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeNote = reviewNotes[activeIndex];

  const move = (direction) => {
    setActiveIndex((current) => (current + direction + reviewNotes.length) % reviewNotes.length);
  };

  return (
    <section className="review-section reveal-block" aria-labelledby="review-title">
      <div className="review-heading">
        <h2 id="review-title">Notes that change the book.</h2>
        <p>Editorial feedback is small enough to read and specific enough to act on.</p>
      </div>
      <div className="review-stage">
        <div className="review-cover-stack" aria-hidden="true">
          <img src={coverArt} alt="" />
          <span>Revision 06</span>
        </div>
        <div className="review-note" role="region" aria-live="polite" aria-atomic="true" aria-label="Current review note">
          <span className="review-note-detail">{activeNote.detail}</span>
          <blockquote>“{activeNote.quote}”</blockquote>
          <div className="review-note-footer">
            <strong>{activeNote.author}</strong>
            <div className="review-controls">
              <button type="button" onClick={() => move(-1)} aria-label="Previous review note">←</button>
              <span>{String(activeIndex + 1).padStart(2, "0")} / {String(reviewNotes.length).padStart(2, "0")}</span>
              <button type="button" onClick={() => move(1)} aria-label="Next review note">→</button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function ActionSection({ onNavigate }) {
  return (
    <section className="action-section reveal-block" aria-labelledby="action-title">
      <div>
        <h2 id="action-title">Give the next idea a proper room.</h2>
      </div>
      <div className="action-side">
        <p>Start with a brief. Keep every accepted choice. Leave the upload to you.</p>
        <button className="button button-primary" type="button" onClick={() => onNavigate("settings")}>
          Create a brief <span aria-hidden="true">↗</span>
        </button>
      </div>
    </section>
  );
}

function ProjectsView({ onNavigate }) {
  const [openProject, setOpenProject] = useState(0);

  return (
    <section className="view-page" aria-labelledby="projects-title">
      <div className="page-intro">
        <div>
          <p className="eyebrow">Library</p>
          <h1 id="projects-title">Projects with a pulse.</h1>
          <p>Drafts, briefs, and accepted revisions in one quiet shelf.</p>
        </div>
        <button className="button button-primary" type="button" onClick={() => onNavigate("settings")}>
          New manuscript <span aria-hidden="true">↗</span>
        </button>
      </div>

      <div className="project-accordion" aria-label="Project library">
        {projects.map((project, index) => {
          const isOpen = openProject === index;
          const toggleId = `project-toggle-${index}`;
          const detailsId = `project-details-${index}`;
          return (
            <article className={`project-row ${isOpen ? "is-open" : ""}`} key={project.title}>
              <button
                className="project-toggle"
                id={toggleId}
                type="button"
                onClick={() => setOpenProject(isOpen ? -1 : index)}
                aria-expanded={isOpen}
                aria-controls={detailsId}
              >
                <span className="project-index">0{index + 1}</span>
                <span className="project-main">
                  <strong>{project.title}</strong>
                  <small>{project.kind}</small>
                </span>
                <span className="project-status">{project.status}</span>
                <span className="project-chevron" aria-hidden="true">{isOpen ? "−" : "+"}</span>
              </button>
              {isOpen && (
                <div className="project-details" id={detailsId} role="region" aria-labelledby={toggleId}>
                  <p>{project.detail}</p>
                  <div className="project-detail-meta">
                    <span>{project.chapters}</span>
                    <span>{project.updated}</span>
                  </div>
                  <button className="text-link" type="button" onClick={() => onNavigate("studio")}>
                    Open in studio <span aria-hidden="true">↗</span>
                  </button>
                </div>
              )}
            </article>
          );
        })}
      </div>

      <div className="empty-shelf">
        <div className="empty-shelf-mark" aria-hidden="true">+</div>
        <div>
          <strong>The shelf is intentionally small.</strong>
          <p>When the next idea arrives, give it a brief before you give it a title.</p>
        </div>
      </div>
    </section>
  );
}

function UsageView() {
  const calls = [
    { purpose: "Orchestration", provider: "Pi account", result: "Observed", value: "Usage captured" },
    { purpose: "Editorial review", provider: "Custom endpoint", result: "Pending", value: "Connection test required" },
    { purpose: "Image route", provider: "Codex subscription", result: "Unknown", value: "Capability spike pending" },
  ];

  return (
    <section className="view-page" aria-labelledby="usage-title">
      <div className="page-intro">
        <div>
          <p className="eyebrow">Usage</p>
          <h1 id="usage-title">Know what the run knows.</h1>
          <p>Observed calls, provider state, and unknowns kept separate on purpose.</p>
        </div>
        <div className="unknown-badge">Billing status: unknown</div>
      </div>

      <div className="usage-overview">
        <article className="usage-lead">
          <span className="usage-label">Current run</span>
          <strong>Run 04</strong>
          <p>Three bounded calls recorded against the sample workspace.</p>
          <span className="usage-footnote">Currency totals are unavailable until a real provider reports them.</span>
        </article>
        <article className="usage-side-stat">
          <span className="usage-label">Account state</span>
          <strong>1 connected</strong>
          <p>Pi account is available to the trusted host adapter.</p>
        </article>
        <article className="usage-side-stat">
          <span className="usage-label">Quota surface</span>
          <strong>Not checked</strong>
          <p>Unknown is a state, not a zero.</p>
        </article>
      </div>

      <div className="ledger-panel">
        <div className="panel-heading">
          <div>
            <h2>Call ledger</h2>
            <p>A small list is easier to audit than a decorative chart.</p>
          </div>
          <span className="panel-count">03 records</span>
        </div>
        <div className="ledger-list">
          {calls.map((call) => (
            <div className="ledger-row" key={call.purpose}>
              <div><strong>{call.purpose}</strong><small>{call.provider}</small></div>
              <span className={`ledger-state ledger-${call.result.toLowerCase()}`}>{call.result}</span>
              <span>{call.value}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function SettingsView() {
  const [saved, setSaved] = useState(false);

  const submit = (event) => {
    event.preventDefault();
    setSaved(true);
  };

  return (
    <section className="view-page" aria-labelledby="settings-title">
      <div className="page-intro">
        <div>
          <p className="eyebrow">Settings</p>
          <h1 id="settings-title">Keep the boundaries visible.</h1>
          <p>Provider connections, Telegram status, and the safe defaults for a personal factory.</p>
        </div>
        {saved && <div className="save-confirmation" role="status">Local draft saved</div>}
      </div>

      <div className="settings-grid">
        <form className="settings-form" onSubmit={submit}>
          <div className="panel-heading">
            <div>
              <h2>Provider adapter</h2>
              <p>These fields are local placeholders until the API is wired.</p>
            </div>
            <span className="connection-state">Draft</span>
          </div>
          <label>
            Provider name
            <input name="provider" defaultValue="Pi account" />
          </label>
          <label>
            Custom endpoint
            <input name="endpoint" placeholder="https://your-local-endpoint" />
            <small>Credentials never belong in this workspace preview.</small>
          </label>
          <label>
            Default profile
            <select name="profile" defaultValue="nonfiction">
              <option value="nonfiction">Nonfiction</option>
              <option value="fiction">Fiction</option>
              <option value="custom">Custom brief</option>
            </select>
          </label>
          <button className="button button-primary" type="submit">Save local draft</button>
        </form>

        <div className="settings-side">
          <article className="integration-card">
            <div className="panel-heading">
              <div>
                <h2>Telegram</h2>
                <p>Same conversation, second doorway.</p>
              </div>
              <span className="connection-state muted">Not configured</span>
            </div>
            <div className="integration-empty">
              <strong>No chat is linked.</strong>
              <p>Add the owner-approved token and chat IDs when the live adapter is ready.</p>
              <button className="text-link" type="button" onClick={() => setSaved(true)}>Mark for setup <span aria-hidden="true">↗</span></button>
            </div>
          </article>
          <article className="integration-card">
            <div className="panel-heading">
              <div>
                <h2>Execution boundary</h2>
                <p>The host owns the sandbox. The job gets the minimum surface.</p>
              </div>
              <span className="connection-state">Planned</span>
            </div>
            <ul className="boundary-list">
              <li>Private job storage</li>
              <li>No home or DB credential mount</li>
              <li>Fenced artifact publication</li>
            </ul>
          </article>
        </div>
      </div>
    </section>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
