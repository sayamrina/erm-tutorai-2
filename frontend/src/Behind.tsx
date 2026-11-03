import type { Trace } from "./api";

const secs = (ms: number) => `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;

/** What happened between the question and the answer: retrieval, timings, tokens and cost. */
export default function Behind({ question, trace, practice, passageIds }: {
  question: string; trace?: Trace; practice: boolean; passageIds: string[];
}) {
  if (!trace) {
    return (
      <div className="panel-empty">
        <p>Ask a question. This tab then shows how the answer was made: which passages retrieval found, which ones it chose, how long each step took and what the answer cost.</p>
      </div>
    );
  }
  const { retrieval_ms, first_token_ms, total_ms } = trace.timings;
  const writing = first_token_ms == null ? 0 : Math.max(total_ms - retrieval_ms - first_token_ms, 0);
  const waiting = first_token_ms ?? 0;
  const segments = [
    { cls: "t-retrieve", label: "Retrieval", ms: retrieval_ms },
    { cls: "t-wait", label: "Waiting for the model", ms: waiting },
    { cls: "t-write", label: "Writing the answer", ms: writing },
  ].filter((s) => s.ms > 0);
  const candidates = trace.retrieval.candidates ?? [];
  const scores = candidates.map((c) => c.score);
  const lo = Math.min(...scores), hi = Math.max(...scores);
  const width = (v: number) => (hi > lo ? 18 + ((v - lo) / (hi - lo)) * 82 : 100);
  const semantic = trace.retrieval.method === "mmr";

  return (
    <article className="behind">
      <p className="behind-q">{practice ? "Feedback on: " : "Answer to: "}<q>{question}</q></p>

      <h3>Time</h3>
      <div className="timeline" role="img" aria-label={segments.map((s) => `${s.label} ${secs(s.ms)}`).join(", ")}>
        {segments.map((s) => <span key={s.cls} className={s.cls} style={{ flexGrow: s.ms }} />)}
      </div>
      <dl className="timeline-legend">
        {segments.map((s) => (
          <div key={s.cls}><dt><i className={s.cls} />{s.label}</dt><dd>{secs(s.ms)}</dd></div>
        ))}
        <div className="total"><dt>Total</dt><dd>{secs(total_ms)}</dd></div>
      </dl>

      {trace.tokens && (
        <>
          <h3>Tokens and cost</h3>
          <dl className="facts">
            <div><dt>Prompt</dt><dd>{trace.tokens.prompt.toLocaleString("en")} tokens</dd></div>
            <div><dt>Answer</dt><dd>{trace.tokens.completion.toLocaleString("en")} tokens</dd></div>
            <div><dt>Cost</dt><dd>≈ ${trace.cost_usd?.toFixed(4)}</dd></div>
          </dl>
          <p className="fine">{trace.model}, temperature 0. Cost estimated at list price; the embedding of the question adds less than $0.00001.</p>
        </>
      )}

      <h3>Retrieval</h3>
      <p className="fine">
        {semantic
          ? `Semantic search found ${candidates.length} candidate passages; maximal marginal relevance chose ${candidates.filter((c) => c.chosen).length} that are relevant but do not repeat each other, so a lower score can win over a near-duplicate.`
          : "Demo mode: keyword search (BM25), scores relative to the best match."}
        {trace.retrieval.seed && " In practice mode, passage 1 is the slide the question was written from; the others come from this search."}
      </p>
      <ol className="candidates">
        {candidates.map((c) => {
          const n = passageIds.indexOf(c.id) + 1;
          return (
            <li key={c.id} className={n ? "chosen" : ""}>
              <span className="rank" aria-label={n ? `Used as passage ${n}` : "Not used"}>{n || "–"}</span>
              <span className="where">
                <b>Unit {c.unit}, page {c.page}</b>
                <span>{c.section}</span>
              </span>
              <span className="score">
                <span className="bar"><i style={{ width: `${width(c.score)}%` }} /></span>
                <span className="val">{c.score.toFixed(3)}</span>
              </span>
            </li>
          );
        })}
      </ol>
      <p className="fine">{semantic ? "Score: cosine similarity between the question and the passage." : ""}</p>
    </article>
  );
}
