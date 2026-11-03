"""Runs the 20 evaluation questions of the thesis (plus three off-topic questions) against a running
ERM Tutor-AI 2 and measures what can be checked without a human rater:

- citation coverage: share of statements that cite at least one course passage
- lexical support: share of cited statements that share at least two content words with the passages
  they cite (a cheap proxy for "the passage says this", not a judgement of correctness)
- unit match: whether a passage from the question's lecture unit was cited
- refusals: whether off-topic questions get the refusal sentence
- answer length, latency, tokens and estimated cost

    python -m eval.run_eval --url https://erm-tutorai-2.onrender.com
"""
import argparse
import json
import re
import statistics
import time
import uuid
from datetime import date
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
STOP = set(("the and for are but not you your with that this from have has was were can will what when which into than "
            "then them they their there these those its it's also more most such only each other some any about between "
            "does use used using how why who all one two may might could would should our out very just like").split())


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z-]{2,}", text.lower()) if w not in STOP}


def statements(answer: str) -> list[str]:
    """Sentences of the answer, without the closing follow-up question."""
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", answer) if s.strip()]
    if parts and parts[-1].endswith("?"):
        parts = parts[:-1]
    return [s for s in parts if len(words(re.sub(r"\[\d+\]", "", s))) >= 3]


def ask(client: httpx.Client, url: str, question: str) -> dict:
    out = {"text": "", "passages": [], "trace": None, "done": None}
    # One session id per question, so the evaluation is not stopped by the per-session demo limit.
    headers = {"X-Session-Id": f"eval-{uuid.uuid4()}"}
    with client.stream("POST", f"{url}/api/ask", json={"question": question}, headers=headers, timeout=120) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            ev = json.loads(line[6:])
            if ev["type"] == "sources":
                out["passages"] = ev["passages"]
            elif ev["type"] == "token":
                out["text"] += ev["text"]
            elif ev["type"] == "trace":
                out["trace"] = ev
            elif ev["type"] == "done":
                out["done"] = ev
            elif ev["type"] == "error":
                raise RuntimeError(ev["message"])
    return out


def score(item: dict, res: dict) -> dict:
    sts = statements(res["text"])
    cited_sts = [s for s in sts if re.search(r"\[\d+\]", s)]
    supported = 0
    for s in cited_sts:
        nums = [int(n) for n in re.findall(r"\[(\d+)\]", s) if 1 <= int(n) <= len(res["passages"])]
        passage_words = set().union(*(words(res["passages"][n - 1]["text"] + " " + res["passages"][n - 1]["section"]) for n in nums)) if nums else set()
        if len(words(re.sub(r"\[\d+\]", "", s)) & passage_words) >= 2:
            supported += 1
    cited = res["done"]["cited"] if res["done"] else []
    cited_units = sorted({res["passages"][n - 1]["unit"] for n in cited})
    trace = res["trace"] or {}
    return {
        "q": item["q"], "question": item["text"], "unit": item.get("unit"),
        "label": res["done"]["label"] if res["done"] else None,
        "words": res["done"]["words"] if res["done"] else len(res["text"].split()),
        "statements": len(sts), "cited_statements": len(cited_sts), "supported_statements": supported,
        "cited_units": cited_units, "unit_match": item.get("unit") in cited_units if item.get("unit") else None,
        "total_ms": trace.get("timings", {}).get("total_ms"), "first_token_ms": trace.get("timings", {}).get("first_token_ms"),
        "tokens": trace.get("tokens"), "cost_usd": trace.get("cost_usd"),
        "answer": res["text"],
    }


def summarise(rows: list[dict], off: list[dict]) -> dict:
    sts = sum(r["statements"] for r in rows)
    cited = sum(r["cited_statements"] for r in rows)
    times = [r["total_ms"] for r in rows if r["total_ms"]]
    return {
        "questions": len(rows),
        "answers_from_course": sum(r["label"] == "course" for r in rows),
        "citation_coverage": round(cited / sts, 3) if sts else None,
        "lexical_support": round(sum(r["supported_statements"] for r in rows) / cited, 3) if cited else None,
        "unit_match": sum(bool(r["unit_match"]) for r in rows),
        "words_mean": round(statistics.mean(r["words"] for r in rows), 1),
        "words_sd": round(statistics.stdev(r["words"] for r in rows), 1),
        "latency_median_s": round(statistics.median(times) / 1000, 2) if times else None,
        "cost_total_usd": round(sum(r["cost_usd"] or 0 for r in rows + off), 4),
        "refusals": f"{sum(r['label'] == 'declined' for r in off)} of {len(off)}",
    }


def report(summary: dict, rows: list[dict], off: list[dict], url: str) -> str:
    s = summary
    lines = [
        f"# Evaluation of ERM Tutor-AI 2, {date.today().isoformat()}", "",
        f"Target: {url}. The 20 evaluation questions of the thesis, each asked once in a fresh conversation, "
        "plus three off-topic questions. Automatic checks only; no human rating.", "",
        "| Check | Result |", "|---|---|",
        f"| Answers based on the course materials | {s['answers_from_course']} of {s['questions']} |",
        f"| Statements with a citation | {s['citation_coverage']:.0%} |",
        f"| Cited statements sharing ≥ 2 content words with the cited passage | {s['lexical_support']:.0%} |",
        f"| A passage from the question's own unit cited | {s['unit_match']} of {s['questions']} |",
        f"| Off-topic questions declined | {s['refusals']} |",
        f"| Answer length | {s['words_mean']} ± {s['words_sd']} words |",
        f"| Median time to full answer | {s['latency_median_s']} s |",
        f"| Total cost of the run (estimate) | ${s['cost_total_usd']} |", "",
        "| Q | Label | Words | Statements cited | Supported | Units cited | Time (s) |", "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['q']} | {r['label']} | {r['words']} | {r['cited_statements']}/{r['statements']} | "
                     f"{r['supported_statements']}/{r['cited_statements']} | {', '.join(map(str, r['cited_units'])) or '–'} | "
                     f"{(r['total_ms'] or 0) / 1000:.1f} |")
    lines += ["", "Off-topic: " + "; ".join(f"{r['q']} {r['label']}" for r in off), ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8096")
    args = parser.parse_args()
    items = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    rows, off = [], []
    with httpx.Client() as client:
        for item in items["course"]:
            rows.append(score(item, ask(client, args.url, item["text"])))
            print(rows[-1]["q"], rows[-1]["label"], rows[-1]["words"], f"{rows[-1]['cited_statements']}/{rows[-1]['statements']}")
            time.sleep(1)
        for item in items["off_topic"]:
            off.append(score(item, ask(client, args.url, item["text"])))
            print(off[-1]["q"], off[-1]["label"])
    summary = summarise(rows, off)
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    stamp = date.today().isoformat()
    (out / f"{stamp}.json").write_text(json.dumps({"url": args.url, "summary": summary, "questions": rows, "off_topic": off},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"{stamp}.md").write_text(report(summary, rows, off, args.url), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
