from __future__ import annotations

import io
from typing import Dict, List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader

from question_bank import GeneratedQuestion, WorkingStep


def _latex_png(latex: str, fontsize: int = 22, dpi: int = 300) -> Image.Image:
    """Render matplotlib mathtext to tight transparent PNG."""
    fig = plt.figure(figsize=(0.01, 0.01), dpi=dpi)
    fig.patch.set_alpha(0.0)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.text(0, 0.5, f"${latex}$", fontsize=fontsize, va="center", ha="left")
    fig.canvas.draw()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, transparent=True, bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def _draw_math(c: canvas.Canvas, latex: str, x: float, y_top: float, max_w: float, target_h: float = 0.78 * cm) -> float:
    img = _latex_png(latex)
    dpi = 300.0
    w_pt = (img.width / dpi) * 72.0
    h_pt = (img.height / dpi) * 72.0

    scale = (target_h / h_pt)
    w = w_pt * scale
    h = h_pt * scale
    if w > max_w:
        scale2 = max_w / w
        w *= scale2
        h *= scale2

    b = io.BytesIO()
    img.save(b, format="PNG")
    b.seek(0)
    c.drawImage(ImageReader(b), x, y_top - h, width=w, height=h, mask="auto")
    return h


def _draw_png(c: canvas.Canvas, png_bytes: bytes, x: float, y_top: float, max_w: float, max_h: float, assumed_dpi: float = 300.0) -> float:
    """Draw a PNG image scaled to fit within max_w/max_h (points). Returns height used."""
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    w_pt = (img.width / assumed_dpi) * 72.0
    h_pt = (img.height / assumed_dpi) * 72.0

    scale = min(max_w / w_pt, max_h / h_pt)
    w = w_pt * scale
    h = h_pt * scale

    b = io.BytesIO()
    img.save(b, format="PNG")
    b.seek(0)
    c.drawImage(ImageReader(b), x, y_top - h, width=w, height=h, mask="auto")
    return h


def _draw_wrapped_text(c: canvas.Canvas, text: str, x: float, y_top: float, max_w: float, font: str, size: int, leading: float) -> float:
    c.setFont(font, size)
    # naive word-wrap
    words = text.split()
    lines: List[str] = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if c.stringWidth(test, font, size) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    y = y_top
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y_top - y  # height used


def build_pdf_bytes(title: str, grouped: Dict[str, List[GeneratedQuestion]], seed: int) -> bytes:
    """
    Layout:
    - 2 questions side-by-side per topic (two columns)
    - 5 topics per page
    - Questions pages, then Answers pages
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    margin = 1.3 * cm
    col_gap = 0.8 * cm
    col_w = (page_w - 2 * margin - col_gap) / 2

    topics = list(grouped.keys())
    topics_per_page = 5

    def draw_topic_row(y_top: float, topic: str, q_left: GeneratedQuestion, q_right: GeneratedQuestion, show_answers: bool) -> float:
        row_h = (page_h - 2 * margin - 2.0 * cm) / topics_per_page
        # topic label
        c.setFont("Helvetica-Bold", 11)
        c.drawString(margin, y_top, topic)

        # content box top
        y_content = y_top - 0.35 * cm
        # left column
        xL = margin
        xR = margin + col_w + col_gap

        def draw_one(q: GeneratedQuestion, x0: float):
            # prompt
            used = 0.0
            used += _draw_wrapped_text(c, q.prompt, x0, y_content, col_w, "Helvetica", 10, leading=11)
            # latex line (optional)
            y_math_top = y_content - used - 0.15 * cm
            if getattr(q, "diagram_png", None):
                h = _draw_png(c, q.diagram_png, x0, y_math_top, max_w=col_w, max_h=2.85*cm)
                used2 = (0.15 * cm + h)
            elif q.latex.strip():
                h = _draw_math(c, q.latex, x0, y_math_top, max_w=col_w, target_h=0.72*cm)
                used2 = (0.15 * cm + h)
            else:
                used2 = 0.0
            used_total = used + used2

            if show_answers:
                y_ans = y_content - used_total - 0.15 * cm
                c.setFont("Helvetica", 10)
                c.drawString(x0, y_ans, "Answer:")
                _draw_math(c, q.answer_latex, x0 + 1.2 * cm, y_ans + 0.15 * cm, max_w=col_w - 1.2 * cm, target_h=0.68*cm)
            return

        draw_one(q_left, xL)
        draw_one(q_right, xR)

        # horizontal separator
        c.setLineWidth(0.5)
        c.line(margin, y_top - row_h + 0.15*cm, page_w - margin, y_top - row_h + 0.15*cm)
        return y_top - row_h

    def draw_pages(show_answers: bool):
        header = f"{'Answers' if show_answers else 'Worksheet'} – {title}"
        for page_start in range(0, len(topics), topics_per_page):
            c.setFont("Helvetica-Bold", 16)
            c.drawString(margin, page_h - margin, header)
            c.setFont("Helvetica", 9)
            c.drawRightString(page_w - margin, page_h - margin + 2, f"seed: {seed}")

            y = page_h - margin - 1.1 * cm
            page_topics = topics[page_start:page_start + topics_per_page]
            for t in page_topics:
                qs = grouped[t]
                # pad if missing
                q1 = qs[0]
                q2 = qs[1] if len(qs) > 1 else qs[0]
                y = draw_topic_row(y, t, q1, q2, show_answers=show_answers)

            c.showPage()

    draw_pages(show_answers=False)
    draw_pages(show_answers=True)

    c.save()
    buf.seek(0)
    return buf.read()
