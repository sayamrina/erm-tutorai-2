import { useEffect, useRef, useState } from "react";
import {
  getHealth, getUnits, newPracticeQuestion, stream,
  type Health, type Label, type Passage, type PracticeQuestion, type StreamEvent, type Unit, type Verdict,
} from "./api";
import ResearchNotes from "./Notes";
import { RichText, splitFollowUp, toMarkdown } from "./text";

type Entry = {
  id: number;
  role: "student" | "tutor";
  text: string;
  passages?: Passage[];
  cited?: number[];
  label?: Label;
  words?: number;
  verdict?: Verdict | null;
  streaming?: boolean;
  error?: string;
};

const STARTERS: Record<number, string> = {
  1: "What is the ERM1 course about and how is it structured?",
  2: "What are the quality criteria of a scientific text?",
  3: "What is the difference between an alpha and a beta error?",
  4: "Why use a standardized questionnaire instead of writing my own items?",
  5: "What is the difference between Data View and Variable View in SPSS?",
  6: "What does a p-value of .03 actually tell me?",
  7: "When do I use a t-test and when an ANOVA?",
  8: "What are the assumptions of the linear model in regression?",
  9: "Why run a MANOVA instead of several ANOVAs?",
  10: "What is sphericity and why does it matter?",
  11: "When should I use a non-parametric test?",
  12: "What kinds of bias can affect a study?",
};

const LABELS: Record<Label, string> = {
  course: "From the course materials",
  general: "From general research-methods knowledge, not the course materials",
  declined: "",
  demo: "Demo mode: matching passages only",
};

const VERDICT_TEXT: Record<Verdict, string> = {
  correct: "Correct", "partly correct": "Partly correct", "not yet": "Not there yet",
};

let nextId = 1;

/** Slide text keeps the PDF's line breaks; join wrapped lines, keep paragraphs and bullets. */
const readable = (text: string) => text.replace(/([^\n])\n(?![\n•])/g, "$1 ");

function sourceLine(p: Passage, n: number) {
  return `[${n}] Unit ${p.unit}, ${p.unit_title}, page ${p.page}${p.section ? ` (${p.section})` : ""}`;
}

/** Twelve ticks for the twelve lecture units: which parts of the course an answer drew on. */
function SyllabusRug({ entry, units, hover }: { entry: Entry; units: Unit[]; hover: number | null }) {
  const passages = entry.passages ?? [];
  const cited = new Set((entry.cited ?? []).map((n) => passages[n - 1]?.unit));
  const retrieved = new Set(passages.map((p) => p.unit));
  const hovered = hover ? passages[hover - 1]?.unit : undefined;
  const citedList = [...cited].filter(Boolean).sort((a, b) => a! - b!);
  return (
    <div className="rug" role="img"
      aria-label={citedList.length ? `Based on unit ${citedList.join(", ")} of 12` : "No course unit cited"}>
      <div className="rug-ticks">
        {units.map((u) => {
          const state = cited.has(u.unit) ? "cited" : retrieved.has(u.unit) ? "retrieved" : "";
          return <span key={u.unit} className={`tick ${state} ${hovered === u.unit ? "hover" : ""}`} title={`Unit ${u.unit}: ${u.title}`} />;
        })}
      </div>
      <span className="rug-label">
        {citedList.length ? `${citedList.length > 1 ? "Units" : "Unit"} ${citedList.join(", ")} of 12` : "No unit cited"}
      </span>
    </div>
  );
}

function TutorEntry({ entry, units, onCite, onReply }: {
  entry: Entry; units: Unit[]; onCite: (entry: Entry, n: number) => void; onReply: (q: string) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const available = entry.passages?.length ?? 0;
  const { body, followUp } = entry.streaming || entry.verdict !== undefined
    ? { body: entry.text, followUp: null } : splitFollowUp(entry.text);
  const cite = { available, onCite: (n: number) => onCite(entry, n), onHover: setHover };
  return (
    <div className="entry tutor">
      {entry.verdict === null && <p className="practice-label">Practice question</p>}
      {entry.verdict && <p className={`verdict v-${entry.verdict.replace(" ", "-")}`}>{VERDICT_TEXT[entry.verdict]}</p>}
      <div className="answer" aria-live={entry.streaming ? "polite" : undefined}>
        {entry.text ? <RichText text={body} {...cite} /> : !entry.error && <p className="thinking">Reading the lecture slides</p>}
        {followUp && (
          <div className="follow-up">
            <RichText text={followUp} {...cite} />
            <button type="button" className="link-button" onClick={() => onReply(followUp)}>Answer this question</button>
          </div>
        )}
        {entry.error && <p className="error" role="alert">{entry.error}</p>}
      </div>
      {!entry.streaming && entry.label !== "declined" && entry.passages && (
        <footer className="entry-meta">
          <SyllabusRug entry={entry} units={units} hover={hover} />
          <span className={`origin o-${entry.label ?? "course"}`}>{entry.label ? LABELS[entry.label] : ""}</span>
          {entry.words ? <span className="words">{entry.words} words</span> : null}
          {available > 0 && (
            <button type="button" className="link-button" onClick={() => onCite(entry, entry.cited?.[0] ?? 1)}>
              {entry.cited?.length ? `Open ${entry.cited.length === 1 ? "source" : `${entry.cited.length} sources`}` : "Show retrieved passages"}
            </button>
          )}
        </footer>
      )}
    </div>
  );
}

function SourcePanel({ entry, active, onSelect }: { entry: Entry | null; active: number; onSelect: (n: number) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.querySelector(".passage.active")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [entry, active]);
  if (!entry?.passages?.length) {
    return (
      <div className="panel-empty">
        <p>Select a number in an answer to read the slide it comes from.</p>
      </div>
    );
  }
  const cited = new Set(entry.cited ?? []);
  return (
    <div className="passages" ref={ref}>
      <p className="panel-intro">
        The tutor read these {entry.passages.length} passages before answering.
        {cited.size ? ` It cited ${cited.size}.` : " It cited none of them."}
      </p>
      {entry.passages.map((p, i) => {
        const n = i + 1;
        return (
          <section key={p.id} className={`passage ${n === active ? "active" : ""} ${cited.has(n) ? "" : "uncited"}`}
            onClick={() => onSelect(n)}>
            <header>
              <span className="num">{n}</span>
              <div>
                <h4>Unit {p.unit}: {p.unit_title}</h4>
                <p>Page {p.page}{p.section ? `, ${p.section}` : ""}{cited.has(n) ? "" : ". Not cited"}</p>
              </div>
            </header>
            <blockquote>{readable(p.text)}</blockquote>
          </section>
        );
      })}
    </div>
  );
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [units, setUnits] = useState<Unit[]>([]);
  const [mode, setMode] = useState<"ask" | "practice">("ask");
  const [unit, setUnit] = useState<number | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [panel, setPanel] = useState<"sources" | "notes">("notes");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [selected, setSelected] = useState<{ id: number; n: number } | null>(null);
  const [practice, setPractice] = useState<PracticeQuestion | null>(null);
  const [practiceLog, setPracticeLog] = useState<Entry[]>([]);
  const [notice, setNotice] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setNotice("The tutor service is not reachable. Reload the page in a moment."));
    getUnits().then(setUnits).catch(() => undefined);
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [entries.length, practiceLog.length]);

  const demo = health?.mode === "demo";
  const unitTitle = unit ? units.find((u) => u.unit === unit)?.title : null;
  const log = mode === "ask" ? entries : practiceLog;
  const setLog = mode === "ask" ? setEntries : setPracticeLog;
  const selectedEntry = selected ? [...entries, ...practiceLog].find((e) => e.id === selected.id) ?? null : null;

  function patch(id: number, update: (e: Entry) => Entry) {
    setLog((list) => list.map((e) => (e.id === id ? update(e) : e)));
  }

  async function run(path: string, body: unknown, studentText: string) {
    const tutorId = nextId++;
    setLog((list) => [...list, { id: nextId++, role: "student", text: studentText }, { id: tutorId, role: "tutor", text: "", streaming: true }]);
    setBusy(true);
    try {
      await stream(path, body, (ev: StreamEvent) => {
        if (ev.type === "sources") patch(tutorId, (e) => ({ ...e, passages: ev.passages }));
        else if (ev.type === "token") patch(tutorId, (e) => ({ ...e, text: e.text + ev.text }));
        else if (ev.type === "verdict") patch(tutorId, (e) => ({ ...e, verdict: ev.verdict }));
        else if (ev.type === "done") patch(tutorId, (e) => ({ ...e, streaming: false, cited: ev.cited, label: ev.label, words: ev.words }));
        else if (ev.type === "error") patch(tutorId, (e) => ({ ...e, streaming: false, error: ev.message }));
      });
    } catch (err) {
      patch(tutorId, (e) => ({ ...e, streaming: false, error: (err as Error).message }));
    } finally {
      setBusy(false);
    }
  }

  function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setInput("");
    const history = entries.filter((e) => e.text && !e.error).slice(-4)
      .map((e) => ({ role: e.role === "student" ? "user" : "assistant", content: e.text }));
    run("/api/ask", { question: q, unit, history }, q);
  }

  async function startPractice() {
    if (!unit || busy) return;
    setBusy(true);
    setNotice("");
    try {
      const q = await newPracticeQuestion(unit);
      setPractice(q);
      setPracticeLog((list) => [...list, { id: nextId++, role: "tutor", text: q.question, verdict: null }]);
      inputRef.current?.focus();
    } catch (err) {
      setNotice((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function checkAnswer(answer: string) {
    const a = answer.trim();
    if (!practice || !a || busy) return;
    setInput("");
    run("/api/practice/feedback", { ...practice, answer: a }, a).then(() => setPractice(null));
  }

  function submit() {
    if (mode === "ask") ask(input);
    else checkAnswer(input);
  }

  function openSource(entry: Entry, n: number) {
    setSelected({ id: entry.id, n });
    setPanel("sources");
    setSheetOpen(true);
  }

  function reply(followUp: string) {
    setInput("");
    inputRef.current?.focus();
    inputRef.current?.setAttribute("placeholder", `Reply to: ${followUp}`);
  }

  function save() {
    const md = toMarkdown(entries.filter((e) => e.text).map((e) => ({
      role: e.role === "student" ? "You" : "Tutor",
      text: e.text,
      sources: (e.cited ?? []).map((n) => e.passages?.[n - 1] && sourceLine(e.passages[n - 1], n)).filter(Boolean) as string[],
    })));
    const url = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "erm-tutor-conversation.md" });
    a.click();
    URL.revokeObjectURL(url);
  }

  function switchMode(next: "ask" | "practice") {
    setMode(next);
    setNotice("");
    if (next === "practice" && !unit) setUnit(7);
  }

  const placeholder = mode === "ask"
    ? (unitTitle ? `Ask about ${unitTitle}` : "Ask about anything in the course")
    : practice ? "Write your answer in a few sentences" : "Pick a unit and get a question first";

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="/" aria-label="ERM Tutor-AI, start page">
          <img src="/logo.png" alt="" width={34} height={34} />
          <span className="brand-text">
            <span>ERM Tutor-AI <small>2</small></span>
            <em>Virtual assistant for the Empirical Research Methods course</em>
          </span>
        </a>
        <nav className="modes" aria-label="Mode">
          <button type="button" aria-pressed={mode === "ask"} onClick={() => switchMode("ask")}>Ask</button>
          <button type="button" aria-pressed={mode === "practice"} onClick={() => switchMode("practice")}>Practice</button>
        </nav>
        <div className="top-actions">
          <button type="button" className="ghost" onClick={save} disabled={!entries.some((e) => e.text)}>Save chat</button>
          <button type="button" className="ghost notes-toggle" onClick={() => { setPanel("notes"); setSheetOpen(true); }}>Research notes</button>
        </div>
      </header>

      <aside className="project-popup" aria-label="Portfolio project">
        <span className="project-popup-badge" aria-hidden="true">★</span>
        <span>This app was developed as part of Amrina's master's thesis.</span>
        <a href="https://sayamrina.github.io/" target="_blank" rel="noopener">View the portfolio →</a>
      </aside>

      <div className="layout">
        <nav className="syllabus" aria-label="Course units">
          <h2>Lecture units</h2>
          <label className="unit-select">
            <span>Unit</span>
            <select value={unit ?? ""} onChange={(e) => setUnit(e.target.value ? Number(e.target.value) : null)}>
              {mode === "ask" && <option value="">All units</option>}
              {units.map((u) => <option key={u.unit} value={u.unit}>{u.unit}. {u.title}</option>)}
            </select>
          </label>
          <ol>
            {mode === "ask" && (
              <li className="all">
                <button type="button" aria-current={unit === null} onClick={() => setUnit(null)}>All units</button>
              </li>
            )}
            {units.map((u) => (
              <li key={u.unit}>
                <button type="button" aria-current={unit === u.unit} onClick={() => setUnit(u.unit)}>
                  <span className="n">{u.unit}</span><span>{u.title}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>

        <main className="conversation">
          {demo && (
            <p className="demo-note">
              Demo mode: no language model is connected, so you see the matching lecture passages instead of tutor answers.
            </p>
          )}
          {notice && <p className="error" role="alert">{notice}</p>}

          {log.length === 0 && mode === "ask" && (
            <section className="empty">
              <h1>Ask about anything in Empirical Research Methods.</h1>
              <p>Answers come from the twelve lecture units, and every claim points to the slide it is based on.</p>
              <div className="starters">
                {(unit ? [unit] : [7, 6, 10]).map((u) => (
                  <button key={u} type="button" onClick={() => ask(STARTERS[u])}>{STARTERS[u]}</button>
                ))}
              </div>
            </section>
          )}

          {log.length === 0 && mode === "practice" && (
            <section className="empty">
              <h1>Test yourself on one unit.</h1>
              <p>The tutor writes a question from a lecture slide, you answer in your own words, and the feedback shows the slides to review.</p>
            </section>
          )}

          <div className="log">
            {log.map((e) => e.role === "student"
              ? <div key={e.id} className="entry student"><p>{e.text}</p></div>
              : <TutorEntry key={e.id} entry={e} units={units} onCite={openSource} onReply={reply} />)}
            <div ref={endRef} />
          </div>

          {mode === "practice" && !practice && (
            <div className="practice-bar">
              <button type="button" className="primary" onClick={startPractice} disabled={busy || demo || !unit}>
                {practiceLog.length ? "Next question" : "Get a question"}{unitTitle ? ` on ${unitTitle}` : ""}
              </button>
              {demo && <span className="muted">Practice needs the language model.</span>}
            </div>
          )}

          <form className="composer" onSubmit={(e) => { e.preventDefault(); submit(); }}>
            <textarea ref={inputRef} rows={2} value={input} placeholder={placeholder}
              disabled={mode === "practice" && !practice} aria-label={mode === "ask" ? "Your question" : "Your answer"}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }} />
            <button type="submit" className="primary" disabled={busy || !input.trim()}>
              {mode === "ask" ? "Ask" : "Check my answer"}
            </button>
          </form>
        </main>

        <aside className={`panel ${sheetOpen ? "open" : ""}`} aria-label="Sources and research notes">
          <div className="panel-tabs" role="tablist">
            <button type="button" role="tab" aria-selected={panel === "sources"} onClick={() => setPanel("sources")}>Sources</button>
            <button type="button" role="tab" aria-selected={panel === "notes"} onClick={() => setPanel("notes")}>Research notes</button>
            <button type="button" className="close-sheet" onClick={() => setSheetOpen(false)} aria-label="Close panel">Close</button>
          </div>
          <div className="panel-body">
            {panel === "sources"
              ? <SourcePanel entry={selectedEntry} active={selected?.n ?? 0} onSelect={(n) => selected && setSelected({ ...selected, n })} />
              : <ResearchNotes />}
          </div>
        </aside>
      </div>
    </div>
  );
}
