import { useEffect, useRef, useState } from "react";
import {
  getHealth, getUnits, newPracticeQuestion, rate, slideUrl, stream,
  type Health, type Label, type Passage, type PracticeQuestion, type StreamEvent, type Trace, type Unit, type Verdict,
} from "./api";
import Behind from "./Behind";
import ResearchNotes from "./Notes";
import { load, save as store, type Progress } from "./storage";
import { claimsCiting, statementsCiting, supportingLines } from "./support";
import { RichText, splitFollowUp, toMarkdown } from "./text";

type Entry = {
  id: number;
  role: "student" | "tutor";
  text: string;
  question?: string;
  passages?: Passage[];
  cited?: number[];
  label?: Label;
  words?: number;
  verdict?: Verdict | null;
  trace?: Trace;
  rating?: "up" | "down";
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
  mixed: "From the course materials; general knowledge is marked",
  general: "From general research-methods knowledge, not the course materials",
  declined: "",
  demo: "Demo mode: matching passages only",
};

const VERDICT_TEXT: Record<Verdict, string> = {
  correct: "Correct", "partly correct": "Partly correct", "not yet": "Not there yet",
};

/** Restores a saved conversation; anything cut off mid-answer is dropped. */
const restore = (key: string) =>
  load<Entry[]>(key, []).filter((e) => e.text && !e.streaming).slice(-40);

const savedChat = restore("erm2-chat");
const savedPractice = restore("erm2-practice-log");
let nextId = Math.max(0, ...savedChat.map((e) => e.id), ...savedPractice.map((e) => e.id)) + 1;

/** Slide text keeps the PDF's line breaks; join wrapped lines, keep paragraphs and bullets. */
const readable = (text: string) => text.replace(/([^\n])\n(?![\n•])/g, "$1 ");

function sourceLine(p: Passage, n: number) {
  return `[${n}] Unit ${p.unit}, ${p.unit_title}, page ${p.page}${p.section ? ` (${p.section})` : ""}`;
}

function plainAnswer(e: Entry) {
  const sources = (e.cited ?? []).map((n) => e.passages?.[n - 1] && sourceLine(e.passages[n - 1], n)).filter(Boolean);
  return [e.text.trim(), ...(sources.length ? ["", "Sources:", ...sources] : [])].join("\n");
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

function TutorEntry({ entry, units, onCite, onReply, onRate, onBehind }: {
  entry: Entry; units: Unit[]; onCite: (entry: Entry, n: number) => void; onReply: (q: string) => void;
  onRate: (entry: Entry, rating: "up" | "down") => void; onBehind: (entry: Entry) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const available = entry.passages?.length ?? 0;
  const { body, followUp } = entry.streaming || entry.verdict !== undefined
    ? { body: entry.text, followUp: null } : splitFollowUp(entry.text);
  const cite = { available, passages: entry.passages, onCite: (n: number) => onCite(entry, n), onHover: setHover };

  function copy() {
    navigator.clipboard?.writeText(plainAnswer(entry)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    }).catch(() => undefined);
  }

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
      {!entry.streaming && entry.text && entry.verdict !== null && !entry.error && (
        <div className="entry-actions">
          <button type="button" className="tool" onClick={copy}>{copied ? "Copied" : "Copy"}</button>
          {entry.trace && <button type="button" className="tool" onClick={() => onBehind(entry)}>Behind the answer</button>}
          <span className="rate" role="group" aria-label="Was this answer helpful?">
            {entry.rating
              ? <span className="muted">Thanks for the feedback</span>
              : (
                <>
                  <span className="muted">Helpful?</span>
                  <button type="button" className="tool" aria-label="Helpful" onClick={() => onRate(entry, "up")}>Yes</button>
                  <button type="button" className="tool" aria-label="Not helpful" onClick={() => onRate(entry, "down")}>No</button>
                </>
              )}
          </span>
        </div>
      )}
    </div>
  );
}

/** One passage line by line, with the lines that support the cited statements marked. */
function PassageText({ text, statements }: { text: string; statements: string[] }) {
  const lines = readable(text).split("\n").filter((line) => line.trim() && !/^\d+$/.test(line.trim()));
  const marked = supportingLines(lines, statements);
  return (
    <blockquote className="lines">
      {lines.map((line, i) => (
        <span key={i} className="line">{marked.has(i) ? <mark>{line}</mark> : line}</span>
      ))}
    </blockquote>
  );
}

function SourcePanel({ entry, active, onSelect }: { entry: Entry | null; active: number; onSelect: (n: number) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState<Passage | null>(null);
  useEffect(() => {
    ref.current?.querySelector(".passage.active")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [entry, active]);
  useEffect(() => {
    if (!zoom) return;
    const close = (e: KeyboardEvent) => { if (e.key === "Escape") setZoom(null); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [zoom]);
  if (!entry?.passages?.length) {
    return (
      <div className="panel-empty">
        <p>Select a number in an answer to see the slide it comes from.</p>
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
        const statements = statementsCiting(entry.text, n);
        const isActive = n === active;
        return (
          <section key={p.id} className={`passage ${isActive ? "active" : ""} ${cited.has(n) ? "" : "uncited"}`}
            onClick={() => onSelect(n)}>
            <header>
              <span className="num">{n}</span>
              <div>
                <h4>Unit {p.unit}: {p.unit_title}</h4>
                <p>Page {p.page}{p.section ? `, ${p.section}` : ""}{cited.has(n) ? "" : ". Not cited"}</p>
              </div>
            </header>
            <button type="button" className="slide" onClick={(e) => { e.stopPropagation(); setZoom(p); }}
              aria-label={`Enlarge slide: unit ${p.unit}, page ${p.page}`}>
              <img src={slideUrl(p.unit, p.page)} alt={`Lecture slide, unit ${p.unit}, page ${p.page}: ${p.section}`}
                loading="lazy" onError={(e) => { (e.currentTarget.parentElement as HTMLElement).hidden = true; }} />
            </button>
            {isActive && statements.length > 0 && (
              <p className="supports"><span>Cited for</span> “{statements[0]}”{statements.length > 1 ? ` and ${statements.length - 1} more` : ""}</p>
            )}
            {isActive ? <PassageText text={p.text} statements={claimsCiting(entry.text, n)} /> : <blockquote>{readable(p.text)}</blockquote>}
          </section>
        );
      })}
      {zoom && (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label="Lecture slide" onClick={() => setZoom(null)}>
          <figure onClick={(e) => e.stopPropagation()}>
            <img src={slideUrl(zoom.unit, zoom.page)} alt={`Lecture slide, unit ${zoom.unit}, page ${zoom.page}: ${zoom.section}`} />
            <figcaption>
              Unit {zoom.unit}: {zoom.unit_title}, page {zoom.page}
              <button type="button" className="primary" onClick={() => setZoom(null)} autoFocus>Close</button>
            </figcaption>
          </figure>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [waking, setWaking] = useState(false);
  const [units, setUnits] = useState<Unit[]>([]);
  const [mode, setMode] = useState<"ask" | "practice">("ask");
  const [unit, setUnit] = useState<number | null>(null);
  const [entries, setEntries] = useState<Entry[]>(savedChat);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [panel, setPanel] = useState<"sources" | "behind" | "notes">("notes");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [selected, setSelected] = useState<{ id: number; n: number } | null>(null);
  const [practice, setPractice] = useState<PracticeQuestion | null>(null);
  const [practiceLog, setPracticeLog] = useState<Entry[]>(savedPractice);
  const [progress, setProgress] = useState<Progress>(() => load<Progress>("erm2-progress", {}));
  const [notice, setNotice] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // A free server sleeps when nobody uses it; keep asking while it starts.
    let tries = 0, stopped = false;
    const check = () => getHealth().then((h) => {
      if (stopped) return;
      setHealth(h);
      setWaking(false);
      getUnits().then(setUnits).catch(() => undefined);
    }).catch(() => {
      if (stopped) return;
      tries += 1;
      if (tries > 30) {
        setWaking(false);
        setNotice("The tutor service is not reachable. Reload the page in a minute.");
      } else {
        setWaking(true);
        setTimeout(check, 3000);
      }
    });
    check();
    return () => { stopped = true; };
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [entries.length, practiceLog.length]);
  useEffect(() => { if (!busy) store("erm2-chat", entries.slice(-40)); }, [entries, busy]);
  useEffect(() => { if (!busy) store("erm2-practice-log", practiceLog.slice(-40)); }, [practiceLog, busy]);
  useEffect(() => { store("erm2-progress", progress); }, [progress]);

  const demo = health?.mode === "demo";
  const unitTitle = unit ? units.find((u) => u.unit === unit)?.title : null;
  const log = mode === "ask" ? entries : practiceLog;
  const setLog = mode === "ask" ? setEntries : setPracticeLog;
  const all = [...entries, ...practiceLog];
  const selectedEntry = selected ? all.find((e) => e.id === selected.id) ?? null : null;
  const behindEntry = (selectedEntry?.trace ? selectedEntry : null) ?? [...log].reverse().find((e) => e.trace) ?? null;

  function patch(id: number, update: (e: Entry) => Entry) {
    setLog((list) => list.map((e) => (e.id === id ? update(e) : e)));
  }

  function count(practiceUnit: number, verdict: Verdict) {
    setProgress((p) => {
      const row = p[practiceUnit] ?? { correct: 0, partly: 0, notYet: 0 };
      const key = verdict === "correct" ? "correct" : verdict === "partly correct" ? "partly" : "notYet";
      return { ...p, [practiceUnit]: { ...row, [key]: row[key] + 1 } };
    });
  }

  async function run(path: string, body: unknown, studentText: string, practiceUnit?: number) {
    const tutorId = nextId++;
    setLog((list) => [...list, { id: nextId++, role: "student", text: studentText },
      { id: tutorId, role: "tutor", text: "", question: studentText, streaming: true }]);
    setBusy(true);
    try {
      await stream(path, body, (ev: StreamEvent) => {
        if (ev.type === "sources") patch(tutorId, (e) => ({ ...e, passages: ev.passages }));
        else if (ev.type === "token") patch(tutorId, (e) => ({ ...e, text: e.text + ev.text }));
        else if (ev.type === "verdict") {
          patch(tutorId, (e) => ({ ...e, verdict: ev.verdict }));
          if (practiceUnit && ev.verdict) count(practiceUnit, ev.verdict);
        } else if (ev.type === "trace") {
          const { type: _, ...trace } = ev;
          patch(tutorId, (e) => ({ ...e, trace }));
        } else if (ev.type === "done") patch(tutorId, (e) => ({ ...e, streaming: false, cited: ev.cited, label: ev.label, words: ev.words }));
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
    run("/api/practice/feedback", { ...practice, answer: a }, a, practice.unit).then(() => setPractice(null));
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

  function openBehind(entry: Entry) {
    setSelected({ id: entry.id, n: entry.cited?.[0] ?? 1 });
    setPanel("behind");
    setSheetOpen(true);
  }

  function rateEntry(entry: Entry, rating: "up" | "down") {
    const update = (e: Entry) => ({ ...e, rating });
    setEntries((list) => list.map((e) => (e.id === entry.id ? update(e) : e)));
    setPracticeLog((list) => list.map((e) => (e.id === entry.id ? update(e) : e)));
    rate({ rating, kind: entry.verdict ? "feedback" : "answer", question: entry.question ?? "", answer: entry.text, cited: entry.cited ?? [] })
      .catch(() => undefined);
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

  function newChat() {
    if (busy) return;
    setLog([]);
    setSelected(null);
    setPractice(null);
    setPanel("notes");
  }

  function switchMode(next: "ask" | "practice") {
    setMode(next);
    setNotice("");
    if (next === "practice" && !unit) setUnit(7);
  }

  const placeholder = mode === "ask"
    ? (unitTitle ? `Ask about ${unitTitle}` : "Ask about anything in the course")
    : practice ? "Write your answer in a few sentences" : "Pick a unit and get a question first";
  const practised = Object.values(progress).reduce((sum, r) => sum + r.correct + r.partly + r.notYet, 0);

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
          <button type="button" className="ghost" onClick={newChat} disabled={busy || log.length === 0}>New chat</button>
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
            {units.map((u) => {
              const row = progress[u.unit];
              return (
                <li key={u.unit}>
                  <button type="button" aria-current={unit === u.unit} onClick={() => setUnit(u.unit)}>
                    <span className="n">{u.unit}</span><span>{u.title}</span>
                    {mode === "practice" && row && (
                      <span className="unit-score" aria-label={`${row.correct} correct, ${row.partly} partly correct, ${row.notYet} not yet`}>
                        {[...Array(row.correct)].map((_, i) => <i key={`c${i}`} className="s-correct" />)}
                        {[...Array(row.partly)].map((_, i) => <i key={`p${i}`} className="s-partly" />)}
                        {[...Array(row.notYet)].map((_, i) => <i key={`n${i}`} className="s-notyet" />)}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>

        <main className="conversation">
          {waking && (
            <p className="demo-note" role="status">
              Starting the tutor. The free server sleeps when nobody uses it and needs up to a minute to wake up.
            </p>
          )}
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
                  <button key={u} type="button" onClick={() => ask(STARTERS[u])} disabled={waking}>{STARTERS[u]}</button>
                ))}
              </div>
            </section>
          )}

          {log.length === 0 && mode === "practice" && (
            <section className="empty">
              <h1>Test yourself on one unit.</h1>
              <p>The tutor writes a question from a lecture slide, you answer in your own words, and the feedback shows the slides to review.</p>
              {practised > 0 && (
                <div className="progress-map" aria-label="Your practice so far">
                  <p className="progress-title">Your practice so far, saved in this browser</p>
                  <ol>
                    {units.map((u) => {
                      const r = progress[u.unit];
                      const total = r ? r.correct + r.partly + r.notYet : 0;
                      return (
                        <li key={u.unit} title={`Unit ${u.unit}: ${u.title}`}>
                          <button type="button" onClick={() => setUnit(u.unit)} aria-current={unit === u.unit}>
                            <span className="pm-n">{u.unit}</span>
                            <span className="pm-bar">
                              {total > 0 && r && (
                                <>
                                  <i className="s-correct" style={{ flexGrow: r.correct }} />
                                  <i className="s-partly" style={{ flexGrow: r.partly }} />
                                  <i className="s-notyet" style={{ flexGrow: r.notYet }} />
                                </>
                              )}
                            </span>
                            <span className="pm-count">{total || ""}</span>
                          </button>
                        </li>
                      );
                    })}
                  </ol>
                  <p className="progress-legend">
                    <span><i className="s-correct" />Correct</span><span><i className="s-partly" />Partly</span><span><i className="s-notyet" />Not yet</span>
                  </p>
                </div>
              )}
            </section>
          )}

          <div className="log">
            {log.map((e) => e.role === "student"
              ? <div key={e.id} className="entry student"><p>{e.text}</p></div>
              : <TutorEntry key={e.id} entry={e} units={units} onCite={openSource} onReply={reply}
                  onRate={rateEntry} onBehind={openBehind} />)}
            <div ref={endRef} />
          </div>

          {mode === "practice" && !practice && (
            <div className="practice-bar">
              <button type="button" className="primary" onClick={startPractice} disabled={busy || demo || !unit || waking}>
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
            <button type="submit" className="primary" disabled={busy || waking || !input.trim()}>
              {mode === "ask" ? "Ask" : "Check my answer"}
            </button>
          </form>
        </main>

        <aside className={`panel ${sheetOpen ? "open" : ""}`} aria-label="Sources, how the answer was made, and research notes">
          <div className="panel-tabs" role="tablist">
            <button type="button" role="tab" aria-selected={panel === "sources"} onClick={() => setPanel("sources")}>Sources</button>
            <button type="button" role="tab" aria-selected={panel === "behind"} onClick={() => setPanel("behind")}>Behind the answer</button>
            <button type="button" role="tab" aria-selected={panel === "notes"} onClick={() => setPanel("notes")}>Research notes</button>
            <button type="button" className="close-sheet" onClick={() => setSheetOpen(false)} aria-label="Close panel">Close</button>
          </div>
          <div className="panel-body" key={panel}>
            {panel === "sources" && <SourcePanel entry={selectedEntry} active={selected?.n ?? 0} onSelect={(n) => selected && setSelected({ ...selected, n })} />}
            {panel === "behind" && (
              <Behind question={behindEntry?.question ?? ""} trace={behindEntry?.trace}
                practice={behindEntry?.verdict !== undefined} passageIds={(behindEntry?.passages ?? []).map((p) => p.id)} />
            )}
            {panel === "notes" && <ResearchNotes />}
          </div>
        </aside>
      </div>
    </div>
  );
}
