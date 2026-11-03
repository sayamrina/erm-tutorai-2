import json
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.retrieval import Retriever, tokens
from app.tutor import Tutor

VOCAB = ["anova", "t", "test", "regression", "bias", "p", "value", "mean", "variance", "questionnaire"]


def fake_embed(texts):
    """Bag-of-words over a tiny vocabulary: enough to make similarity meaningful in tests."""
    rows = []
    for text in texts:
        words = tokens(text)
        rows.append([words.count(w) for w in VOCAB] + [0.01])
    return np.array(rows, dtype=np.float32)


class FakeChat:
    """Stands in for client.chat.completions; replies are queued per test."""

    def __init__(self):
        self.replies: list[str] = []
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if kwargs.get("stream"):
            return iter(SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=piece))])
                        for piece in [reply[i:i + 7] for i in range(0, len(reply), 7)])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])


@pytest.fixture
def chat():
    return FakeChat()


@pytest.fixture
def tutor(chat, tmp_path):
    client = SimpleNamespace(chat=SimpleNamespace(completions=chat))
    return Tutor(Retriever(fake_embed, embeddings_path=tmp_path / "e.npy"), client)


@pytest.fixture
def api(tutor):
    return TestClient(create_app(tutor))


@pytest.fixture
def demo_api():
    return TestClient(create_app(Tutor(Retriever())))


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
