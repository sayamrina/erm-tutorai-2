<p align="center"><img src="docs/img/logo.png" width="110" alt="ERM Tutor-AI logo"></p>

# ERM Tutor-AI 2: an AI tutor that cites the lecture page for every statement

[![ci](https://github.com/sayamrina/erm-tutorai-2/actions/workflows/ci.yml/badge.svg)](https://github.com/sayamrina/erm-tutorai-2/actions/workflows/ci.yml)

**Version 2 of my master's thesis project · M.Sc. Educational Technology · Saarland University**
Amrina · Supervisors: Dominik Thüs and Dr. Sarah Malone

🌐 **Project page:** https://sayamrina.github.io/erm-tutorai-2/ · 🚀 **Live app:** https://erm-tutorai-2.onrender.com/ · 👤 **Portfolio:** https://sayamrina.github.io

↩️ **Version 1 (thesis app):** [project page](https://sayamrina.github.io/ERM_TutorAI_v4/) · [live app](https://erm-tutorai.streamlit.app/) · [code](https://github.com/sayamrina/ERM_TutorAI_v4) · 📄 [Thesis](https://doi.org/10.5281/zenodo.23749487)

ERM Tutor-AI is a virtual assistant for students in the *Empirical Research Methods* (ERM) course. Like version 1, it answers from the course's twelve lecture units with **Retrieval-Augmented Generation (RAG)**, behaves like a tutor rather than a search engine, and declines questions outside the course.

Version 2 keeps the same lecture materials, model and tutor rules and makes the answers easier to check and to learn from: every statement points to the lecture page it is based on, a practice mode gives feedback on the student's own answers, and a side panel summarises what the thesis evaluation found.

![Answer with numbered citations, the syllabus strip and the source panel](docs/img/d-answer.jpg)

---

## Why a version 2

The thesis showed that grounding a tutor in the course materials gives shorter, focused answers. Two things it listed as next steps shaped this version:

- **Citations at passage level.** Version 1 named one source file under each answer. A student who wants to check a claim still has to search the PDF. Version 2 links each statement to the exact lecture page.
- **Adaptive feedback.** Version 1 only answered questions. Version 2 adds a practice mode in which the student answers and the tutor gives feedback, a first step towards the adaptive feedback proposed in the thesis.

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

| Practice mode | Mobile |
|---|---|
| ![Practice question, the student's answer and feedback with a verdict and citations](docs/img/d-practice.jpg) | <img src="docs/img/m-answer.jpg" width="260" alt="Answer on a phone"> |

## How it works

1. **Indexing** (`backend/app/ingest.py`). The 12 lecture PDFs (unchanged from version 1) are read page by page with pdfminer, the engine Markitdown uses for PDFs, and split into chunks of up to 1,500 characters with 50 characters overlap, as in version 1. Each chunk keeps its unit, page and slide title (`backend/data/chunks.json`, 354 chunks).
2. **Embeddings.** OpenAI `text-embedding-3-small`, as in the live version 1 app. They are computed once at start-up and cached in `backend/data/embeddings.npy`.
3. **Retrieval** (`retrieval.py`). Cosine similarity with maximal marginal relevance, 4 passages from 10 candidates, as in version 1; optionally limited to one unit.
4. **Answering** (`tutor.py`). GPT-4o, temperature 0, with the version 1 tutor prompt: course materials first, general ERM knowledge second, the same refusal sentence for unrelated questions, and reflection, answer and follow-up woven into one reply. New: the passages are numbered and the model cites them as [1], [2]. Answers stream to the browser as server-sent events.
5. **Interface.** React and TypeScript, served by the FastAPI backend.

Without an OpenAI key the app runs in **demo mode**: keyword search (BM25) over the same chunks shows the matching passages, but there are no tutor answers and no practice questions. The public deployment limits model calls per browser session per hour and per day.

| Layer | Version 1 | Version 2 |
|---|---|---|
| Interface | Streamlit | React 18, TypeScript, Vite |
| API | – | FastAPI, server-sent events |
| LLM | OpenAI GPT-4o | OpenAI GPT-4o |
| Orchestration | LangChain (RetrievalQA) | Direct API calls |
| Vector store | ChromaDB | NumPy (cosine, MMR); rank-bm25 for demo mode |
| PDF parsing | Markitdown | pdfminer.six, page by page |
| Tests and delivery | Streamlit Cloud | pytest (13 tests), GitHub Actions, Docker, Render |

Version 2 calls the OpenAI API directly, because streaming and numbered citations need control over the prompt and the passages, and 354 vectors fit comfortably in memory.

## Evaluation (version 1)

Version 2 has not been evaluated yet. The thesis evaluated version 1:

- **Questions:** 20 representative questions from the weekly ERM assignments, covering all course units.
- **Systems:** ERM Tutor-AI vs. ChatGPT-4o (without retrieval) as the baseline.
- **Raters:** two course instructors, using a 7-point rubric adapted from Lee (2024): accuracy, relevance, excessive or insufficient information, user perception, and tutoring behaviour.

Mean rubric score (± SD), re-computed from the raw ratings:

| Rater | ERM Tutor-AI | ChatGPT-4o |
|---|---|---|
| Both instructors (n = 40) | 6.33 ± 1.00 | 6.00 ± 0.75 |
| Instructor 1 (n = 20) | 7.00 ± 0.00 | 5.60 ± 0.50 |
| Instructor 2 (n = 20) | 5.65 ± 1.04 | 6.40 ± 0.75 |

On average the tutor was rated slightly higher (two-way ANOVA, system F(1, 76) = 4.44, p = .038), but the two instructors disagreed on which system was better (interaction F(1, 76) = 48.6, p < .001), so the quality result is preliminary. The tutor's answers were shorter (198 vs. 280 words on average) and more consistent in length.

These figures were re-checked against the raw ratings after the thesis was submitted and replace the summary table in the thesis (6.75 vs. 6.00).

![Research notes panel](docs/img/t-notes.jpg)

## Limitations

- The evaluation used 20 questions and two raters who were not blind to the system and who disagreed.
- There was no study with students, so effects on learning and engagement are unknown.
- The knowledge base is limited to the course materials, and the system was not compared with other architectures.
- Version 2's citations and practice feedback have not been evaluated. The model can still cite a passage that only partly supports a statement, so the source panel is there for students to check.

## Next steps

A study with students that compares version 1 and version 2 (do page-level citations change how often students check an answer, and how much they trust it?), and practice questions that adapt to what each student already answered correctly.

## Run it locally

```bash
git clone https://github.com/sayamrina/erm-tutorai-2.git
cd erm-tutorai-2

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

## Repository structure

```text
backend/
  app/
    main.py        FastAPI app: ask, practice and health endpoints, rate limits, static files
    ingest.py      PDF parsing per page and chunking with unit, page and slide title
    retrieval.py   embeddings, cosine similarity + MMR, BM25 for demo mode
    tutor.py       tutor prompt, numbered passages, practice questions and feedback
    config.py      settings from environment variables
  data/
    materials/     ERM lecture PDFs used as the knowledge base (same as version 1)
    chunks.json    354 chunks with their metadata
  tests/           pytest
frontend/src/      React interface (chat, source panel, practice mode, research notes)
docs/              project page (GitHub Pages)
Dockerfile, render.yaml
```

## Author

**Amrina** · [LinkedIn](https://www.linkedin.com/in/amrina-ali-487025119/) · [GitHub](https://github.com/sayamrina)

Master's thesis in Educational Technology, Saarland University, 2025. Lecture materials: Empirical Research Methods course, Saarland University.

This app was built by Amrina, with AI as a supporting tool for coding.

© 2025–2026 Amrina. All rights reserved.
