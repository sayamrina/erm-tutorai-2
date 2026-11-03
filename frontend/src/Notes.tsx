import { useState } from "react";

// Ratings re-computed from the raw evaluation data of the thesis (7-point rubric, 20 questions).
const ROWS = [
  { label: "Both instructors", n: 40, tutor: [6.33, 1.0], gpt: [6.0, 0.75] },
  { label: "Instructor 1", n: 20, tutor: [7.0, 0.0], gpt: [5.6, 0.5] },
  { label: "Instructor 2", n: 20, tutor: [5.65, 1.04], gpt: [6.4, 0.75] },
] as const;

const W = 300, LEFT = 104, RIGHT = 14, ROW = 40, TOP = 26;
const MIN = 4; // the rubric runs from 1 to 7; all means lie above 5
const x = (v: number) => LEFT + ((v - MIN) / (7 - MIN)) * (W - LEFT - RIGHT);

type Tip = { x: number; y: number; text: string } | null;

function RatingChart() {
  const [tip, setTip] = useState<Tip>(null);
  const height = TOP + ROWS.length * ROW + 22;
  return (
    <div className="chart">
      <div className="legend" aria-hidden="true">
        <span><i className="dot tutor" /> ERM Tutor-AI</span>
        <span><i className="dot gpt" /> ChatGPT-4o</span>
      </div>
      <svg viewBox={`0 0 ${W} ${height}`} role="img"
        aria-label="Mean rubric scores. Both instructors: ERM Tutor-AI 6.33, ChatGPT-4o 6.00. Instructor 1: 7.00 and 5.60. Instructor 2: 5.65 and 6.40.">
        {[4, 5, 6, 7].map((v) => (
          <g key={v}>
            <line className="grid" x1={x(v)} x2={x(v)} y1={TOP - 8} y2={height - 20} />
            <text className="axis-label" x={x(v)} y={height - 6} textAnchor="middle">{v}</text>
          </g>
        ))}
        {ROWS.map((r, i) => {
          const y = TOP + i * ROW + ROW / 2 - 8;
          const pts = [
            { cls: "tutor", name: "ERM Tutor-AI", v: r.tutor },
            { cls: "gpt", name: "ChatGPT-4o", v: r.gpt },
          ];
          return (
            <g key={r.label}>
              <text className="row-label" x={0} y={y + 4}>{r.label}</text>
              <line className="link" x1={x(r.tutor[0])} x2={x(r.gpt[0])} y1={y} y2={y} />
              {pts.map((p) => (
                <g key={p.cls}>
                  <circle className={`mark ${p.cls}`} cx={x(p.v[0])} cy={y} r={5.5} />
                  <circle className="hit" cx={x(p.v[0])} cy={y} r={12}
                    onMouseEnter={() => setTip({ x: x(p.v[0]), y, text: `${p.name}, ${r.label.toLowerCase()}: ${p.v[0].toFixed(2)} ± ${p.v[1].toFixed(2)} (n = ${r.n})` })}
                    onMouseLeave={() => setTip(null)} />
                </g>
              ))}
            </g>
          );
        })}
      </svg>
      {tip && (
        <div className="tooltip" style={{ left: `${(tip.x / W) * 100}%`, top: `${((tip.y + 18) / height) * 100}%` }}>
          {tip.text}
        </div>
      )}
    </div>
  );
}

function RatingTable() {
  return (
    <table className="data-table">
      <caption>Mean ± SD on the 7-point rubric</caption>
      <thead><tr><th scope="col">Rater</th><th scope="col">ERM Tutor-AI</th><th scope="col">ChatGPT-4o</th></tr></thead>
      <tbody>
        {ROWS.map((r) => (
          <tr key={r.label}>
            <th scope="row">{r.label}</th>
            <td>{r.tutor[0].toFixed(2)} ± {r.tutor[1].toFixed(2)}</td>
            <td>{r.gpt[0].toFixed(2)} ± {r.gpt[1].toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function ResearchNotes() {
  const [asTable, setAsTable] = useState(false);
  return (
    <article className="notes">
      <h2>What the thesis found</h2>
      <p className="lede">
        ERM Tutor-AI was built and evaluated in a master's thesis in Educational Technology at Saarland
        University (2025), supervised by Dominik Thüs and Dr. Sarah Malone. Version 2 uses the same lecture
        materials, with stricter rules for citing them. The findings below are about the first version.
      </p>

      <h3>How it was tested</h3>
      <p>
        Twenty questions from the weekly ERM assignments went to the tutor and to ChatGPT-4o without access
        to the course materials. Two course instructors rated every answer on a 7-point rubric: accuracy,
        relevance, amount of information, how it reads to a student, and tutoring behaviour.
      </p>

      <h3>Ratings</h3>
      <div className="chart-head">
        <span>Mean score per rater (scale 1 to 7, axis starts at 4)</span>
        <button type="button" className="link-button" onClick={() => setAsTable(!asTable)}>
          {asTable ? "Show chart" : "Show table"}
        </button>
      </div>
      {asTable ? <RatingTable /> : <RatingChart />}
      <p>
        On average the tutor was rated slightly higher, 6.33 against 6.00 (two-way ANOVA, system
        F(1, 76) = 4.44, p = .038). The instructors disagreed, though: one preferred the tutor, the other
        ChatGPT-4o (interaction F(1, 76) = 48.6, p &lt; .001). The quality result is preliminary.
      </p>

      <h3>Answer length</h3>
      <p>
        The tutor's answers had 198 words on average, against 280 for ChatGPT-4o, and their length varied
        less. The instructors described them as concise summaries of key concepts that invite further study,
        useful next to regular tutoring and for exam preparation.
      </p>

      <h3>Limits</h3>
      <ul>
        <li>No students took part, so the study measured answer quality, not learning.</li>
        <li>Two raters who disagreed, rating without being blind to the system.</li>
        <li>Twenty questions, all from the assignments the tutor's materials cover.</li>
        <li>One comparison only, so it does not show which component made the difference.</li>
      </ul>

      <h3>What version 2 adds</h3>
      <ul>
        <li>Every answer links to the lecture page it uses, so you can check it against the slide.</li>
        <li>Practice questions with feedback, a first step towards the adaptive feedback the thesis proposed as future work.</li>
      </ul>

      <h3>Automatic check of version 2</h3>
      <p>
        The 20 thesis questions and three off-topic questions, run against this app on 3 November 2026: all 20
        answers drew on the course materials and all three off-topic questions were declined. With the thesis
        rules, about one statement in four carried a citation. Version 2 rules make the slides the source, ask for a
        citation per sentence and mark general knowledge as "Beyond the course slides": cited statements rose to
        41%, and 99% of them share key words with the slide they cite. No human rating yet.
      </p>

      <p className="source-note">
        Figures are re-computed from the raw ratings. Full thesis:{" "}
        <a href="https://doi.org/10.5281/zenodo.23749487" target="_blank" rel="noopener">doi.org/10.5281/zenodo.23749487</a>
      </p>
    </article>
  );
}
