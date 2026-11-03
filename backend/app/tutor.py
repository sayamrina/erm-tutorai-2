"""The tutor: grounded answers with numbered citations, and a practice mode with feedback.

Prompt rules are those of ERM Tutor-AI v4 (course materials first, general ERM knowledge second,
refusal for unrelated questions, reflection + answer + follow-up woven into one reply).
New in v2: passages are numbered and the model cites them as [1], [2] …
"""
import json
import random
import re
from collections.abc import Iterator

from .retrieval import Retriever

REFUSAL = ("Sorry, I cannot answer that, because I am ERM Tutor, "
           "I only want you to ask questions related to that.")

TUTOR_PROMPT = f"""You're an AI mentor and tutor for the Empirical Research Methods (ERM) course. When a student asks a question, reply like a supportive human mentor — friendly, encouraging, and natural.

CRITICAL RULES:
1. FIRST PRIORITY: Always check the numbered course passages below. If the answer can be found or inferred from them, you MUST use them as your primary source and base your explanation on them.
2. SECOND PRIORITY: If the information is NOT in the passages, but the question is related to general Empirical Research Methods (ERM) or academic research, you may answer using your reliable academic knowledge.
3. GENERAL IDENTITY: If the student greets you or asks about your identity (e.g., "Who are you?"), reply warmly and conversationally as an ERM tutor.
4. REFUSAL: Only if the question is completely unrelated to academics, research methods, or your role as an ERM tutor, reply strictly with this exact sentence:
"{REFUSAL}"

CITATIONS:
- Put the passage number in square brackets right after each statement that uses it, e.g. "... compares two group means [2]." Several passages: [1][3].
- Cite only passages you actually used. Never cite a passage for knowledge that is not in it.
- No citations in greetings, refusals, or statements from general knowledge.

STYLE:
Provide a natural, conversational, and cohesive response in paragraphs. Include an empathetic reflection, the factual answer, and an engaging follow-up question at the end, but DO NOT use labels, headings, or bullet points like 'Reflection:', 'Answer:', or 'Follow-up:'. Keep it focused and approachable, like talking to a student one-on-one."""

PRACTICE_QUESTION_PROMPT = """You write one practice question for a student of the Empirical Research Methods course.
Base it only on the course passage below. The student should be able to answer it in two to four sentences.
Ask about understanding (why, when, what is the difference), not about slide wording or names of people.
Return JSON: {"question": "..."}"""

FEEDBACK_PROMPT = """You are a supportive tutor for the Empirical Research Methods course. A student answered a practice question.
Judge the answer only against the numbered course passages.

Write the first line exactly as one of:
VERDICT: correct
VERDICT: partly correct
VERDICT: not yet

Then, in two short paragraphs without headings: say what the student got right, then what is missing or wrong and the correct idea, citing passages as [1], [2] right after the statements that use them. End with one concrete thing to review next. Be warm and specific, never vague."""

CITATION = re.compile(r"\[(\d+)\]")
VERDICTS = ("correct", "partly correct", "not yet")


def format_passages(passages: list[dict]) -> str:
    return "\n\n".join(
        f"[{n}] Unit {p['unit']}: {p['unit_title']}, page {p['page']} ({p['section']})\n{p['text']}"
        for n, p in enumerate(passages, start=1)
    )


def cited_numbers(answer: str, available: int) -> list[int]:
    found = {int(n) for n in CITATION.findall(answer)}
    return sorted(n for n in found if 1 <= n <= available)


def source_label(answer: str, cited: list[int]) -> str:
    if REFUSAL.lower()[:28] in answer.lower():
        return "declined"
    return "course" if cited else "general"


def public(p: dict) -> dict:
    return {k: p[k] for k in ("id", "unit", "unit_title", "page", "section", "text", "score")}


class Tutor:
    def __init__(self, retriever: Retriever, client=None, model: str = "gpt-4o"):
        self.retriever = retriever
        self.client = client  # OpenAI client, or None in demo mode
        self.model = model

    def _stream(self, messages: list[dict]) -> Iterator[str]:
        stream = self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=0, stream=True)
        for event in stream:
            if event.choices and event.choices[0].delta.content:
                yield event.choices[0].delta.content

    def ask(self, question: str, unit: int | None = None, history: list[dict] | None = None) -> Iterator[dict]:
        history = (history or [])[-4:]
        # When the student replies to the tutor's follow-up, the follow-up carries the topic.
        context_query = " ".join([m["content"][-300:] for m in history[-1:] if m["role"] == "assistant"] + [question])
        passages = self.retriever.search(context_query, unit=unit)
        yield {"type": "sources", "passages": [public(p) for p in passages]}

        if self.client is None:
            text = self._demo_answer(passages)
            yield {"type": "token", "text": text}
            yield {"type": "done", "label": "demo", "cited": list(range(1, len(passages) + 1)),
                   "words": len(text.split())}
            return

        messages = [{"role": "system", "content": TUTOR_PROMPT + "\n\nCourse passages:\n" + format_passages(passages)}]
        messages += [{"role": m["role"], "content": m["content"]} for m in history if m["role"] in ("user", "assistant")]
        messages.append({"role": "user", "content": question})
        answer = ""
        for piece in self._stream(messages):
            answer += piece
            yield {"type": "token", "text": piece}
        cited = cited_numbers(answer, len(passages))
        yield {"type": "done", "label": source_label(answer, cited), "cited": cited, "words": len(answer.split())}

    @staticmethod
    def _demo_answer(passages: list[dict]) -> str:
        if not passages:
            return "Demo mode: no course passage matches these words. Try terms from the lectures, such as t-test, p-value or validity."
        refs = "".join(f"[{n}]" for n in range(1, len(passages) + 1))
        return ("Demo mode: no language model is connected, so the tutor cannot write an explanation. "
                f"These are the course passages it would answer from {refs}. Open one to read it.")

    def practice_question(self, unit: int, rng: random.Random | None = None) -> dict:
        rng = rng or random.Random()
        pool = [c for c in self.retriever.chunks if c["unit"] == unit and len(c["text"]) >= 300]
        seed = rng.choice(pool)
        response = self.client.chat.completions.create(
            model=self.model, temperature=0.7, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": PRACTICE_QUESTION_PROMPT},
                      {"role": "user", "content": format_passages([seed])}])
        question = json.loads(response.choices[0].message.content)["question"].strip()
        return {"question": question, "unit": unit, "seed_id": seed["id"]}

    def feedback(self, question: str, answer: str, seed_id: str, unit: int) -> Iterator[dict]:
        passages = [{**self.retriever.by_id[seed_id], "score": 1.0}]
        for hit in self.retriever.search(question, unit=unit):
            if hit["id"] != seed_id and len(passages) < 4:
                passages.append(hit)
        yield {"type": "sources", "passages": [public(p) for p in passages]}

        messages = [{"role": "system", "content": FEEDBACK_PROMPT + "\n\nCourse passages:\n" + format_passages(passages)},
                    {"role": "user", "content": f"Question: {question}\n\nStudent answer: {answer}"}]
        buffer, text, verdict_sent = "", "", False
        for piece in self._stream(messages):
            if verdict_sent:
                text += piece
                yield {"type": "token", "text": piece}
                continue
            buffer += piece
            if "\n" in buffer:
                first, rest = buffer.split("\n", 1)
                yield {"type": "verdict", "verdict": parse_verdict(first)}
                verdict_sent, text = True, rest.lstrip()
                if text:
                    yield {"type": "token", "text": text}
        if not verdict_sent:  # the model ignored the format: show everything as feedback
            text = buffer
            yield {"type": "token", "text": buffer}
        yield {"type": "done", "cited": cited_numbers(text, len(passages)), "words": len(text.split())}


def parse_verdict(line: str) -> str | None:
    value = line.lower().replace("verdict:", "").strip(" *.")
    return value if value in VERDICTS else None
