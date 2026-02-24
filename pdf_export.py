from __future__ import annotations

import io
from typing import List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader

from question_bank import GeneratedQuestion


def _latex_png(latex: str, fontsize: int = 22, dpi: int = 300) -> Image.Image:
    """
    Render mathtext to a tight transparent PNG.
    """
    fig = plt.figure(figsize=(0.01, 0.01), dpi=dpi)
    fig.patch.set_alpha(0.0)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.text(0, 0.5, f"${latex}$", fontsize=fontsize, va="center", ha="left")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, transparent=True, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def _draw_math(c: canvas.Canvas, latex: str, x: float, y_top: float, max_w: float, target_h: float = 0.85 * cm) -> float:
    """
    Draw LaTeX (mathtext) at (x, y_top) with height target_h and width <= max_w.
    Returns rendered height in points.
    """
    img = _latex_png(latex)
    dpi = 300.0
    w_pt = (img.width / dpi) * 72.0
    h_pt = (img.height / dpi) * 72.0

    # Scale to target height, then shrink if too wide
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


def build_pdf_bytes(title: str, questions: List[GeneratedQuestion], seed: int) -> bytes:
    """
    Produces a PDF with:
      - N pages of questions (8 per page)
      - N pages of answers   (8 per page)
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    margin = 1.5 * cm
    col_gap = 1.0 * cm
    col_w = (page_w - 2 * margin - col_gap) / 2

    per_page = 8
    pages = (len(questions) + per_page - 1) // per_page

    def draw_block(header: str, items: List[GeneratedQuestion], page_index: int, show_answers: bool):
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin, page_h - margin, header)
        c.setFont("Helvetica", 9)
        c.drawRightString(page_w - margin, page_h - margin + 2, f"seed: {seed}  •  page {page_index}/{pages}")

        top = page_h - margin - 1.0 * cm
        row_h = (page_h - 2 * margin - 2.0 * cm) / 4  # 4 per column

        for i, q in enumerate(items):
            col = 0 if i < 4 else 1
            row = i if i < 4 else i - 4
            x0 = margin + col * (col_w + col_gap)
            y0 = top - row * row_h

            number = (page_index - 1) * per_page + i + 1
            c.setFont("Helvetica-Bold", 11)
            # q.prompt is LaTeX text, so just show a plain label
            c.drawString(x0, y0, f"{number}.")
            # prompt line as LaTeX
            _draw_math(c, q.prompt, x0 + 0.55 * cm, y0 + 0.15 * cm, max_w=col_w - 0.55 * cm, target_h=0.65 * cm)

            y_math_top = y0 - 0.35 * cm
            h1 = _draw_math(c, q.latex, x0, y_math_top, max_w=col_w)

            if show_answers:
                c.setFont("Helvetica", 10)
                c.drawString(x0, y_math_top - h1 - 0.25 * cm, "Answer:")
                _draw_math(
                    c,
                    q.answer_latex,
                    x0 + 1.4 * cm,
                    y_math_top - h1 - 0.05 * cm,
                    max_w=col_w - 1.4 * cm,
                    target_h=0.75 * cm,
                )

    # Questions pages
    for p in range(pages):
        block = questions[p * per_page : (p + 1) * per_page]
        draw_block(f"Worksheet – {title}", block, p + 1, show_answers=False)
        c.showPage()

    # Answers pages
    for p in range(pages):
        block = questions[p * per_page : (p + 1) * per_page]
        draw_block(f"Answers – {title}", block, p + 1, show_answers=True)
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()
