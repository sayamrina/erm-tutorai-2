"""Turns the 12 ERM lecture PDFs into page-aware chunks (data/chunks.json).

Same chunking as ERM Tutor-AI v4 (1,500 characters, 50 overlap) and the same PDF engine that
Markitdown uses (pdfminer), but read page by page, so every chunk knows its unit, page and slide title.

    python -m app.ingest
"""
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
MATERIALS = DATA / "materials"
CHUNKS = DATA / "chunks.json"

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 50

# Display titles for the course units; the file names contain typos ("Instroduction", "ANNOVA").
UNIT_TITLES = {
    1: "Introduction",
    2: "Quality criteria, structure and content of scientific texts",
    3: "Experiment design",
    4: "Standardized questionnaires",
    5: "Introduction to SPSS",
    6: "P-value and descriptive statistics",
    7: "T-test and ANOVA",
    8: "Regression",
    9: "MANOVA",
    10: "Paired samples ANOVA",
    11: "Non-parametric tests",
    12: "Bias in research",
}


def split_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Paragraph-based splitter that behaves like LangChain's CharacterTextSplitter("\\n\\n")."""
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, current, length = [], [], 0
    for part in parts:
        extra = len(part) + (2 if current else 0)
        if current and length + extra > size:
            chunks.append("\n\n".join(current))
            # keep trailing paragraphs that fit into the overlap
            while current and (length > overlap or length + extra > size):
                length -= len(current[0]) + (2 if len(current) > 1 else 0)
                current.pop(0)
            extra = len(part) + (2 if current else 0)
        current.append(part)
        length += extra
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def clean(text: str) -> str:
    text = text.replace("Ø ", "• ").replace("Ø", "•")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def lines(page: str) -> list[str]:
    return [ln.strip(" •-#*") for ln in page.splitlines() if len(ln.strip(" •-#*")) >= 3 and not ln.strip().isdigit()]


def running_headers(pages: list[str]) -> set[str]:
    """Lines repeated on many slides (course name, lecture title) are headers, not slide titles."""
    counts: dict[str, int] = {}
    for page in pages:
        for line in set(lines(page)[:3]):
            counts[line] = counts.get(line, 0) + 1
    return {line for line, n in counts.items() if n >= 3 and n > len(pages) * 0.3}


def slide_title(page: str, headers: set[str]) -> str:
    for line in lines(page):
        if line not in headers:
            return line[:90]
    return ""


def build() -> list[dict]:
    from pdfminer.high_level import extract_pages, extract_text

    chunks = []
    for pdf in sorted(MATERIALS.glob("*.pdf"), key=lambda p: int(p.name.split(".")[0])):
        unit = int(pdf.name.split(".")[0])
        count = sum(1 for _ in extract_pages(str(pdf)))
        pages = [clean(extract_text(str(pdf), page_numbers=[i])) for i in range(count)]
        headers = running_headers(pages)
        for page_no, page in enumerate(pages, start=1):
            if len(page) < 40:  # title-only or empty slides carry no content
                continue
            title = slide_title(page, headers)
            for i, text in enumerate(split_text(page)):
                chunks.append({
                    "id": f"u{unit:02d}-p{page_no:03d}-{i}",
                    "unit": unit,
                    "unit_title": UNIT_TITLES[unit],
                    "file": pdf.name,
                    "page": page_no,
                    "section": title,
                    "text": text,
                })
    return chunks


if __name__ == "__main__":
    chunks = build()
    CHUNKS.write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")
    units = sorted({c["unit"] for c in chunks})
    print(f"{len(chunks)} chunks from {len(units)} units -> {CHUNKS}")
