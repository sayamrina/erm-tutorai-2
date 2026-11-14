"""Checks whether cited passages support the statements that cite them, with a natural language
inference (NLI) model instead of word overlap.

For every cited statement in a saved run of run_eval.py, the cited passage is the premise and the
statement (without its [n] markers) the hypothesis. The NLI model, which is independent of GPT-4o,
labels the pair as entailment (the passage supports the statement), neutral (the passage does not say
it) or contradiction. A statement that cites several passages counts as supported if one of them
entails it. Slides are terse, so "neutral" often means the slide only implies the statement.

It also writes a blind sample of pairs for a human check: the sheet has no NLI labels, the key does.

    pip install -r eval/requirements-nli.txt
    python -m eval.nli_check results/2026-11-03-v1-prompt.json results/2026-11-03-v2-prompt.json ...
"""
import argparse
import csv
import json
import random
import re
from pathlib import Path

from .run_eval import statements

MODEL = "cross-encoder/nli-deberta-v3-base"
HERE = Path(__file__).resolve().parent
CITE = re.compile(r"\[(\d+)\]")


def pairs(run: dict) -> list[dict]:
    """Every cited statement of a run, with the passages it cites."""
    out = []
    for row in run["questions"]:
        for st in statements(row["answer"]):
            nums = [int(n) for n in CITE.findall(st) if 1 <= int(n) <= len(row["passages"])]
            if nums:
                out.append({"q": row["q"], "statement": CITE.sub("", st).replace(" .", ".").strip(),
                            "passages": [row["passages"][n - 1] for n in sorted(set(nums))]})
    return out


def classify(items: list[dict], batch: int = 8) -> None:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL).eval()
    labels = model.config.id2label
    flat = [(i, p) for i, it in enumerate(items) for p in it["passages"]]
    probs = []
    with torch.no_grad():
        for start in range(0, len(flat), batch):
            chunk = flat[start:start + batch]
            enc = tok([f"{p['section']}. {p['text']}" for _, p in chunk], [items[i]["statement"] for i, _ in chunk],
                      return_tensors="pt", truncation="only_first", max_length=512, padding=True)
            probs += torch.softmax(model(**enc).logits, -1).tolist()
    for it in items:
        it["nli"] = []
    for (i, _), pr in zip(flat, probs):
        items[i]["nli"].append({labels[k]: round(v, 3) for k, v in enumerate(pr)})
    for it in items:
        best = max(it["nli"], key=lambda d: d["entailment"])
        it["label"] = max(best, key=best.get)
        it["entailment"] = best["entailment"]


def summary(items: list[dict]) -> dict:
    n = len(items)
    count = {k: sum(it["label"] == k for it in items) for k in ("entailment", "neutral", "contradiction")}
    return {"cited_statements": n, **{k: round(v / n, 3) if n else None for k, v in count.items()}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+", help="JSON files written by run_eval.py")
    parser.add_argument("--name", default="nli-check")
    parser.add_argument("--sample", type=int, default=30, help="pairs in the blind sheet for a human check")
    args = parser.parse_args()
    results, everything = {}, []
    for path in args.runs:
        run = json.loads(Path(path).read_text(encoding="utf-8"))
        name = Path(path).stem
        items = pairs(run)
        classify(items)
        results[name] = {"summary": summary(items), "pairs": items}
        everything += [{"run": name, **it} for it in items]
        print(name, json.dumps(results[name]["summary"]))

    out = HERE / "results"
    (out / f"{args.name}.json").write_text(json.dumps({"model": MODEL, "runs": results}, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    lines = [f"# NLI check of cited statements ({MODEL})", "",
             "Premise: the cited lecture passage. Hypothesis: the statement without its citation marker. "
             "A statement with several citations counts as supported if one passage entails it. Automatic check; "
             "the model is independent of GPT-4o, but NLI on terse slide text is strict, so neutral often means "
             "'implied, not stated'.", "",
             "| Run | Cited statements | Entailment | Neutral | Contradiction |", "|---|---|---|---|---|"]
    for name, r in results.items():
        s = r["summary"]
        lines.append(f"| {name} | {s['cited_statements']} | {s['entailment']:.0%} | {s['neutral']:.0%} | {s['contradiction']:.0%} |")
    (out / f"{args.name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Blind sample for a human check: the sheet hides run and NLI label; the key keeps them.
    rng = random.Random(14)
    sample = rng.sample(everything, min(args.sample, len(everything)))
    with open(out / f"{args.name}-sheet.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "statement", "cited passage(s)", "supported? (yes / partly / no)"])
        for k, it in enumerate(sample, 1):
            w.writerow([k, it["statement"], "\n---\n".join(f"{p['section']}: {p['text']}" for p in it["passages"]), ""])
    with open(out / f"{args.name}-key.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "run", "q", "nli_label", "entailment"])
        for k, it in enumerate(sample, 1):
            w.writerow([k, it["run"], it["q"], it["label"], it["entailment"]])


if __name__ == "__main__":
    main()
