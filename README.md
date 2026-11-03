<p align="center"><img src="frontend/public/logo.png" width="96" alt="ERM Tutor-AI logo"></p>

# ERM Tutor-AI 2

[![ci](https://github.com/sayamrina/erm-tutorai-2/actions/workflows/ci.yml/badge.svg)](https://github.com/sayamrina/erm-tutorai-2/actions/workflows/ci.yml)

**Version 2 of my master's thesis project** · [Version 1 (thesis app)](https://github.com/sayamrina/ERM_TutorAI_v4) · [Thesis](https://doi.org/10.5281/zenodo.23749487) · [Portfolio](https://sayamrina.github.io/)

ERM Tutor-AI is a tutor for students of the *Empirical Research Methods* course at Saarland University. It answers from the course's twelve lecture units with retrieval-augmented generation (RAG), behaves like a tutor rather than a search engine, and declines questions outside the course.

Version 2 keeps the same lecture materials, model and tutor rules as the thesis app and gives it a new interface: every statement in an answer points to the lecture page it is based on, a practice mode gives feedback on the student's own answers, and a side panel summarises what the thesis evaluation found.

![Answer with citations, the syllabus strip and the source panel](docs/img/d-answer.jpg)
<sub>Interface preview. The answer text in the screenshots was scripted to show the layout; it is not model output.</sub>

## What is new in version 2

| | Version 1 (thesis) | Version 2 |
|---|---|---|
| Sources | Name of one source file under the answer | Numbered citations after each statement; each opens the lecture passage with unit, page and slide title |
| Where an answer comes from | Label "course materials" or "general knowledge" | The same two labels, now derived from whether the answer cites a passage, plus a strip of twelve ticks showing which lecture units the answer used |
| Course focus | All units | All units, or one chosen unit |
| Practice | – | The tutor writes a question from a lecture slide, the student answers, the feedback gives a verdict (correct, partly correct, not yet) and cites the slides to review |
| Follow-up | Written in the answer | Shown separately with a button to answer it; the last two turns are sent along so the tutor can follow the conversation |
| Research notes | PDF "About this app" | Side panel with the evaluation design, ratings chart (or table), answer length and limits |
| Other | – | Streaming answers, save the conversation as Markdown, light and dark mode, mobile layout |

## How it works

1. **Indexing** (`backend/app/ingest.py`). The 12 lecture PDFs (unchanged from version 1) are read page by page with pdfminer, the engine Markitdown uses for PDFs, and split into chunks of up to 1,500 characters with 50 characters overlap, as in version 1. Each chunk keeps its unit, page and slide title (`backend/data/chunks.json`, 354 chunks).
2. **Embeddings.** OpenAI `text-embedding-3-small`, as in the live version 1 app. They are computed once at start-up (about 130,000 characters) and cached in `backend/data/embeddings.npy`.
3. **Retrieval** (`retrieval.py`). Cosine similarity with maximal marginal relevance, 4 passages from 10 candidates, as in version 1; optionally limited to one unit.
4. **Answering** (`tutor.py`). GPT-4o, temperature 0, with the version 1 tutor prompt: course materials first, general ERM knowledge second, the same refusal sentence for unrelated questions, and reflection, answer and follow-up woven into one reply. New: the passages are numbered and the model cites them as [1], [2]. Answers stream to the browser as server-sent events.
5. **Interface.** React and TypeScript, served by the FastAPI backend.

Without an OpenAI key the app runs in **demo mode**: keyword search (BM25) over the same chunks shows the matching passages, but there are no tutor answers and no practice questions.

A public deployment limits model calls per browser session per hour and per day.

| Layer | Tools |
|---|---|
| Interface | React 18, TypeScript, Vite |
| API | FastAPI, server-sent events |
| Model | OpenAI GPT-4o, text-embedding-3-small |
| Retrieval | NumPy (cosine, MMR), rank-bm25 for demo mode |
| PDF parsing | pdfminer.six |
| Tests and delivery | pytest (13 tests), GitHub Actions, Docker, Render |

Version 1 used LangChain's RetrievalQA and ChromaDB for the same steps. Version 2 calls the OpenAI API directly, because streaming and numbered citations need control over the prompt and the passages, and 354 vectors fit comfortably in memory.

## What the thesis found

Two course instructors rated the answers of version 1 and of ChatGPT-4o (without retrieval) to 20 questions from the weekly assignments on a 7-point rubric.

| Rater | ERM Tutor-AI | ChatGPT-4o |
|---|---|---|
| Both instructors (n = 40) | 6.33 ± 1.00 | 6.00 ± 0.75 |
| Instructor 1 (n = 20) | 7.00 ± 0.00 | 5.60 ± 0.50 |
| Instructor 2 (n = 20) | 5.65 ± 1.04 | 6.40 ± 0.75 |

On average the tutor was rated slightly higher (two-way ANOVA, system F(1, 76) = 4.44, p = .038), but the instructors disagreed on which system was better (interaction F(1, 76) = 48.6, p < .001), so the result is preliminary. The tutor's answers were shorter (198 vs. 280 words on average). The study had no students, two non-blind raters and 20 questions. Figures are re-computed from the raw ratings. Version 2 has not been evaluated.

![Research notes panel](docs/img/t-notes.jpg)

## Run it

```bash
# backend (Python 3.12)
python -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
cd backend && ../.venv/bin/pytest -q                        # 13 tests
echo "OPENAI_API_KEY=sk-..." > .env                         # leave out for demo mode
../.venv/bin/uvicorn app.main:app --port 8096

# frontend (Node 22), in a second terminal
cd frontend && npm ci && npm run dev                        # http://127.0.0.1:5173
```

`npm run build` writes the frontend to `backend/static`, which the backend then serves on its own port. To rebuild the chunks from the PDFs: `cd backend && ../.venv/bin/python -m app.ingest`.

**Deploy on Render:** New → Blueprint → this repository (`render.yaml`), then add `OPENAI_API_KEY` in the dashboard.

## Credits

Master's thesis in Educational Technology, Saarland University, 2025. Supervisors: Dominik Thüs and Dr. Sarah Malone. Lecture materials: Empirical Research Methods course, Saarland University.

This app was built by Amrina, with AI as a supporting tool for coding.
