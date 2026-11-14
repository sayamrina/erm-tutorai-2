import json
import random

from app.ingest import split_text
from app.retrieval import Retriever
from app.tutor import REFUSAL, cited_numbers, parse_verdict, source_label

from .conftest import events, fake_embed


def test_splitter_respects_size_and_keeps_all_text():
    text = "\n\n".join(f"paragraph {i} " + "x" * 300 for i in range(12))
    chunks = split_text(text, size=1500, overlap=50)
    assert all(len(c) <= 1500 for c in chunks)
    assert all(f"paragraph {i} " in text for i in range(12))
    assert sum("paragraph 11 " in c for c in chunks) >= 1


def test_every_unit_has_chunks_with_page_numbers():
    r = Retriever()
    assert {c["unit"] for c in r.chunks} == set(range(1, 13))
    assert all(c["page"] >= 1 and c["text"] for c in r.chunks)


def test_keyword_search_finds_the_right_unit():
    hits = Retriever().search("multiple regression with several predictors")
    assert hits and hits[0]["unit"] == 8


def test_unit_filter_limits_results():
    hits = Retriever().search("test", unit=11)
    assert hits and all(h["unit"] == 11 for h in hits)


def test_semantic_search_returns_k_diverse_hits(tmp_path):
    r = Retriever(fake_embed, embeddings_path=tmp_path / "e.npy")
    hits = r.search("anova variance")
    assert len(hits) == 4
    assert len({h["id"] for h in hits}) == 4
    assert (tmp_path / "e.npy").exists()  # cached for the next start


def test_citations_are_parsed_and_bounded():
    assert cited_numbers("A [1] and B [3][2], not [9].", 4) == [1, 2, 3]
    assert source_label("Means differ [2].", [2]) == "course"
    assert source_label("Generally speaking ...", []) == "general"
    assert source_label(REFUSAL, []) == "declined"
    assert source_label("Means differ [2]. Beyond the course slides, effect sizes help.", [2]) == "mixed"


def test_ask_streams_sources_tokens_and_label(api, chat):
    chat.replies.append("Great question! ANOVA compares more than two means [1]. What would you test next?")
    ev = events(api.post("/api/ask", json={"question": "What is an ANOVA?"}))
    assert ev[0]["type"] == "sources" and len(ev[0]["passages"]) == 4
    text = "".join(e["text"] for e in ev if e["type"] == "token")
    assert text.startswith("Great question!")
    assert ev[-1] == {"type": "done", "label": "course", "cited": [1], "words": 14}


def test_structured_citations_give_every_statement_a_source(api, chat):
    chat.replies.append(json.dumps({"off_topic": False, "reflection": "Good question.", "follow_up": "Which test fits your data?",
                                    "statements": [{"text": "ANOVA compares more than two means [3].", "source": "1"},
                                                   {"text": "It uses the F-value", "source": "2"},
                                                   {"text": "Effect sizes are often reported too.", "source": "general"}]}))
    ev = events(api.post("/api/ask", json={"question": "What is an ANOVA?", "citations": "structured"}))
    text = "".join(e["text"] for e in ev if e["type"] == "token")
    assert text == ("Good question. ANOVA compares more than two means [1]. It uses the F-value [2]. "
                    "Beyond the course slides, effect sizes are often reported too. Which test fits your data?")
    schema = chat.calls[0]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["statements"]["items"]["properties"]["source"]["enum"] == ["1", "2", "3", "4", "general"]
    assert ev[-1]["label"] == "mixed" and ev[-1]["cited"] == [1, 2]


def test_structured_off_topic_gives_the_refusal(api, chat):
    chat.replies.append(json.dumps({"off_topic": True, "reflection": "", "statements": [], "follow_up": ""}))
    ev = events(api.post("/api/ask", json={"question": "Best pizza in town?", "citations": "structured"}))
    assert ev[-1]["label"] == "declined"


def test_prompt_keeps_refusal_and_history(api, chat):
    chat.replies.append("Sure [1].")
    api.post("/api/ask", json={"question": "and for paired data?", "history": [
        {"role": "user", "content": "What is a t-test?"},
        {"role": "assistant", "content": "It compares two means. Do you know the paired version?"}]})
    messages = chat.calls[0]["messages"]
    assert REFUSAL in messages[0]["content"] and "[1] Unit" in messages[-1]["content"]
    assert "Beyond the course slides" in messages[0]["content"] and "sentence by sentence" in messages[0]["content"]
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert chat.calls[0]["temperature"] == 0


def test_practice_question_and_feedback(tutor, chat):
    chat.replies.append('{"question": "Why do we use a control group?"}')
    q = tutor.practice_question(3, random.Random(1))
    assert q["question"] == "Why do we use a control group?" and q["seed_id"].startswith("u03-")

    chat.replies.append("VERDICT: partly correct\nYou named the comparison [1]. Missing: random assignment [2].")
    ev = list(tutor.feedback(q["question"], "To compare.", q["seed_id"], 3))
    assert ev[0]["passages"][0]["id"] == q["seed_id"]
    assert {"type": "verdict", "verdict": "partly correct"} in ev
    assert "".join(e["text"] for e in ev if e["type"] == "token").startswith("You named")
    assert ev[-1]["cited"] == [1, 2]


def test_parse_verdict():
    assert parse_verdict("VERDICT: not yet") == "not yet"
    assert parse_verdict("**Verdict: correct**") == "correct"
    assert parse_verdict("Nice try") is None


def test_demo_mode_answers_with_passages_only(demo_api):
    assert demo_api.get("/api/health").json()["mode"] == "demo"
    ev = events(demo_api.post("/api/ask", json={"question": "Mann-Whitney U test"}))
    assert ev[0]["passages"] and ev[-1]["label"] == "demo"
    assert demo_api.post("/api/practice/question", json={"unit": 3}).status_code == 409


def test_units_and_passages(demo_api):
    units = demo_api.get("/api/units").json()
    assert len(units) == 12 and units[6]["title"] == "T-test and ANOVA"
    assert demo_api.get("/api/passages/u08-p002-0").status_code in (200, 404)
    assert demo_api.get("/api/passages/nope").status_code == 404


def test_rate_limit(api, chat, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "session_limit_per_hour", 1)
    chat.replies += ["One [1].", "Two [1]."]
    headers = {"x-session-id": "s1"}
    assert api.post("/api/ask", json={"question": "t-test"}, headers=headers).status_code == 200
    assert api.post("/api/ask", json={"question": "t-test"}, headers=headers).status_code == 429


def test_trace_shows_candidates_timings_and_cost(api, chat):
    chat.replies.append("ANOVA compares means [1].")
    ev = events(api.post("/api/ask", json={"question": "anova variance"}))
    trace = next(e for e in ev if e["type"] == "trace")
    assert trace["retrieval"]["method"] == "mmr"
    chosen = [c for c in trace["retrieval"]["candidates"] if c["chosen"]]
    assert len(chosen) == 4 and sorted(c["rank"] for c in chosen) == [1, 2, 3, 4]
    assert [c["id"] for c in sorted(chosen, key=lambda c: c["rank"])] == [p["id"] for p in ev[0]["passages"]]
    assert trace["timings"]["total_ms"] >= trace["timings"]["retrieval_ms"] >= 0
    assert ev[-1]["type"] == "done"


def test_rating_is_accepted_and_validated(api, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.RATINGS", tmp_path / "ratings.jsonl")
    ok = api.post("/api/rating", json={"rating": "up", "kind": "answer", "question": "q", "answer": "a [1]", "cited": [1]})
    assert ok.status_code == 204
    assert '"rating": "up"' in (tmp_path / "ratings.jsonl").read_text()
    assert api.post("/api/rating", json={"rating": "meh", "kind": "answer", "question": "q", "answer": "a"}).status_code == 422


def test_health_allows_the_start_page_on_github_pages(demo_api):
    r = demo_api.get("/api/health", headers={"Origin": "https://sayamrina.github.io"})
    assert r.headers["access-control-allow-origin"] == "https://sayamrina.github.io"
