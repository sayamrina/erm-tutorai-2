"""Retrieval over the course chunks.

With an OpenAI key: embeddings (text-embedding-3-small, as in the live v4 app) and maximal
marginal relevance, k = 4 from 10 candidates. Without a key: BM25 keyword search (demo mode).
"""
import json
import re
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from .ingest import CHUNKS, DATA

EMBEDDINGS = DATA / "embeddings.npy"
K, FETCH_K, MMR_LAMBDA = 4, 10, 0.5


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class Retriever:
    def __init__(self, embed=None, chunks_path: Path = CHUNKS, embeddings_path: Path = EMBEDDINGS):
        """embed: function list[str] -> np.ndarray of shape (n, d), or None for demo mode."""
        self.chunks: list[dict] = json.loads(chunks_path.read_text(encoding="utf-8"))
        self.by_id = {c["id"]: c for c in self.chunks}
        self.embed = embed
        self.bm25 = BM25Okapi([tokens(c["section"] + " " + c["text"]) for c in self.chunks])
        self.vectors = None
        if embed is not None:
            if embeddings_path.exists():
                vectors = np.load(embeddings_path)
            else:  # built once, then reused
                vectors = embed([f"{c['unit_title']}\n{c['text']}" for c in self.chunks])
                np.save(embeddings_path, vectors)
            if len(vectors) != len(self.chunks):
                raise RuntimeError(f"{embeddings_path} does not match chunks.json; delete it to rebuild")
            self.vectors = normalise(np.asarray(vectors, dtype=np.float32))

    @property
    def mode(self) -> str:
        return "semantic" if self.vectors is not None else "keyword"

    def search(self, query: str, unit: int | None = None, k: int = K, trace: dict | None = None) -> list[dict]:
        """trace, if given, is filled with the candidates and their scores (shown as "Behind the answer")."""
        allowed = np.array([unit is None or c["unit"] == unit for c in self.chunks])
        if self.vectors is None:
            scores = np.where(allowed, self.bm25.get_scores(tokens(query)), -np.inf)
            order = [i for i in np.argsort(-scores)[:k] if scores[i] > 0]
            top = scores[order[0]] if order else 1.0
            if trace is not None:
                trace.update(method="bm25", candidates=[self._candidate(i, float(scores[i] / top), r) for r, i in enumerate(order)])
            return [self._hit(i, float(scores[i] / top)) for i in order]

        q = normalise(np.asarray(self.embed([query]), dtype=np.float32))[0]
        sims = np.where(allowed, self.vectors @ q, -np.inf)
        candidates = [int(i) for i in np.argsort(-sims)[:FETCH_K] if np.isfinite(sims[i])]
        chosen = mmr(self.vectors, sims, list(candidates), k)
        if trace is not None:
            trace.update(method="mmr", candidates=[
                self._candidate(i, float(sims[i]), chosen.index(i) if i in chosen else None) for i in candidates])
        return [self._hit(i, float(sims[i])) for i in chosen]

    def _hit(self, i: int, score: float) -> dict:
        return {**self.chunks[i], "score": round(score, 3)}

    def _candidate(self, i: int, score: float, rank: int | None) -> dict:
        c = self.chunks[i]
        return {"id": c["id"], "unit": c["unit"], "page": c["page"], "section": c["section"],
                "score": round(score, 3), "chosen": rank is not None, "rank": None if rank is None else rank + 1}


def normalise(m: np.ndarray) -> np.ndarray:
    return m / np.clip(np.linalg.norm(m, axis=1, keepdims=True), 1e-9, None)


def mmr(vectors: np.ndarray, sims: np.ndarray, candidates: list[int], k: int) -> list[int]:
    """Maximal marginal relevance: relevant to the question, but not repeating each other."""
    chosen: list[int] = []
    while candidates and len(chosen) < k:
        def value(i):
            redundancy = max((float(vectors[i] @ vectors[j]) for j in chosen), default=0.0)
            return MMR_LAMBDA * sims[i] - (1 - MMR_LAMBDA) * redundancy
        best = max(candidates, key=value)
        chosen.append(best)
        candidates.remove(best)
    return chosen
