"""API of ERM Tutor-AI 2. The React frontend is served from the same origin."""
import json
import logging
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .ingest import DATA, UNIT_TITLES
from .retrieval import Retriever
from .slides import SLIDES
from .tutor import Tutor

STATIC = Path(__file__).resolve().parent.parent / "static"
RATINGS = DATA / "ratings.jsonl"
log = logging.getLogger("uvicorn.error")


def make_tutor() -> Tutor:
    if not settings.openai_api_key:
        return Tutor(Retriever())
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key, timeout=60)

    def embed(texts: list[str]):
        out = []
        for start in range(0, len(texts), 100):
            response = client.embeddings.create(model=settings.embedding_model, input=texts[start:start + 100])
            out += [d.embedding for d in response.data]
        return out

    try:
        retriever = Retriever(embed)
    except Exception as exc:  # wrong key, no credit, network: keep the app up in demo mode
        log.error("Could not build embeddings, starting in demo mode: %s", exc)
        return Tutor(Retriever())
    return Tutor(retriever, client, settings.chat_model)


class Limiter:
    """Bounds model calls on a public demo: per browser session per hour, and per day overall."""

    def __init__(self):
        self.sessions: dict[str, deque] = defaultdict(deque)
        self.day: tuple[str, int] = ("", 0)

    def check(self, session: str):
        now = time.time()
        q = self.sessions[session]
        while q and now - q[0] > 3600:
            q.popleft()
        today = time.strftime("%Y-%m-%d")
        if self.day[0] != today:
            self.day = (today, 0)
        if len(q) >= settings.session_limit_per_hour or self.day[1] >= settings.global_limit_per_day:
            raise HTTPException(429, "The question limit for this demo is reached. Try again in an hour.")
        q.append(now)
        self.day = (today, self.day[1] + 1)


class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=6000)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=800)
    unit: int | None = Field(default=None, ge=1, le=12)
    history: list[Turn] = Field(default_factory=list, max_length=12)


class PracticeRequest(BaseModel):
    unit: int = Field(ge=1, le=12)


class Rating(BaseModel):
    rating: str = Field(pattern="^(up|down)$")
    kind: str = Field(pattern="^(answer|feedback)$")
    question: str = Field(max_length=800)
    answer: str = Field(max_length=6000)
    cited: list[int] = Field(default_factory=list, max_length=20)


class PracticeAnswer(BaseModel):
    question: str = Field(min_length=1, max_length=800)
    answer: str = Field(min_length=1, max_length=2000)
    seed_id: str = Field(max_length=40)
    unit: int = Field(ge=1, le=12)


def sse(events) -> StreamingResponse:
    def body():
        try:
            for event in events:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception:  # the stream has started, so report the failure as an event
            yield 'data: {"type": "error", "message": "The language model did not respond. Try again."}\n\n'
    return StreamingResponse(body(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def create_app(tutor: Tutor | None = None) -> FastAPI:
    app = FastAPI(title="ERM Tutor-AI 2", version="2.0.0")
    # The start page on GitHub Pages polls /api/health while the free server wakes up.
    app.add_middleware(CORSMiddleware, allow_origins=["https://sayamrina.github.io"], allow_methods=["GET"])
    tutor = tutor or make_tutor()
    limiter = Limiter()

    def guard(request: Request):
        if tutor.client is not None:
            session = request.headers.get("x-session-id") or (request.client.host if request.client else "anon")
            limiter.check(session)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "tutor" if tutor.client else "demo", "retrieval": tutor.retriever.mode}

    @app.get("/api/units")
    def units():
        counts = defaultdict(int)
        for c in tutor.retriever.chunks:
            counts[c["unit"]] += 1
        return [{"unit": u, "title": t, "chunks": counts[u]} for u, t in UNIT_TITLES.items()]

    @app.get("/api/passages/{passage_id}")
    def passage(passage_id: str):
        if passage_id not in tutor.retriever.by_id:
            raise HTTPException(404, "Passage not found")
        return tutor.retriever.by_id[passage_id]

    @app.post("/api/ask")
    def ask(q: Question, request: Request):
        guard(request)
        return sse(tutor.ask(q.question, q.unit, [t.model_dump() for t in q.history]))

    @app.post("/api/practice/question")
    def practice_question(p: PracticeRequest, request: Request):
        if tutor.client is None:
            raise HTTPException(409, "Practice needs the language model, which is not connected in demo mode.")
        guard(request)
        return tutor.practice_question(p.unit)

    @app.post("/api/practice/feedback")
    def practice_feedback(a: PracticeAnswer, request: Request):
        if tutor.client is None:
            raise HTTPException(409, "Practice needs the language model, which is not connected in demo mode.")
        if a.seed_id not in tutor.retriever.by_id:
            raise HTTPException(404, "Practice passage not found")
        guard(request)
        return sse(tutor.feedback(a.question, a.answer, a.seed_id, a.unit))

    @app.post("/api/rating", status_code=204)
    def rating(r: Rating):
        # Render's free disk is wiped on every deploy, so ratings also go to the log.
        record = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), **r.model_dump()}
        log.info("rating %s", json.dumps(record, ensure_ascii=False))
        try:
            with RATINGS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:  # read-only or full disk: the log line is enough
            pass

    if SLIDES.exists():
        app.mount("/slides", StaticFiles(directory=SLIDES), name="slides")

    if STATIC.exists():
        app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            file = STATIC / path
            return FileResponse(file if path and file.is_file() else STATIC / "index.html")

    return app


app = create_app()
