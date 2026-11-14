"""The tutor: grounded answers with numbered citations, and a practice mode with feedback.

Version 1 (the thesis app) let the model use course materials first and general ERM knowledge second.
Version 2 tightens this: the course passages are the source, every sentence that uses one cites it,
and general knowledge is allowed only for what the passages do not cover, introduced with a fixed marker
so the interface can show it. Refusal sentence and tutor style (reflection, answer, follow-up) are kept.
"""
import json
import random
import re
import time
from collections.abc import Iterator

from .config import settings
from .retrieval import Retriever

REFUSAL = ("Sorry, I cannot answer that, because I am ERM Tutor, "
           "I only want you to ask questions related to that.")

# Sentences from general knowledge start with this marker, so the interface can label them.
GENERAL_MARKER = "Beyond the course slides"

TUTOR_PROMPT = f"""You're an AI mentor and tutor for the Empirical Research Methods (ERM) course. When a student asks a question, reply like a supportive human mentor — friendly, encouraging, and natural.

CRITICAL RULES:
1. THE COURSE PASSAGES ARE YOUR SOURCE: Each question comes with numbered passages from the course slides. Build your explanation from them. If the passages contain or clearly imply the answer, use only them, even if you know more.
2. GENERAL KNOWLEDGE ONLY FOR GAPS: Only if the passages do not cover the question, or a part the student needs, may you add reliable general ERM or academic knowledge. Keep that part short and begin it with "{GENERAL_MARKER}," so the student knows it is not from the course. Never present general knowledge as if it came from the slides.
3. GENERAL IDENTITY: If the student greets you or asks about your identity (e.g., "Who are you?"), reply warmly and conversationally as an ERM tutor.
4. REFUSAL: Only if the question is completely unrelated to academics, research methods, or your role as an ERM tutor, reply strictly with this exact sentence:
"{REFUSAL}"

CITATIONS:
- Every sentence that states something from a passage ends with that passage's number in square brackets, e.g. "... compares two group means [2]." Several passages: [1][3]. Cite sentence by sentence, not once per paragraph.
- Cite only passages that really say what the sentence says. Never cite a passage for general knowledge.
- The opening reflection, the closing follow-up question and sentences after "{GENERAL_MARKER}," carry no citation.
- Check every sentence of the explanation before you write it: it either ends with a passage number, or it belongs to the part that begins with "{GENERAL_MARKER},". A sentence that is neither does not belong in the answer.

EXAMPLE (passages about the t-test and ANOVA):
Great question, choosing the right test is one of the first decisions in an analysis. A t-test compares the means of two groups [1]. With more than two groups or levels, an ANOVA compares all means at once [2]. It does this with an F-value, which is located in an F-distribution to decide significance [2]. {GENERAL_MARKER}, many researchers also report an effect size such as eta squared, which the slides here do not cover. Which design are you working with at the moment?

STYLE:
Provide a natural, conversational, and cohesive response in paragraphs. Include a short empathetic reflection, the factual answer, and an engaging follow-up question at the end, but DO NOT use labels, headings, or bullet points like 'Reflection:', 'Answer:', or 'Follow-up:'. Keep it focused and approachable, like talking to a student one-on-one."""

QUESTION_NOTE = ("Answer the student question below as the ERM tutor, from the numbered course passages.\n"
                 "- Every sentence of the explanation ends with the number of the passage it comes from, e.g. [1], "
                 "even when the sentence before cites the same passage.\n"
                 "- Do not add steps, examples or consequences that the passages do not contain. If the student needs "
                 f"them, put them at the end in a short part that begins with \"{GENERAL_MARKER},\".")

# Structured citations: instead of asking for [n] markers in free text, the answer is a list of statements,
# and the response schema makes every statement name its source, a passage number or "general".
STRUCTURED_NOTE = ("Answer the student question below as the ERM tutor, from the numbered course passages, "
                   "by filling the fields of the response format:\n"
                   "- reflection: one short, warm sentence about the question, without facts.\n"
                   "- statements: the explanation, one sentence per item, each with the number of the passage it comes "
                   "from as source. Use \"general\" only for a sentence that no passage supports, and only if the student "
                   "needs it; put such sentences last. Do not write [n] markers in the text.\n"
                   "- follow_up: one question that keeps the student thinking.\n"
                   "- off_topic: true only if the question is completely unrelated to academics, research methods or "
                   "your role as ERM tutor; then leave the other fields empty.")


def answer_schema(n_passages: int) -> dict:
    sources = [str(n) for n in range(1, n_passages + 1)] + ["general"]
    statement = {"type": "object", "additionalProperties": False, "required": ["text", "source"],
                 "properties": {"text": {"type": "string"}, "source": {"type": "string", "enum": sources}}}
    return {"type": "json_schema", "json_schema": {"name": "tutor_answer", "strict": True, "schema": {
        "type": "object", "additionalProperties": False,
        "required": ["off_topic", "reflection", "statements", "follow_up"],
        "properties": {"off_topic": {"type": "boolean"}, "reflection": {"type": "string"},
                       "statements": {"type": "array", "items": statement}, "follow_up": {"type": "string"}}}}}


def render_structured(data: dict) -> str:
    """Writes a structured answer in the same form as a prompted one: [n] before the full stop,
    general knowledge last and introduced with the marker."""
    if data.get("off_topic"):
        return REFUSAL

    def cite(text: str, source: str) -> str:
        text = CITATION.sub("", text).strip()
        end = text[-1] if text and text[-1] in ".!?" else "."
        return f"{text.rstrip('.!? ')} [{source}]{end}"

    course = [cite(s["text"], s["source"]) for s in data["statements"] if s["source"] != "general"]
    general = [CITATION.sub("", s["text"]).strip() for s in data["statements"] if s["source"] == "general"]
    if general:
        first = general[0]
        if len(first) > 1 and first[1].islower():
            first = first[0].lower() + first[1:]
        general[0] = f"{GENERAL_MARKER}, {first}"
    parts = [data.get("reflection", "").strip(), *course, *general, data.get("follow_up", "").strip()]
    return " ".join(p for p in parts if p)


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
    if not cited:
        return "general"
    return "mixed" if GENERAL_MARKER.lower() in answer.lower() else "course"


def public(p: dict) -> dict:
    return {k: p[k] for k in ("id", "unit", "unit_title", "page", "section", "text", "score")}


def ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def trace_event(retrieval: dict, retrieval_ms: int, meter: dict, started: float, model: str | None) -> dict:
    """What happened behind an answer: candidates, timings, tokens and an estimated cost."""
    usage = meter.get("usage")
    tokens = cost = None
    if usage is not None:
        tokens = {"prompt": usage.prompt_tokens, "completion": usage.completion_tokens}
        cost = round((usage.prompt_tokens * settings.price_input_per_million
                      + usage.completion_tokens * settings.price_output_per_million) / 1e6, 5)
    return {"type": "trace", "model": model, "retrieval": retrieval,
            "timings": {"retrieval_ms": retrieval_ms, "first_token_ms": meter.get("first_token_ms"),
                        "total_ms": ms(started)},
            "tokens": tokens, "cost_usd": cost}


class Tutor:
    def __init__(self, retriever: Retriever, client=None, model: str = "gpt-4o"):
        self.retriever = retriever
        self.client = client  # OpenAI client, or None in demo mode
        self.model = model

    def _stream(self, messages: list[dict], meter: dict | None = None) -> Iterator[str]:
        """Streams the reply; meter collects time to first token and token usage."""
        meter = {} if meter is None else meter
        start = time.perf_counter()
        stream = self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=0, stream=True,
            stream_options={"include_usage": True})
        for event in stream:
            if getattr(event, "usage", None):
                meter["usage"] = event.usage
            if event.choices and event.choices[0].delta.content:
                meter.setdefault("first_token_ms", ms(start))
                yield event.choices[0].delta.content

    def ask(self, question: str, unit: int | None = None, history: list[dict] | None = None,
            citations: str = "prompt") -> Iterator[dict]:
        history = (history or [])[-4:]
        # When the student replies to the tutor's follow-up, the follow-up carries the topic.
        context_query = " ".join([m["content"][-300:] for m in history[-1:] if m["role"] == "assistant"] + [question])
        started, retrieval = time.perf_counter(), {}
        passages = self.retriever.search(context_query, unit=unit, trace=retrieval)
        retrieval_ms = ms(started)
        yield {"type": "sources", "passages": [public(p) for p in passages]}

        if self.client is None:
            text = self._demo_answer(passages)
            yield {"type": "token", "text": text}
            yield trace_event(retrieval, retrieval_ms, {}, started, None)
            yield {"type": "done", "label": "demo", "cited": list(range(1, len(passages) + 1)),
                   "words": len(text.split())}
            return

        # Passages and the citation reminder sit next to the question; at the end of a long
        # system prompt GPT-4o used the passages but often left out the [n] markers.
        messages = [{"role": "system", "content": TUTOR_PROMPT}]
        messages += [{"role": m["role"], "content": m["content"]} for m in history if m["role"] in ("user", "assistant")]
        note = STRUCTURED_NOTE if citations == "structured" else QUESTION_NOTE
        messages.append({"role": "user", "content": f"{note}\n\nCourse passages:\n{format_passages(passages)}\n\nStudent question: {question}"})
        answer, meter = "", {}
        if citations == "structured":
            # Not streamed: the answer is a JSON object that is only usable once complete.
            start = time.perf_counter()
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=0, response_format=answer_schema(len(passages)))
            meter["usage"] = getattr(response, "usage", None)
            meter["first_token_ms"] = ms(start)
            answer = render_structured(json.loads(response.choices[0].message.content))
            yield {"type": "token", "text": answer}
        else:
            for piece in self._stream(messages, meter):
                answer += piece
                yield {"type": "token", "text": piece}
        yield trace_event(retrieval, retrieval_ms, meter, started, self.model)
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
        started, retrieval = time.perf_counter(), {}
        passages = [{**self.retriever.by_id[seed_id], "score": 1.0}]
        for hit in self.retriever.search(question, unit=unit, trace=retrieval):
            if hit["id"] != seed_id and len(passages) < 4:
                passages.append(hit)
        retrieval_ms = ms(started)
        retrieval["seed"] = seed_id  # passage [1] is the slide the question was written from
        yield {"type": "sources", "passages": [public(p) for p in passages]}

        messages = [{"role": "system", "content": FEEDBACK_PROMPT + "\n\nCourse passages:\n" + format_passages(passages)},
                    {"role": "user", "content": f"Question: {question}\n\nStudent answer: {answer}"}]
        buffer, text, verdict_sent, meter = "", "", False, {}
        for piece in self._stream(messages, meter):
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
        yield trace_event(retrieval, retrieval_ms, meter, started, self.model)
        yield {"type": "done", "cited": cited_numbers(text, len(passages)), "words": len(text.split())}


def parse_verdict(line: str) -> str | None:
    value = line.lower().replace("verdict:", "").strip(" *.")
    return value if value in VERDICTS else None
