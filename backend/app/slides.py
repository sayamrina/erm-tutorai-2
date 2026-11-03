"""Renders every lecture slide to a small WebP image (data/slides/u07-p051.webp).

The source panel shows the cited slide as the student saw it in the lecture. Run once at build time:

    python -m app.slides
"""
from .ingest import DATA, MATERIALS

SLIDES = DATA / "slides"
WIDTH = 960


def slide_name(unit: int, page: int) -> str:
    return f"u{unit:02d}-p{page:03d}.webp"


def render() -> int:
    import pypdfium2 as pdfium  # build-time only

    SLIDES.mkdir(exist_ok=True)
    count = 0
    for path in sorted(MATERIALS.glob("*.pdf"), key=lambda p: int(p.name.split(".")[0])):
        unit = int(path.name.split(".")[0])
        pdf = pdfium.PdfDocument(path)
        for i, page in enumerate(pdf, start=1):
            target = SLIDES / slide_name(unit, i)
            if not target.exists():
                image = page.render(scale=WIDTH / page.get_width()).to_pil().convert("RGB")
                image.save(target, "WEBP", quality=72, method=6)
            count += 1
        pdf.close()
    return count


if __name__ == "__main__":
    print(f"{render()} slides -> {SLIDES}")
