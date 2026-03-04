from __future__ import annotations

import hashlib
import io
import random
import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

# -----------------------------
# Helpers (formatting)
# -----------------------------

WorkingStep = Tuple[str, str]  # ("text"|"math", content)


def _fmt_int(n: int) -> str:
    return str(n)


def _fmt_frac(fr: Fraction) -> str:
    fr = fr.limit_denominator()
    if fr.denominator == 1:
        return str(fr.numerator)
    return rf"\\frac{{{fr.numerator}}}{{{fr.denominator}}}"


def _fmt_coef(coef: int, var: str = "x") -> str:
    """Format ax with no '1x'."""
    if coef == 0:
        return "0"
    if coef == 1:
        return var
    if coef == -1:
        return f"-{var}"
    return f"{coef}{var}"


def _lin_expr(a: int, b: int, var: str = "x") -> str:
    """Return LaTeX for ax + b with clean formatting."""
    if a == 0:
        return _fmt_int(b)
    ax = _fmt_coef(a, var)
    if b == 0:
        return ax
    return f"{ax} {'+' if b > 0 else '-'} {abs(b)}"


def _sequence_str(seq: List[int]) -> str:
    # Use thin-spaces (\,) between terms to avoid accidental line-breaks
    return ",\\,".join(str(x) for x in seq) + r",\\,\\ldots"


def _sanitize_math(s: str) -> str:
    """Sanitise LaTeX so it works in both Streamlit (KaTeX) and Matplotlib mathtext."""
    return (
        s.replace("\t", " ")
        .replace("\x0c", "")
        .replace("\\\\", "\\")
        .replace("\\tfrac", "\\frac")
        .replace("\\dfrac", "\\frac")
    )


def _sig(prompt: str, latex: str, diagram_png: Optional[bytes]) -> Tuple[str, str, str]:
    """Signature used to prevent identical pairs in a topic."""
    d = hashlib.md5(diagram_png).hexdigest() if diagram_png else ""
    return (prompt.strip(), latex.strip(), d)


# -----------------------------
# Diagram helpers (PIL)
# -----------------------------

_BG = (255, 255, 255)
_FG = (0, 0, 0)


def _text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    """Return (w, h) for text using the provided font."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return (bbox[2] - bbox[0], bbox[3] - bbox[1])
    except Exception:
        return draw.textsize(text, font=font)


def _label(draw: ImageDraw.ImageDraw, xy: Tuple[float, float], text: str, font: ImageFont.ImageFont):
    """Draw plain label text (GCSE worksheet style: no arrowheads, no dimension lines)."""
    x, y = xy
    draw.text((int(round(x)), int(round(y))), text, fill=_FG, font=font)


def _label_center(draw: ImageDraw.ImageDraw, center: Tuple[float, float], text: str, font: ImageFont.ImageFont):
    """Draw plain label text centred at (x, y)."""
    cx, cy = center
    w, h = _text_bbox(draw, text, font)
    _label(draw, (cx - w / 2, cy - h / 2), text, font)



def _arrowhead(draw: ImageDraw.ImageDraw, tip: Tuple[float, float], direction: Tuple[float, float], size: int = 8):
    """Draw a simple filled triangular arrowhead."""
    tx, ty = tip
    dx, dy = direction
    mag = (dx * dx + dy * dy) ** 0.5
    if mag == 0:
        return
    dx /= mag
    dy /= mag
    px, py = -dy, dx
    base_x = tx - dx * size
    base_y = ty - dy * size
    left = (base_x + px * (size * 0.6), base_y + py * (size * 0.6))
    right = (base_x - px * (size * 0.6), base_y - py * (size * 0.6))
    draw.polygon([(tx, ty), left, right], fill=_FG)


def _dim_h(draw: ImageDraw.ImageDraw, x0: float, x1: float, y: float, offset: float, label: str,
           font: ImageFont.ImageFont, tick: int = 8, lw: int = 2):
    """Horizontal dimension line with arrowheads and label."""
    if x1 < x0:
        x0, x1 = x1, x0
    yy = y + offset
    draw.line([(x0, y), (x0, yy)], fill=_FG, width=lw)
    draw.line([(x1, y), (x1, yy)], fill=_FG, width=lw)
    draw.line([(x0, yy), (x1, yy)], fill=_FG, width=lw)
    _arrowhead(draw, (x0, yy), (1, 0), size=tick)
    _arrowhead(draw, (x1, yy), (-1, 0), size=tick)
    w, h = _text_bbox(draw, label, font)
    _label(draw, ((x0 + x1) / 2 - w / 2, yy - h - 6), label, font)


def _dim_v(draw: ImageDraw.ImageDraw, y0: float, y1: float, x: float, offset: float, label: str,
           font: ImageFont.ImageFont, tick: int = 8, lw: int = 2):
    """Vertical dimension line with arrowheads and label."""
    if y1 < y0:
        y0, y1 = y1, y0
    xx = x + offset
    draw.line([(x, y0), (xx, y0)], fill=_FG, width=lw)
    draw.line([(x, y1), (xx, y1)], fill=_FG, width=lw)
    draw.line([(xx, y0), (xx, y1)], fill=_FG, width=lw)
    _arrowhead(draw, (xx, y0), (0, 1), size=tick)
    _arrowhead(draw, (xx, y1), (0, -1), size=tick)
    w, h = _text_bbox(draw, label, font)
    _label(draw, (xx + 6, (y0 + y1) / 2 - h / 2), label, font)


def _dashed_line(draw: ImageDraw.ImageDraw, p0: Tuple[float, float], p1: Tuple[float, float], dash: int = 8,
                 gap: int = 6, lw: int = 2):
    """Draw a dashed line between two points."""
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    dist = (dx * dx + dy * dy) ** 0.5
    if dist == 0:
        return
    ux, uy = dx / dist, dy / dist
    cur = 0.0
    while cur < dist:
        seg = min(dash, dist - cur)
        sx0 = x0 + ux * cur
        sy0 = y0 + uy * cur
        sx1 = x0 + ux * (cur + seg)
        sy1 = y0 + uy * (cur + seg)
        draw.line([(sx0, sy0), (sx1, sy1)], fill=_FG, width=lw)
        cur += dash + gap


def _default_font(size: int = 40, bold: bool = False):
    """Reliable font loader for diagram labels.

    Streamlit Cloud can miss system fonts; Matplotlib ships with DejaVu fonts.
    """
    try:
        from matplotlib import font_manager as fm

        fp = fm.FontProperties(family="DejaVu Sans", weight=("bold" if bold else "normal"))
        path = fm.findfont(fp, fallback_to_default=True)
        return ImageFont.truetype(path, size=size)
    except Exception:
        try:
            fname = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
            return ImageFont.truetype(fname, size=size)
        except Exception:
            return ImageFont.load_default()


def _img_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _rectilinear_notch_diagram(W: str, H: str, L1: str, w: str, L2: str, d: str) -> bytes:
    """Rectilinear notch shape labelled in the same style as the provided EPP examples.

    Labels are placed adjacent to the relevant edges (no arrows / no dimension lines).
    """
    img = Image.new("RGB", (870, 420), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(40)

    x0, y0 = 105, 345
    x1, y1 = 765, 82

    total_w = x1 - x0
    notch_w = int(total_w * 0.22)
    notch_left = x0 + int(total_w * 0.36)
    notch_d = 105

    p0 = (x0, y0)
    p1 = (x1, y0)
    p2 = (x1, y1)
    p3 = (notch_left + notch_w, y1)
    p4 = (notch_left + notch_w, y1 + notch_d)
    p5 = (notch_left, y1 + notch_d)
    p6 = (notch_left, y1)
    p7 = (x0, y1)

    pts = [p0, p1, p2, p3, p4, p5, p6, p7, p0]
    draw.line(pts, fill=_FG, width=4)

    _label_center(draw, ((p0[0] + p1[0]) / 2, y0 + 30), W, font)
    _label_center(draw, (x0 - 57, (p7[1] + p0[1]) / 2), H, font)
    _label_center(draw, ((p7[0] + p6[0]) / 2, y1 - 33), L1, font)
    _label_center(draw, ((p3[0] + p2[0]) / 2, y1 - 33), L2, font)
    _label_center(draw, ((p5[0] + p4[0]) / 2, p5[1] - 33), w, font)
    _label_center(draw, (p3[0] - 42, (p3[1] + p4[1]) / 2), d, font)

    return _img_bytes(img)

def _rectangle_diagram(L: str, W: str) -> bytes:
    """Axis-aligned rectangle with GCSE worksheet-style labels (no arrows)."""
    img = Image.new("RGB", (630, 330), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(40)

    x0, y0 = 105, 270
    x1, y1 = 525, 90
    draw.rectangle([x0, y1, x1, y0], outline=_FG, width=4)

    _label_center(draw, ((x0 + x1) / 2, y1 - 33), L, font)
    _label_center(draw, (x0 - 42, (y0 + y1) / 2), W, font)

    return _img_bytes(img)


def _rectangle_with_diagonal_diagram(L_top: str, W_left: str, diag_label: str) -> bytes:
    """Rectangle with a diagonal and GCSE worksheet-style labels (no arrows).

    L_top: label for the top edge
    W_left: label for the left edge
    diag_label: label placed just off the diagonal (e.g. x or 13)
    """
    img = Image.new("RGB", (660, 360), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(40)

    x0, y0 = 120, 285
    x1, y1 = 540, 90
    draw.rectangle([x0, y1, x1, y0], outline=_FG, width=4)

    # Diagonal from bottom-left to top-right
    draw.line([(x0, y0), (x1, y1)], fill=_FG, width=4)

    # Edge labels
    if L_top:
        _label_center(draw, ((x0 + x1) / 2, y1 - 33), L_top, font)
    if W_left:
        _label_center(draw, (x0 - 42, (y0 + y1) / 2), W_left, font)

    # Diagonal label: offset away from the rectangle centre to avoid touching the line
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    vx, vy = (x1 - x0), (y1 - y0)
    nx, ny = vy, -vx
    # Ensure normal points away from rectangle centre
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    # n currently arbitrary; choose direction so that (centre-mid) dot n < 0 (push outwards)
    if ((cx - mx) * nx + (cy - my) * ny) > 0:
        nx, ny = -nx, -ny
    nmag = (nx * nx + ny * ny) ** 0.5
    if nmag == 0:
        nmag = 1.0
    nx, ny = nx / nmag, ny / nmag
    # Bigger offset to prevent the diagonal running through wide labels (e.g. '10').
    off = 78
    _label_center(draw, (mx + nx * off, my + ny * off), diag_label, font)

    return _img_bytes(img)


def _isosceles_height_diagram(equal_side: str, base: str, height_label: str) -> bytes:
    """Isosceles triangle with a dashed perpendicular height from the apex.

    Designed for Pythagoras-in-context questions (e.g. find the height).
    """
    img = Image.new("RGB", (690, 390), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(40)

    A = (150, 300)
    B = (540, 300)
    C = (345, 90)
    draw.line([A, B, C, A], fill=_FG, width=4)

    # Height (dashed)
    foot = (C[0], A[1])
    _dashed_line(draw, C, foot, dash=10, gap=9, lw=3)

    # Right-angle marker
    ra = 16
    # Full right-angle "box" (3 sides) for clarity
    draw.line([(foot[0], foot[1]), (foot[0] - ra, foot[1])], fill=_FG, width=3)
    draw.line([(foot[0] - ra, foot[1]), (foot[0] - ra, foot[1] - ra)], fill=_FG, width=3)
    draw.line([(foot[0] - ra, foot[1] - ra), (foot[0], foot[1] - ra)], fill=_FG, width=3)

    # Labels
    _label_center(draw, ((A[0] + B[0]) / 2, A[1] + 32), base, font)

    # Equal side labels (place slightly outward from each sloping side)
    # Left side (A-C)
    mx1, my1 = (A[0] + C[0]) / 2, (A[1] + C[1]) / 2
    vx1, vy1 = (C[0] - A[0]), (C[1] - A[1])
    nx1, ny1 = vy1, -vx1
    # Push away from triangle centre
    cx, cy = (A[0] + B[0] + C[0]) / 3, (A[1] + B[1] + C[1]) / 3
    if ((cx - mx1) * nx1 + (cy - my1) * ny1) > 0:
        nx1, ny1 = -nx1, -ny1
    mag1 = (nx1 * nx1 + ny1 * ny1) ** 0.5 or 1.0
    nx1, ny1 = nx1 / mag1, ny1 / mag1
    _label_center(draw, (mx1 + nx1 * 28, my1 + ny1 * 28), equal_side, font)

    # Right side (B-C)
    mx2, my2 = (B[0] + C[0]) / 2, (B[1] + C[1]) / 2
    vx2, vy2 = (C[0] - B[0]), (C[1] - B[1])
    nx2, ny2 = vy2, -vx2
    if ((cx - mx2) * nx2 + (cy - my2) * ny2) > 0:
        nx2, ny2 = -nx2, -ny2
    mag2 = (nx2 * nx2 + ny2 * ny2) ** 0.5 or 1.0
    nx2, ny2 = nx2 / mag2, ny2 / mag2
    _label_center(draw, (mx2 + nx2 * 28, my2 + ny2 * 28), equal_side, font)

    # Height label (placed to the right of the dashed line)
    _label_center(draw, (foot[0] + 34, (C[1] + foot[1]) / 2), height_label, font)

    return _img_bytes(img)

def _triangle_diagram(base: str, height: str) -> bytes:
    """Triangle with dashed perpendicular height and clear labels (no arrows)."""
    img = Image.new("RGB", (630, 360), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(40)

    A = (120, 285)
    B = (510, 285)
    C = (390, 105)

    draw.line([A, B, C, A], fill=_FG, width=4)

    foot = (C[0], A[1])
    _dashed_line(draw, C, foot, dash=10, gap=9, lw=3)

    ra = 15
    draw.line([(foot[0], foot[1]), (foot[0] - ra, foot[1]), (foot[0] - ra, foot[1] - ra)], fill=_FG, width=3)

    _label_center(draw, ((A[0] + B[0]) / 2, A[1] + 30), base, font)
    _label_center(draw, (foot[0] + 48, (C[1] + foot[1]) / 2), height, font)

    return _img_bytes(img)

def _parallelogram_diagram(base: str, height: str) -> bytes:
    """Parallelogram with dashed perpendicular height and simple labels."""
    img = Image.new("RGB", (690, 360), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(40)

    A = (165, 285)
    B = (540, 285)
    D = (105, 120)
    C = (480, 120)

    draw.line([A, B, C, D, A], fill=_FG, width=4)

    foot = (D[0], A[1])
    _dashed_line(draw, D, foot, dash=10, gap=9, lw=3)

    ra = 15
    draw.line([(foot[0], foot[1]), (foot[0] + ra, foot[1]), (foot[0] + ra, foot[1] - ra)], fill=_FG, width=3)

    _label_center(draw, ((A[0] + B[0]) / 2, A[1] + 30), base, font)
    _label_center(draw, (foot[0] + 51, (D[1] + foot[1]) / 2), height, font)

    return _img_bytes(img)

def _trapezium_diagram(a: str, b: str, h: str) -> bytes:
    """Trapezium with parallel sides a (top) and b (bottom) and dashed perpendicular height."""
    img = Image.new("RGB", (720, 390), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(40)

    A = (180, 300)
    B = (570, 300)
    D = (240, 120)
    C = (480, 120)

    draw.line([A, B, C, D, A], fill=_FG, width=4)

    foot = (D[0], A[1])
    _dashed_line(draw, D, foot, dash=10, gap=9, lw=3)

    ra = 15
    draw.line([(foot[0], foot[1]), (foot[0] + ra, foot[1]), (foot[0] + ra, foot[1] - ra)], fill=_FG, width=3)

    _label_center(draw, ((D[0] + C[0]) / 2, D[1] - 33), a, font)
    _label_center(draw, ((A[0] + B[0]) / 2, A[1] + 30), b, font)
    _label_center(draw, (foot[0] + 51, (D[1] + foot[1]) / 2), h, font)

    return _img_bytes(img)

def _kite_diagram(d1: str, d2: str) -> bytes:
    """Kite/rhombus with dashed diagonals and labels (no arrows)."""
    img = Image.new("RGB", (630, 390), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(40)

    top = (315, 90)
    right = (495, 195)
    bottom = (315, 315)
    left = (135, 195)

    draw.line([top, right, bottom, left, top], fill=_FG, width=4)

    _dashed_line(draw, top, bottom, dash=10, gap=9, lw=3)
    _dashed_line(draw, left, right, dash=10, gap=9, lw=3)

    _label_center(draw, (345, 187), d1, font)
    _label_center(draw, (255, 225), d2, font)

    return _img_bytes(img)


def _pythagoras_triangle_diagram(a_label: str, b_label: str, c_label: str, orientation: str = "BL") -> bytes:
    """Right-angled triangle diagram for Pythagoras' theorem.

    Labels are placed adjacent to the relevant edges (no arrows / no dimension lines),
    consistent with the worksheet-style labelling used elsewhere in this project.

    Side mapping (for all orientations):
    - a_label labels the leg AC
    - b_label labels the leg AB
    - c_label labels the hypotenuse BC

    orientation options:
    - "BL": right angle at bottom-left (default)
    - "BR": right angle at bottom-right
    - "TL": right angle at top-left
    - "TR": right angle at top-right
    - "HB": right angle at the top (hypotenuse appears as the base)
    """
    img = Image.new("RGB", (700, 440), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(44)

    if orientation == "BL":
        A, B, C = (160, 350), (560, 350), (160, 90)
    elif orientation == "BR":
        A, B, C = (560, 350), (160, 350), (560, 90)
    elif orientation == "TL":
        A, B, C = (160, 90), (560, 90), (160, 350)
    elif orientation == "TR":
        A, B, C = (560, 90), (160, 90), (560, 350)
    elif orientation == "HB":
        # Hypotenuse is the horizontal base (B-C)
        A, B, C = (360, 90), (160, 350), (560, 350)
    else:
        A, B, C = (160, 350), (560, 350), (160, 90)

    # Triangle
    draw.line([A, B, C, A], fill=_FG, width=4)

    # Right-angle marker at A (draw 3 sides of a small square)
    def _unit(P, Q):
        dx, dy = (Q[0] - P[0]), (Q[1] - P[1])
        mag = (dx * dx + dy * dy) ** 0.5 or 1.0
        return dx / mag, dy / mag

    ux, uy = _unit(A, B)
    vx, vy = _unit(A, C)
    s = 28
    p1 = (A[0] + ux * s, A[1] + uy * s)
    p2 = (p1[0] + vx * s, p1[1] + vy * s)
    p3 = (A[0] + vx * s, A[1] + vy * s)
    draw.line([A, p1, p2, p3], fill=_FG, width=3)

    # Label placement helper: push labels away from the triangle centroid
    cx, cy = (A[0] + B[0] + C[0]) / 3, (A[1] + B[1] + C[1]) / 3

    def _place_on_segment(P, Q, label: str, offset: float):
        if label == "":
            return
        mx, my = (P[0] + Q[0]) / 2, (P[1] + Q[1]) / 2
        vx0, vy0 = (Q[0] - P[0]), (Q[1] - P[1])
        nx, ny = vy0, -vx0
        # choose outward normal (away from centroid)
        if ((cx - mx) * nx + (cy - my) * ny) > 0:
            nx, ny = -nx, -ny
        nmag = (nx * nx + ny * ny) ** 0.5 or 1.0
        nx, ny = nx / nmag, ny / nmag
        _label_center(draw, (mx + nx * offset, my + ny * offset), label, font)

    # Legs: slightly smaller offset; hypotenuse: larger offset for clear white space
    _place_on_segment(A, C, a_label, 44)
    _place_on_segment(A, B, b_label, 44)
    _place_on_segment(B, C, c_label, 66)

    return _img_bytes(img)

@dataclass(frozen=True)
class GeneratedQuestion:
    qid: str
    topic: str
    level_id: str
    level_name: str
    difficulty: int
    prompt: str
    latex: str
    answer_latex: str
    working: List[WorkingStep]
    template_id: str
    seed: int
    diagram_png: Optional[bytes] = None


@dataclass(frozen=True)
class Template:
    template_id: str
    topic: str
    level_id: str
    level_name: str
    difficulty: int
    generator: Callable[[random.Random, int, Optional[Dict[str, Any]]], Tuple]
    pair_params_factory: Optional[Callable[[random.Random], Dict[str, Any]]] = None


# -----------------------------
# Generators
# -----------------------------

# --- Continuing sequences ---

def _gen_seq_add(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    d = int(params["d"]) if params and "d" in params else rng.choice([2, 3, 4, 5, 6, 7, 8, 9, 10])
    a1 = rng.randint(-20, 30)
    seq = [a1 + i * d for i in range(5)]
    nxt = [seq[-1] + d, seq[-1] + 2 * d]
    prompt = "Write the next two terms:"
    latex = _sequence_str(seq)
    answer = f"{nxt[0]},\\, {nxt[1]}"
    working = [
        ("text", f"The common difference is {d}."),
        ("math", rf"{seq[-1]}+{d}={nxt[0]}\\quad {nxt[0]}+{d}={nxt[1]}"),
    ]
    return prompt, latex, answer, working


def _gen_seq_sub(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    s = int(params["s"]) if params and "s" in params else rng.choice([2, 3, 4, 5, 6, 7, 8, 9, 10])
    d = -s
    a1 = rng.randint(-10, 60)
    seq = [a1 + i * d for i in range(5)]
    nxt = [seq[-1] + d, seq[-1] + 2 * d]
    prompt = "Write the next two terms:"
    latex = _sequence_str(seq)
    answer = f"{nxt[0]},\\, {nxt[1]}"
    working = [
        ("text", f"The common difference is {d}."),
        ("math", rf"{seq[-1]}{d}={nxt[0]}\\quad {nxt[0]}{d}={nxt[1]}"),
    ]
    return prompt, latex, answer, working


def _gen_seq_mul(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    r = int(params["r"]) if params and "r" in params else rng.choice([2, 3])

    def ok_start(a1: int) -> bool:
        term5 = a1 * (r ** 4)
        return term5 <= 200

    starts = [1, 2, 3, 4, 5, 6, 8, 9, 10, 12]
    a1 = rng.choice(starts)
    tries = 0
    while not ok_start(a1) and tries < 30:
        a1 = rng.choice(starts)
        tries += 1

    seq = [a1]
    for _ in range(4):
        seq.append(seq[-1] * r)

    nxt = [seq[-1] * r, seq[-1] * r * r]
    prompt = "Write the next two terms:"
    latex = _sequence_str(seq)
    answer = f"{nxt[0]},\\, {nxt[1]}"
    working = [
        ("text", f"Multiply by {r} each time."),
        ("math", rf"{seq[-1]}\times {r}={nxt[0]}\quad {nxt[0]}\times {r}={nxt[1]}"),
    ]
    return prompt, latex, answer, working


def _gen_seq_div(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    r = int(params["r"]) if params and "r" in params else rng.choice([2, 3])

    if r == 2:
        k_choices = [4, 8, 12, 16, 20]
    else:
        k_choices = [9, 18, 27]

    k = rng.choice(k_choices)
    a1 = k * (r ** 4)

    seq = [a1]
    for _ in range(4):
        seq.append(seq[-1] // r)

    nxt = [seq[-1] // r, seq[-1] // (r * r)]
    prompt = "Write the next two terms:"
    latex = _sequence_str(seq)
    answer = f"{nxt[0]},\\, {nxt[1]}"
    working = [
        ("text", f"Divide by {r} each time."),
        ("math", rf"{seq[-1]}\div {r}={nxt[0]}\quad {nxt[0]}\div {r}={nxt[1]}"),
    ]
    return prompt, latex, answer, working


def _gen_seq_fibo(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    a = rng.randint(1, 12)
    b = rng.randint(1, 12)
    seq = [a, b]
    for _ in range(3):
        seq.append(seq[-1] + seq[-2])
    nxt1 = seq[-1] + seq[-2]
    nxt2 = nxt1 + seq[-1]
    prompt = "Write the next two terms:"
    latex = _sequence_str(seq)
    answer = f"{nxt1},\\, {nxt2}"
    working = [
        ("text", "Each term is the sum of the previous two terms."),
        ("math", rf"{seq[-2]}+{seq[-1]}={nxt1}\\quad {seq[-1]}+{nxt1}={nxt2}"),
    ]
    return prompt, latex, answer, working


# --- Finding the nth term (difference + 0th term method) ---

def _gen_nth_term_arith(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    d_sign = int(params.get("d_sign", 1)) if params else 1
    a0_sign = int(params.get("a0_sign", 1)) if params else 1

    d_mag = rng.choice([1, 2, 3, 4, 5, 6, 7, 8, 9])
    d = d_sign * d_mag

    a0 = rng.randint(1, 20) * (1 if a0_sign > 0 else -1)

    a1 = a0 + d
    seq = [a0 + n * d for n in range(1, 6)]  # a1..a5

    prompt = "Find the nth term of the sequence:"
    latex = _sequence_str(seq)

    answer = _lin_expr(d, a0, "n")

    d_str = f"{d}" if d >= 0 else f"({d})"
    working = [
        ("text", f"The common difference is {d}."),
        ("math", rf"a_0 = a_1 - d = {a1} - {d_str} = {a0}"),
        ("math", rf"a_n = dn + a_0 = {d}n + {a0}"),
        ("math", rf"a_n = {answer}"),
    ]

    return prompt, latex, answer, working


# --- Using the nth term ---

def _gen_use_nth_find_term(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    a_sign = int(params.get("a_sign", 1)) if params else 1
    A = a_sign * rng.choice([1, 2, 3, 4, 5, 6, 7, 8])
    B = rng.randint(-20, 20)
    n = rng.choice([10, 12, 15, 20, 25])

    expr = _lin_expr(A, B, "n")
    value = A * n + B

    prompt = f"Given the nth term, find the {n}th term:"
    latex = expr
    answer = str(value)

    working = [
        ("math", rf"a_n = {expr}"),
        ("math", rf"a_{{{n}}} = {A}\times {n} {'+' if B>=0 else '-'} {abs(B)} = {value}"),
    ]
    return prompt, latex, answer, working


def _gen_use_nth_find_n(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    a_sign = int(params.get("a_sign", 1)) if params else 1
    A = a_sign * rng.choice([2, 3, 4, 5, 6, 7, 8, 9])
    B = rng.randint(-20, 20)
    n = rng.choice([7, 8, 9, 10, 11, 12, 13, 15, 20])
    target = A * n + B

    expr = _lin_expr(A, B, "n")

    prompt = f"The nth term is shown. Which term is {target}?"
    latex = expr
    answer = rf"n = {n}"

    rhs = target - B
    working = [
        ("math", rf"{expr} = {target}"),
        ("math", rf"{A}n {'+' if B>=0 else '-'} {abs(B)} = {target}"),
        ("math", rf"{A}n = {rhs}"),
        ("math", rf"n = \\frac{{{rhs}}}{{{A}}} = {n}"),
    ]
    return prompt, latex, answer, working


def _gen_use_nth_is_term(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    a_sign = int(params.get("a_sign", 1)) if params else 1
    A = a_sign * rng.choice([2, 3, 4, 5, 6, 7, 8, 9])
    B = rng.randint(-20, 20)
    expr = _lin_expr(A, B, "n")

    n_true = rng.choice([6, 7, 8, 9, 10, 12, 15])
    term = A * n_true + B

    make_yes = rng.random() < 0.6
    if make_yes:
        target = term
    else:
        offset = rng.choice([1, 2, 3, 4, 5, 6, 7, 8, 9])
        divisor = abs(A)
        target = term + offset
        for _ in range(30):
            if (target - B) % divisor != 0:
                break
            target += 1

    prompt = f"The nth term is shown. Is {target} a term?"
    latex = expr

    rhs = target - B
    frac = Fraction(rhs, A)
    frac_tex = _fmt_frac(frac)

    sign = "+" if B >= 0 else "-"

    working: List[WorkingStep] = [
        ("math", rf"{expr} = {target}"),
        ("math", rf"{A}n {sign} {abs(B)} = {target}"),
        ("math", rf"{A}n = {rhs}"),
        ("math", rf"n = \frac{{{rhs}}}{{{A}}} = {frac_tex}"),
    ]

    if frac.denominator == 1 and frac.numerator > 0:
        answer = rf"\mathrm{{Yes}},\ n = {frac.numerator}"
        working.append(("text", "n is a positive integer, so it is a term."))
    else:
        answer = r"\mathrm{No}"
        working.append(("text", "n is not a positive integer, so it is not a term."))

    return prompt, latex, answer, working


# --- Solving 1-step equations ---

def _gen_eq_1_add(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    b = rng.randint(1, 15)
    x = rng.randint(-12, 12)
    c = x + b
    prompt = "Solve the equation:"
    latex = rf"x + {b} = {c}"
    answer = rf"x = {x}"
    working = [
        ("math", latex),
        ("text", f"Subtract {b} from both sides."),
        ("math", rf"x = {c} - {b} = {x}"),
    ]
    return prompt, latex, answer, working


def _gen_eq_1_sub(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    b = rng.randint(1, 15)
    x = rng.randint(-12, 12)
    c = x - b
    prompt = "Solve the equation:"
    latex = rf"x - {b} = {c}"
    answer = rf"x = {x}"
    working = [
        ("math", latex),
        ("text", f"Add {b} to both sides."),
        ("math", rf"x = {c} + {b} = {x}"),
    ]
    return prompt, latex, answer, working


def _gen_eq_1_mul(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    a = rng.choice([2, 3, 4, 5, 6, 7, 8, 9])
    x = rng.randint(-12, 12)
    c = a * x
    prompt = "Solve the equation:"
    latex = rf"{_fmt_coef(a, 'x')} = {c}"
    answer = rf"x = {x}"
    working = [
        ("math", latex),
        ("text", f"Divide both sides by {a}."),
        ("math", rf"x = \\frac{{{c}}}{{{a}}} = {x}"),
    ]
    return prompt, latex, answer, working


def _gen_eq_1_div(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    a = rng.choice([2, 3, 4, 5, 6, 7, 8, 9])
    c = rng.randint(-12, 12)
    x = a * c
    prompt = "Solve the equation:"
    latex = rf"\\frac{{x}}{{{a}}} = {c}"
    answer = rf"x = {x}"
    working = [
        ("math", latex),
        ("text", f"Multiply both sides by {a}."),
        ("math", rf"x = {c}\times {a} = {x}"),
    ]
    return prompt, latex, answer, working


# --- Solving 2-step equations ---

def _gen_eq_2_ax_plus_b(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    b_sign = int(params.get("b_sign", 1)) if params else 1
    a = rng.choice([2, 3, 4, 5, 6, 7, 8, 9])
    b = b_sign * rng.randint(1, 20)
    x = rng.randint(-10, 10)
    c = a * x + b

    prompt = "Solve the equation:"
    latex = rf"{_lin_expr(a, b, 'x')} = {c}"
    answer = rf"x = {x}"

    move = "Subtract" if b > 0 else "Add"
    working = [
        ("math", latex),
        ("text", f"{move} {abs(b)} from both sides."),
        ("math", rf"{_fmt_coef(a,'x')} = {c - b}"),
        ("text", f"Divide both sides by {a}."),
        ("math", rf"x = \\frac{{{c - b}}}{{{a}}} = {x}"),
    ]
    return prompt, latex, answer, working


def _gen_eq_2_a_bracket(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    inside_sign = int(params.get("inside_sign", 1)) if params else 1
    a = rng.choice([2, 3, 4, 5, 6, 7, 8, 9])
    b = inside_sign * rng.randint(1, 12)
    x = rng.randint(-10, 10)
    c = a * (x + b)

    prompt = "Solve the equation:"
    latex = rf"{a}(x {'+' if b>=0 else '-'} {abs(b)}) = {c}"
    answer = rf"x = {x}"

    undo = "Subtract" if b > 0 else "Add"
    working = [
        ("math", latex),
        ("text", f"Divide both sides by {a}."),
        ("math", rf"x {'+' if b>=0 else '-'} {abs(b)} = {c//a}"),
        ("text", f"{undo} {abs(b)} on both sides."),
        ("math", rf"x = {c//a} {'-' if b>0 else '+'} {abs(b)} = {x}"),
    ]
    return prompt, latex, answer, working


# --- Percentages (non-calculator) ---

def _gen_pct_noncalc(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    level = str(params.get("level", "simple")) if params else "simple"

    if level == "simple":
        pct = rng.choice([10, 20, 25, 50])
        amount = rng.choice([40, 60, 80, 120, 160, 200, 240, 320, 360, 400, 480, 600, 720, 800])
    elif level == "five_fifteen":
        pct = rng.choice([5, 15])
        amount = rng.choice([40, 60, 80, 120, 160, 200, 240, 320, 360, 400, 480, 600, 720, 800])
    elif level == "eighths":
        pct = rng.choice([12.5, 37.5])
        amount = rng.choice([80, 120, 160, 200, 240, 320, 400, 480, 560, 640, 720, 800])
    else:
        pct = rng.choice([35, 45, 65])
        amount = rng.choice([120, 160, 200, 240, 280, 320, 360, 400, 440, 480, 520, 600, 640, 720, 800])

    prompt = "Find:"
    latex = rf"{pct}\\%\\ \\mathrm{{of}}\\ {amount}"

    value = amount * (pct / 100)

    if abs(value - round(value)) < 1e-9:
        ans = str(int(round(value)))
    else:
        fr = Fraction(str(value)).limit_denominator()
        if fr.denominator in (2, 4, 5, 8, 10, 20, 25, 50, 100):
            ans = str(float(fr)).rstrip("0").rstrip(".")
        else:
            ans = _fmt_frac(fr)

    working: List[WorkingStep] = []

    if pct in (10, 20, 25, 50):
        if pct == 10:
            working = [("text", "10% is one tenth."), ("math", rf"{amount}\\div 10 = {amount//10}")]
        elif pct == 20:
            working = [
                ("text", "20% is twice 10%."),
                ("math", rf"10\\%:\\ {amount}\\div 10 = {amount//10}"),
                ("math", rf"20\\%:\\ 2\\times {amount//10} = {ans}"),
            ]
        elif pct == 25:
            working = [("text", "25% is a quarter."), ("math", rf"{amount}\\div 4 = {ans}")]
        else:
            working = [("text", "50% is a half."), ("math", rf"{amount}\\div 2 = {ans}")]

    elif pct in (5, 15):
        ten = amount // 10
        five = ten / 2
        five_s = str(five).rstrip("0").rstrip(".")
        working = [
            ("text", "Work out 10% then halve it to get 5%."),
            ("math", rf"10\\%:\\ {amount}\\div 10 = {ten}"),
            ("math", rf"5\\%:\\ {ten}\\div 2 = {five_s}"),
        ]
        if pct == 15:
            working.append(("math", rf"15\\%:\\ {ten} + {five_s} = {ans}"))

    elif pct in (12.5, 37.5):
        eighth = amount // 8
        if pct == 12.5:
            working = [("text", "12.5% is one eighth."), ("math", rf"{amount}\\div 8 = {eighth}")]
        else:
            working = [
                ("text", "37.5% is 3 times 12.5%."),
                ("math", rf"12.5\\%:\\ {amount}\\div 8 = {eighth}"),
                ("math", rf"37.5\\%:\\ 3\\times {eighth} = {ans}"),
            ]

    else:
        ten = amount / 10
        five = ten / 2
        ten_s = str(ten).rstrip("0").rstrip(".")
        five_s = str(five).rstrip("0").rstrip(".")
        parts: List[WorkingStep] = [
            ("text", "Use 10% and 5% to build the percentage."),
            ("math", rf"10\\%:\\ {amount}\\div 10 = {ten_s}"),
            ("math", rf"5\\%:\\ {ten_s}\\div 2 = {five_s}"),
        ]
        if pct == 35:
            parts.append(("math", rf"35\\%:\\ 3\\times {ten_s} + {five_s} = {ans}"))
        elif pct == 45:
            parts.append(("math", rf"45\\%:\\ 4\\times {ten_s} + {five_s} = {ans}"))
        else:
            parts.append(("math", rf"65\\%:\\ 6\\times {ten_s} + {five_s} = {ans}"))
        working = parts

    return prompt, latex, ans, working


# --- Percentages (calculator) ---

def _gen_pct_calc(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    level = str(params.get("level", "int")) if params else "int"
    pct = rng.choice([7, 12, 17, 18, 23, 34, 42, 65]) if level == "int" else rng.choice([12.5, 17.5, 0.5, 2.5, 7.5, 37.5])
    amount = rng.randint(120, 950)

    prompt = "Find (calculator method):"
    latex = rf"{pct}\\%\\ \\mathrm{{of}}\\ {amount}"

    value = amount * float(pct) / 100.0
    ans = f"{value:.2f}".rstrip("0").rstrip(".")

    working = [
        ("text", "Convert the percentage to a decimal then multiply."),
        ("math", rf"{pct}\\% = {float(pct)/100}"),
        ("math", rf"{amount}\\times {float(pct)/100} = {ans}"),
    ]
    return prompt, latex, ans, working


# --- Increase / decrease (non-calculator) ---

def _gen_inc_dec_noncalc(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    inc = str(params.get("direction", "increase")) if params else "increase"
    family = str(params.get("family", "simple")) if params else "simple"

    pct = rng.choice([10, 20, 25]) if family == "simple" else rng.choice([5, 15, 30])
    amount = rng.choice([80, 120, 160, 200, 240, 300, 320, 360, 400, 480, 600, 720])

    prompt = f"{inc.capitalize()} {amount} by {pct}% (non-calculator)."
    latex = ""

    change = amount * pct / 100
    new = amount + change if inc == "increase" else amount - change
    ans = str(int(new))

    steps: List[WorkingStep] = [("text", f"Find {pct}% of {amount}.")]

    if pct == 25:
        delta = amount // 4
        steps.append(("math", rf"25\\%:\\ {amount}\\div 4 = {delta}"))
    else:
        ten = amount // 10
        steps.append(("math", rf"10\\%:\\ {amount}\\div 10 = {ten}"))
        if pct == 5:
            delta = ten // 2
            steps.append(("math", rf"5\\%:\\ {ten}\\div 2 = {delta}"))
        elif pct == 15:
            delta = ten + (ten // 2)
            steps.append(("math", rf"5\\%:\\ {ten}\\div 2 = {ten//2}"))
            steps.append(("math", rf"15\\%:\\ {ten} + {ten//2} = {delta}"))
        elif pct == 20:
            delta = 2 * ten
            steps.append(("math", rf"20\\%:\\ 2\\times {ten} = {delta}"))
        else:
            delta = 3 * ten
            steps.append(("math", rf"30\\%:\\ 3\\times {ten} = {delta}"))

    if inc == "increase":
        steps.append(("text", "Add the change to the original amount."))
        steps.append(("math", rf"{amount} + {delta} = {ans}"))
    else:
        steps.append(("text", "Subtract the change from the original amount."))
        steps.append(("math", rf"{amount} - {delta} = {ans}"))

    return prompt, latex, ans, steps


# --- Increase / decrease (calculator) ---

def _gen_inc_dec_calc(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    direction = str(params.get("direction", "increase")) if params else "increase"
    pct = rng.choice([7, 12, 18, 23, 35, 42])
    amount = rng.randint(120, 900)

    prompt = f"{direction.capitalize()} {amount} by {pct}% (calculator)."
    latex = ""

    multiplier = 1 + pct / 100 if direction == "increase" else 1 - pct / 100
    new = amount * multiplier
    ans = f"{new:.2f}".rstrip("0").rstrip(".")

    working = [
        ("text", "Use a multiplier."),
        ("math", rf"\\mathrm{{Multiplier}} = {multiplier}"),
        ("math", rf"{amount}\\times {multiplier} = {ans}"),
    ]

    return prompt, latex, ans, working


# --- Completing the square ---

def _gen_complete_square_a1(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    parity = str(params.get("b_parity", "even")) if params else "even"

    b = rng.choice([-10, -8, -6, -4, -2, 2, 4, 6, 8, 10]) if parity == "even" else rng.choice([-9, -7, -5, -3, -1, 1, 3, 5, 7, 9])
    c = rng.randint(-12, 20)

    prompt = "Complete the square:"
    expr = rf"x^2 {'+' if b>0 else '-'} {abs(b)}x" + (f" {'+' if c>=0 else '-'} {abs(c)}" if c != 0 else "")

    half = Fraction(b, 2)
    bracket = rf"(x {'+' if half>0 else '-'} {_fmt_frac(abs(half))})" if half.denominator != 1 else rf"(x {'+' if half>0 else '-'} {abs(half.numerator)})"

    working: List[WorkingStep] = [("math", expr)]

    if half.denominator == 1:
        h = half.numerator
        working.append(("math", rf"= {bracket}^2 - {h}^2 {'+' if c>=0 else '-'} {abs(c)}"))
        const = c - h * h
        working.append(("math", rf"= {bracket}^2 {'+' if const>=0 else '-'} {abs(const)}"))
        answer = rf"{bracket}^2 {'+' if const>=0 else '-'} {abs(const)}"
        return prompt, expr, answer, working

    num = abs(half.numerator)
    den = half.denominator
    den2 = den * den

    working.append(("math", rf"= {bracket}^2 - \\left(\\frac{{{num}}}{{{den}}}\\right)^2 {'+' if c>=0 else '-'} {abs(c)}"))
    working.append(("math", rf"= {bracket}^2 - \\frac{{{num*num}}}{{{den2}}} {'+' if c>=0 else '-'} {abs(c)}"))

    c_scaled = Fraction(c * den2, den2)
    working.append(("math", rf"= {bracket}^2 - \\frac{{{num*num}}}{{{den2}}} {'+' if c>=0 else '-'} \\frac{{{abs(c_scaled.numerator)}}}{{{den2}}}"))

    const = Fraction(c, 1) - Fraction(num * num, den2)
    const_s = _fmt_frac(abs(const))
    working.append(("math", rf"= {bracket}^2 {'+' if const>=0 else '-'} {const_s}"))

    answer = rf"{bracket}^2 {'+' if const>=0 else '-'} {const_s}"
    return prompt, expr, answer, working


def _gen_complete_square_a_not1(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    frac_inside = bool(params.get("frac_inside", False)) if params else False

    a = rng.choice([2, 3, 4, 5])

    if not frac_inside:
        k = rng.choice([-6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6])
        b = 2 * a * k
    else:
        b = rng.choice([-9, -7, -5, -3, -1, 1, 3, 5, 7, 9]) * a
        if b % (2 * a) == 0:
            b += a

    c = rng.randint(-20, 20)

    prompt = "Complete the square:"
    expr = rf"{a}x^2 {'+' if b>0 else '-'} {abs(b)}x" + (f" {'+' if c>=0 else '-'} {abs(c)}" if c != 0 else "")

    inside_coef = Fraction(b, a)
    inside = rf"x^2 {'+' if inside_coef>0 else '-'} {_fmt_frac(abs(inside_coef))}x" if inside_coef.denominator != 1 else rf"x^2 {'+' if inside_coef>0 else '-'} {abs(inside_coef.numerator)}x"

    half = inside_coef / 2
    half_abs = abs(half)
    half_s = _fmt_frac(half_abs) if half_abs.denominator != 1 else str(half_abs.numerator)
    bracket = rf"(x {'+' if half>0 else '-'} {half_s})"

    half_sq = half * half

    working: List[WorkingStep] = []
    working.append(("math", expr))
    working.append(("math", rf"= {a}\\left({inside}\\right) {'+' if c>=0 else '-'} {abs(c)}"))
    working.append(("math", rf"= {a}\\left[{bracket}^2 - ({_fmt_frac(half_abs)})^2\\right] {'+' if c>=0 else '-'} {abs(c)}"))
    working.append(("math", rf"= {a}{bracket}^2 - {a}\\left({_fmt_frac(half_abs)}\\right)^2 {'+' if c>=0 else '-'} {abs(c)}"))

    corr = Fraction(a, 1) * half_sq
    corr_s = _fmt_frac(corr)
    working.append(("math", rf"= {a}{bracket}^2 - {corr_s} {'+' if c>=0 else '-'} {abs(c)}"))

    den = corr.denominator
    c_scaled = Fraction(c * den, den)
    working.append(("math", rf"= {a}{bracket}^2 - \\frac{{{corr.numerator}}}{{{den}}} {'+' if c>=0 else '-'} \\frac{{{abs(c_scaled.numerator)}}}{{{den}}}"))

    const = Fraction(c, 1) - corr
    const_s = _fmt_frac(abs(const))
    working.append(("math", rf"= {a}{bracket}^2 {'+' if const>=0 else '-'} {const_s}"))

    answer = rf"{a}{bracket}^2 {'+' if const>=0 else '-'} {const_s}"
    return prompt, expr, answer, working


# --- Perimeter of rectilinear shapes (with diagrams) ---

def _gen_rect_perim_all(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    W = rng.choice([18, 20, 22, 24, 26, 28, 30])
    H = rng.choice([10, 12, 14, 16, 18])
    w = rng.choice([6, 8, 10])
    d = rng.choice([3, 4, 5, 6])
    L1 = rng.choice([5, 6, 7, 8, 9, 10])
    L2 = W - L1 - w
    if L2 <= 3:
        L1 = 6
        L2 = W - L1 - w

    P = 2 * W + 2 * H + 2 * d
    diagram = _rectilinear_notch_diagram(str(W), str(H), str(L1), str(w), str(L2), str(d))

    prompt = "Find the perimeter of the shape (in cm)."
    latex = ""
    answer = rf"{P}\ \mathrm{{cm}}"
    working = [
        ("text", "Add all the outside edges around the shape."),
        ("math", rf"P = 2\times {W} + 2\times {H} + 2\times {d}"),
        ("math", rf"P = {P}\ \mathrm{{cm}}"),
    ]
    return prompt, latex, answer, working, diagram


def _gen_rect_perim_missing(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    W = rng.choice([20, 22, 24, 26, 28, 30])
    H = rng.choice([12, 14, 16, 18])
    w = rng.choice([6, 8, 10])
    d = rng.choice([3, 4, 5, 6])
    L1 = rng.choice([6, 7, 8, 9, 10])
    L2 = W - L1 - w
    if L2 <= 3:
        L1 = 7
        L2 = W - L1 - w

    P = 2 * W + 2 * H + 2 * d
    diagram = _rectilinear_notch_diagram(str(W), str(H), str(L1), str(w), "?", str(d))

    prompt = "Find the perimeter of the shape (in cm)."
    latex = ""
    answer = rf"{P}\ \mathrm{{cm}}"
    working = [
        ("text", "First find the missing top length."),
        ("math", rf"{L2} = {W} - {L1} - {w}"),
        ("text", "Now add all the outside edges around the shape."),
        ("math", rf"P = 2\times {W} + 2\times {H} + 2\times {d}"),
        ("math", rf"P = {P}\ \mathrm{{cm}}"),
    ]
    return prompt, latex, answer, working, diagram


def _gen_rect_perim_find_x(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    W = rng.choice([20, 22, 24, 26, 28, 30])
    H = rng.choice([12, 14, 16, 18])
    w = rng.choice([6, 8, 10])
    L1 = rng.choice([6, 7, 8, 9, 10])
    L2 = W - L1 - w
    if L2 <= 3:
        L1 = 7
        L2 = W - L1 - w

    x = rng.choice([3, 4, 5, 6])
    P = 2 * W + 2 * H + 2 * x
    diagram = _rectilinear_notch_diagram(str(W), str(H), str(L1), str(w), str(L2), "x")

    prompt = f"The perimeter of the shape is {P} cm. Find x."
    latex = ""
    answer = rf"x = {x}\ \mathrm{{cm}}"
    working = [
        ("text", "Write an expression for the perimeter."),
        ("math", rf"{P} = 2\times {W} + 2\times {H} + 2x"),
        ("math", rf"2x = {P - (2*W + 2*H)}"),
        ("math", rf"x = \\frac{{{P - (2*W + 2*H)}}}{{2}} = {x}"),
    ]
    return prompt, latex, answer, working, diagram


# --- Area of shapes (with diagrams) ---

def _gen_area_rectangle(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    L = rng.choice([6, 7, 8, 9, 10, 12, 14, 15, 16, 18])
    W = rng.choice([4, 5, 6, 7, 8, 9, 10, 12])
    A = L * W
    diagram = _rectangle_diagram(str(L), str(W))

    prompt = "Find the area of the rectangle (in cm²)."
    latex = ""
    answer = rf"{A}\ \mathrm{{cm}}^2"
    working = [
        ("text", "Area of a rectangle = length × width."),
        ("math", rf"A = {L}\times {W}"),
        ("math", rf"A = {A}\ \mathrm{{cm}}^2"),
    ]
    return prompt, latex, answer, working, diagram


def _gen_area_triangle(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    b = rng.choice([6, 8, 10, 12, 14, 16, 18])
    h = rng.choice([4, 5, 6, 7, 8, 9, 10])
    A = b * h / 2
    if A != int(A):
        b = rng.choice([6, 8, 10, 12, 14, 16, 18])
        h = rng.choice([4, 6, 8, 10])
        A = b * h / 2
    A = int(A)

    diagram = _triangle_diagram(str(b), str(h))

    prompt = "Find the area of the triangle (in cm²)."
    latex = ""
    answer = rf"{A}\ \mathrm{{cm}}^2"
    working = [
        ("text", "Area of a triangle = 1/2 × base × height."),
        ("math", rf"A = \frac{{1}}{{2}}\times {b}\times {h}"),
        ("math", rf"A = {A}\ \mathrm{{cm}}^2"),
    ]
    return prompt, latex, answer, working, diagram


def _gen_area_parallelogram(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    b = rng.choice([6, 7, 8, 9, 10, 12, 14, 15, 16])
    h = rng.choice([4, 5, 6, 7, 8, 9, 10])
    A = b * h
    diagram = _parallelogram_diagram(str(b), str(h))

    prompt = "Find the area of the parallelogram (in cm²)."
    latex = ""
    answer = rf"{A}\ \mathrm{{cm}}^2"
    working = [
        ("text", "Area of a parallelogram = base × perpendicular height."),
        ("math", rf"A = {b}\times {h}"),
        ("math", rf"A = {A}\ \mathrm{{cm}}^2"),
    ]
    return prompt, latex, answer, working, diagram


def _gen_area_trapezium(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    a = rng.choice([6, 8, 10, 12, 14, 16])
    b = rng.choice([10, 12, 14, 16, 18, 20])
    if b <= a:
        a, b = b, a
    h = rng.choice([4, 5, 6, 7, 8, 9, 10])
    A = (a + b) * h / 2
    if A != int(A):
        h = rng.choice([4, 6, 8, 10])
        A = (a + b) * h / 2
    A = int(A)

    diagram = _trapezium_diagram(str(a), str(b), str(h))

    prompt = "Find the area of the trapezium (in cm²)."
    latex = ""
    answer = rf"{A}\ \mathrm{{cm}}^2"
    working = [
        ("text", "Area of a trapezium = 1/2 × (sum of parallel sides) × height."),
        ("math", rf"A = \frac{{1}}{{2}}\times ({a}+{b})\times {h}"),
        ("math", rf"A = \frac{{1}}{{2}}\times {a+b}\times {h}"),
        ("math", rf"A = {A}\ \mathrm{{cm}}^2"),
    ]
    return prompt, latex, answer, working, diagram


def _gen_area_kite(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    d1 = rng.choice([8, 10, 12, 14, 16, 18])
    d2 = rng.choice([6, 8, 10, 12, 14, 16])
    A = d1 * d2 / 2
    if A != int(A):
        d1 = rng.choice([8, 10, 12, 14, 16])
        d2 = rng.choice([6, 8, 10, 12, 14])
        A = d1 * d2 / 2
    A = int(A)

    diagram = _kite_diagram(str(d1), str(d2))

    prompt = "Find the area of the kite (in cm²)."
    latex = ""
    answer = rf"{A}\ \mathrm{{cm}}^2"
    working = [
        ("text", "Area of a kite (or rhombus) = 1/2 × d_1 × d_2."),
        ("math", rf"A = \frac{{1}}{{2}}\times {d1}\times {d2}"),
        ("math", rf"A = {A}\ \mathrm{{cm}}^2"),
    ]
    return prompt, latex, answer, working, diagram


def _gen_area_compound_rectilinear(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    W = rng.choice([18, 20, 22, 24, 26, 28, 30])
    H = rng.choice([12, 14, 16, 18, 20])
    w = rng.choice([6, 8, 10])
    d = rng.choice([3, 4, 5, 6])
    L1 = rng.choice([5, 6, 7, 8, 9])
    L2 = W - L1 - w
    if L2 <= 3:
        L1 = 6
        L2 = W - L1 - w

    big = W * H
    cut = w * d
    A = big - cut

    diagram = _rectilinear_notch_diagram(str(W), str(H), str(L1), str(w), str(L2), str(d))

    prompt = "Find the area of the compound rectilinear shape (in cm²)."
    latex = ""
    answer = rf"{A}\ \mathrm{{cm}}^2"
    working = [
        ("text", "Find the area of the large rectangle."),
        ("math", rf"A_\mathrm{{big}} = {W}\times {H} = {big}"),
        ("text", "Find the area of the cut-out rectangle."),
        ("math", rf"A_\mathrm{{cut}} = {w}\times {d} = {cut}"),
        ("text", "Subtract to get the area of the shape."),
        ("math", rf"A = {big} - {cut} = {A}\ \mathrm{{cm}}^2"),
    ]
    return prompt, latex, answer, working, diagram


def _gen_area_find_x(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    W = rng.choice([4, 5, 6, 7, 8, 9, 10, 12])
    x = rng.choice([6, 7, 8, 9, 10, 12, 14, 15, 16])
    A = W * x

    diagram = _rectangle_diagram("x", str(W))

    prompt = f"The area of the rectangle is {A} cm². Find x."
    latex = ""
    answer = rf"x = {x}\ \mathrm{{cm}}"
    working = [
        ("text", "Area = length × width."),
        ("math", rf"{A} = x\times {W}"),
        ("math", rf"x = \frac{{{A}}}{{{W}}} = {x}"),
    ]
    return prompt, latex, answer, working, diagram

# --- Pythagoras' theorem (with diagrams) ---

def _sqrt_simplify(n: int) -> Tuple[int, int]:
    """Return (k, m) such that sqrt(n) = k*sqrt(m) with m squarefree-ish."""
    if n <= 0:
        return 0, 0
    r = int(math.isqrt(n))
    for k in range(r, 1, -1):
        sq = k * k
        if n % sq == 0:
            return k, n // sq
    return 1, n


def _sqrt_latex(n: int) -> str:
    k, m = _sqrt_simplify(n)
    if m == 1:
        return str(k)
    if k == 1:
        return rf"\sqrt{{{m}}}"
    return rf"{k}\sqrt{{{m}}}"


def _gen_pyth_hyp_int(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    triples = [(3, 4, 5), (5, 12, 13), (6, 8, 10), (8, 15, 17), (7, 24, 25)]
    a0, b0, c0 = rng.choice(triples)
    scale = rng.choice([1, 2, 3])
    a, b, c = a0 * scale, b0 * scale, c0 * scale

    orient = rng.choice(["BL", "BR", "TL", "TR", "HB"])
    diagram = _pythagoras_triangle_diagram(str(a), str(b), "x", orientation=orient)
    prompt = "Find the length marked x (cm)."
    latex = ""
    answer = rf"x = {c}\ \mathrm{{cm}}"
    working = [
        ("text", "Use Pythagoras' theorem."),
        ("math", rf"x^2 = {a}^2 + {b}^2"),
        ("math", rf"x^2 = {a*a} + {b*b} = {c*c}"),
        ("math", rf"x = \sqrt{{{c*c}}} = {c}"),
    ]
    return prompt, latex, answer, working, diagram


def _gen_pyth_leg_int(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    triples = [(3, 4, 5), (5, 12, 13), (6, 8, 10), (8, 15, 17), (7, 24, 25)]
    a0, b0, c0 = rng.choice(triples)
    scale = rng.choice([1, 2, 3])
    a, b, c = a0 * scale, b0 * scale, c0 * scale

    orient = rng.choice(["BL", "BR", "TL", "TR", "HB"])
    unknown_side = rng.choice(["AB", "AC"])  # vary which leg is unknown

    if unknown_side == "AB":
        # AB is x; AC and BC are known
        diagram = _pythagoras_triangle_diagram(str(a), "x", str(c), orientation=orient)
        prompt = "Find the length marked x (cm)."
        latex = ""
        answer = rf"x = {b}\ \mathrm{{cm}}"
        working = [
            ("text", "Use Pythagoras' theorem."),
            ("math", rf"{c}^2 = {a}^2 + x^2"),
            ("math", rf"x^2 = {c}^2 - {a}^2"),
            ("math", rf"x^2 = {c*c} - {a*a} = {b*b}"),
            ("math", rf"x = \sqrt{{{b*b}}} = {b}"),
        ]
    else:
        # AC is x; AB and BC are known
        diagram = _pythagoras_triangle_diagram("x", str(b), str(c), orientation=orient)
        prompt = "Find the length marked x (cm)."
        latex = ""
        answer = rf"x = {a}\ \mathrm{{cm}}"
        working = [
            ("text", "Use Pythagoras' theorem."),
            ("math", rf"{c}^2 = x^2 + {b}^2"),
            ("math", rf"x^2 = {c}^2 - {b}^2"),
            ("math", rf"x^2 = {c*c} - {b*b} = {a*a}"),
            ("math", rf"x = \sqrt{{{a*a}}} = {a}"),
        ]

    return prompt, latex, answer, working, diagram


def _gen_pyth_hyp_surd(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    # Choose legs so hypotenuse is not an integer (often simplifies).
    for _ in range(60):
        a = rng.randint(4, 18)
        b = rng.randint(4, 18)
        n = a*a + b*b
        r = int(math.isqrt(n))
        if r*r != n and n <= 600:
            break
    orient = rng.choice(["BL", "BR", "TL", "TR", "HB"])
    diagram = _pythagoras_triangle_diagram(str(a), str(b), "x", orientation=orient)
    prompt = "Find the length marked x (cm)."
    latex = ""
    surd = _sqrt_latex(n)
    answer = rf"x = {surd}\ \mathrm{{cm}}"
    working = [
        ("text", "Use Pythagoras' theorem."),
        ("math", rf"x^2 = {a}^2 + {b}^2"),
        ("math", rf"x^2 = {a*a} + {b*b} = {n}"),
        ("math", rf"x = \sqrt{{{n}}}"),
    ]
    if surd != rf"\sqrt{{{n}}}":
        working.append(("math", rf"x = {surd}"))
    return prompt, latex, answer, working, diagram


def _gen_pyth_leg_surd(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    # Choose hypotenuse and one leg so the other leg is a surd.
    for _ in range(80):
        c = rng.randint(10, 26)
        a = rng.randint(4, c - 1)
        n = c * c - a * a
        r = int(math.isqrt(n))
        if n > 0 and r * r != n and n <= 600:
            break

    orient = rng.choice(["BL", "BR", "TL", "TR", "HB"])
    unknown_side = rng.choice(["AB", "AC"])

    prompt = "Find the length marked x (cm)."
    latex = ""
    surd = _sqrt_latex(n)
    answer = rf"x = {surd}\ \mathrm{{cm}}"

    if unknown_side == "AB":
        diagram = _pythagoras_triangle_diagram(str(a), "x", str(c), orientation=orient)
        working = [
            ("text", "Use Pythagoras' theorem."),
            ("math", rf"{c}^2 = {a}^2 + x^2"),
            ("math", rf"x^2 = {c}^2 - {a}^2"),
            ("math", rf"x^2 = {c*c} - {a*a} = {n}"),
            ("math", rf"x = \sqrt{{{n}}}"),
        ]
    else:
        diagram = _pythagoras_triangle_diagram("x", str(a), str(c), orientation=orient)
        working = [
            ("text", "Use Pythagoras' theorem."),
            ("math", rf"{c}^2 = x^2 + {a}^2"),
            ("math", rf"x^2 = {c}^2 - {a}^2"),
            ("math", rf"x^2 = {c*c} - {a*a} = {n}"),
            ("math", rf"x = \sqrt{{{n}}}"),
        ]

    if surd != rf"\sqrt{{{n}}}":
        working.append(("math", rf"x = {surd}"))

    return prompt, latex, answer, working, diagram


# --- Pythagoras' theorem (in other shapes / orientations) ---

def _square_with_diagonal_diagram(diag_label: str) -> bytes:
    """Square with a diagonal labelled (used for 'perimeter from diagonal' type questions)."""
    img = Image.new("RGB", (520, 380), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(40)

    x0, y0 = 150, 300
    s = 170
    x1, y1 = x0 + s, y0 - s
    draw.rectangle([x0, y1, x1, y0], outline=_FG, width=4)
    draw.line([(x0, y0), (x1, y1)], fill=_FG, width=4)

    # Diagonal label offset slightly from the diagonal
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    vx, vy = (x1 - x0), (y1 - y0)
    nx, ny = vy, -vx
    nmag = (nx * nx + ny * ny) ** 0.5 or 1.0
    nx, ny = nx / nmag, ny / nmag
    # Push far enough so the diagonal doesn't run through the label.
    _label_center(draw, (mx + nx * 72, my + ny * 72), diag_label, font)

    return _img_bytes(img)


def _gen_pyth_rect_diag_int(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    """Diagonal of a rectangle (integer answers) - embedded right triangle."""
    triples = [(3, 4, 5), (5, 12, 13), (6, 8, 10), (8, 15, 17), (7, 24, 25)]
    a0, b0, c0 = rng.choice(triples)
    scale = rng.choice([1, 2, 3])
    L, W, d = a0 * scale, b0 * scale, c0 * scale

    diagram = _rectangle_with_diagonal_diagram(str(L), str(W), "x")
    prompt = "Find the length marked x (cm)."
    latex = ""
    answer = rf"x = {d}\ \mathrm{{cm}}"
    working = [
        ("text", "Use Pythagoras' theorem on the right-angled triangle."),
        ("math", rf"x^2 = {L}^2 + {W}^2"),
        ("math", rf"x^2 = {L*L} + {W*W} = {d*d}"),
        ("math", rf"x = \sqrt{{{d*d}}} = {d}"),
    ]
    return prompt, latex, answer, working, diagram


def _gen_pyth_rect_side_int(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    """Missing side of a rectangle given diagonal (integer answers)."""
    triples = [(3, 4, 5), (5, 12, 13), (6, 8, 10), (8, 15, 17), (7, 24, 25)]
    a0, b0, c0 = rng.choice(triples)
    scale = rng.choice([1, 2, 3])
    a, b, c = a0 * scale, b0 * scale, c0 * scale

    # Known top edge = a, left edge = x, diagonal = c
    diagram = _rectangle_with_diagonal_diagram(str(a), "x", str(c))
    prompt = "Find the length marked x (cm)."
    latex = ""
    answer = rf"x = {b}\ \mathrm{{cm}}"
    working = [
        ("text", "Use Pythagoras' theorem on the right-angled triangle."),
        ("math", rf"{c}^2 = {a}^2 + x^2"),
        ("math", rf"x^2 = {c}^2 - {a}^2"),
        ("math", rf"x^2 = {c*c} - {a*a} = {b*b}"),
        ("math", rf"x = \sqrt{{{b*b}}} = {b}"),
    ]
    return prompt, latex, answer, working, diagram


def _gen_pyth_isos_height_int(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    """Height of an isosceles triangle (integer answers) using Pythagoras."""
    triples = [(3, 4, 5), (5, 12, 13), (6, 8, 10)]
    hb0, h0, s0 = rng.choice(triples)  # half-base, height, equal side
    scale = rng.choice([1, 2, 3])
    half_base, height, side = hb0 * scale, h0 * scale, s0 * scale
    base = 2 * half_base

    diagram = _isosceles_height_diagram(str(side), str(base), "x")
    prompt = "Find the height marked x (cm)."
    latex = ""
    answer = rf"x = {height}\ \mathrm{{cm}}"
    working = [
        ("text", "The perpendicular height splits the base into two equal parts."),
        ("math", rf"\frac{{{base}}}{{2}} = {half_base}"),
        ("text", "Use Pythagoras' theorem on one of the right-angled triangles."),
        ("math", rf"{side}^2 = x^2 + {half_base}^2"),
        ("math", rf"x^2 = {side}^2 - {half_base}^2"),
        ("math", rf"x^2 = {side*side} - {half_base*half_base} = {height*height}"),
        ("math", rf"x = \sqrt{{{height*height}}} = {height}"),
    ]
    return prompt, latex, answer, working, diagram


def _gen_pyth_square_perimeter_surd(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    """Perimeter of a square given its diagonal (exact surd answers)."""
    d = rng.choice([6, 8, 10, 12, 14, 16])
    diagram = _square_with_diagonal_diagram(str(d))

    # Perimeter = 2d*sqrt(2)
    coef = 2 * d
    perim = rf"{coef}\sqrt{{2}}"

    prompt = "A square has a diagonal length of " + str(d) + " cm. Find its perimeter." 
    latex = ""
    answer = rf"{perim}\ \mathrm{{cm}}"
    working = [
        ("text", "In a square, the diagonal forms two congruent right-angled triangles."),
        ("math", rf"d^2 = s^2 + s^2 = 2s^2"),
        ("math", rf"{d}^2 = 2s^2"),
        ("math", rf"s^2 = \frac{{{d*d}}}{{2}}"),
        ("math", rf"s = \frac{{{d}}}{{\sqrt{{2}}}}"),
        ("text", "Perimeter = 4s."),
        ("math", rf"P = 4\times \frac{{{d}}}{{\sqrt{{2}}}} = {perim}"),
    ]
    return prompt, latex, answer, working, diagram


# Extra Pythagoras-in-context / embedded-shape variants (GCSE-style)

def _ladder_diagram(base_label: str, height_label: str, ladder_label: str) -> bytes:
    '''Ladder against a wall (right-angled triangle context).'''
    img = Image.new("RGB", (720, 420), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(40)

    # Corner (right angle), foot on ground, top on wall
    A = (200, 340)   # corner
    B = (610, 340)   # foot
    C = (200, 110)   # top

    # Wall + ground + ladder
    draw.line([A, C], fill=_FG, width=4)
    draw.line([A, B], fill=_FG, width=4)
    draw.line([B, C], fill=_FG, width=4)

    # Right-angle marker at A (3 sides)
    s = 22
    draw.line([A, (A[0] + s, A[1])], fill=_FG, width=3)
    draw.line([(A[0] + s, A[1]), (A[0] + s, A[1] - s)], fill=_FG, width=3)
    draw.line([(A[0] + s, A[1] - s), (A[0], A[1] - s)], fill=_FG, width=3)

    # Label helper (push away from triangle centroid)
    cx, cy = (A[0] + B[0] + C[0]) / 3, (A[1] + B[1] + C[1]) / 3

    def _place_on_segment(P, Q, label: str, offset: float):
        if label == "":
            return
        mx, my = (P[0] + Q[0]) / 2, (P[1] + Q[1]) / 2
        vx, vy = (Q[0] - P[0]), (Q[1] - P[1])
        nx, ny = vy, -vx
        if ((cx - mx) * nx + (cy - my) * ny) > 0:
            nx, ny = -nx, -ny
        mag = (nx * nx + ny * ny) ** 0.5 or 1.0
        nx, ny = nx / mag, ny / mag
        _label_center(draw, (mx + nx * offset, my + ny * offset), label, font)

    _place_on_segment(A, B, base_label, 40)
    _place_on_segment(A, C, height_label, 40)
    _place_on_segment(B, C, ladder_label, 70)

    return _img_bytes(img)


def _gen_pyth_ladder_int(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    '''Worded ladder problem (integer answers) using Pythagoras.'''
    triples = [(3, 4, 5), (5, 12, 13), (6, 8, 10), (8, 15, 17)]
    a0, b0, c0 = rng.choice(triples)
    scale = rng.choice([1, 2, 3])
    height, base, ladder = a0 * scale, b0 * scale, c0 * scale

    diagram = _ladder_diagram(str(base), "x", str(ladder))

    prompt = f"A {ladder} m ladder is placed against a vertical wall. The base of the ladder is {base} m from the wall. Work out how far up the wall the ladder reaches."
    latex = ""
    answer = rf"x = {height}\ \mathrm{{m}}"
    working = [
        ("text", "Use Pythagoras' theorem."),
        ("math", rf"{ladder}^2 = x^2 + {base}^2"),
        ("math", rf"x^2 = {ladder}^2 - {base}^2"),
        ("math", rf"x^2 = {ladder*ladder} - {base*base} = {height*height}"),
        ("math", rf"x = \sqrt{{{height*height}}} = {height}"),
    ]
    return prompt, latex, answer, working, diagram


def _right_trapezium_slant_diagram(top_base: str, bottom_base: str, height: str, slant_label: str) -> bytes:
    '''Right-angled trapezium with a dashed height from the top-right corner.'''
    img = Image.new("RGB", (760, 420), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(40)

    A = (200, 340)  # bottom-left
    B = (610, 340)  # bottom-right
    D = (200, 120)  # top-left (right angles on left side)
    C = (520, 120)  # top-right

    # Outline
    draw.line([A, B, C, D, A], fill=_FG, width=4)

    # Dashed height from C to E on AB
    E = (C[0], A[1])
    _dashed_line(draw, C, E, dash=10, gap=9, lw=3)

    # Right-angle marker at E (3 sides)
    ra = 16
    draw.line([E, (E[0] - ra, E[1])], fill=_FG, width=3)
    draw.line([(E[0] - ra, E[1]), (E[0] - ra, E[1] - ra)], fill=_FG, width=3)
    draw.line([(E[0] - ra, E[1] - ra), (E[0], E[1] - ra)], fill=_FG, width=3)

    # Labels: bases
    _label_center(draw, ((D[0] + C[0]) / 2, D[1] - 34), top_base, font)
    _label_center(draw, ((A[0] + B[0]) / 2, A[1] + 34), bottom_base, font)

    # Slanted side label (B-C) offset away from shape
    mx, my = (B[0] + C[0]) / 2, (B[1] + C[1]) / 2
    vx, vy = (C[0] - B[0]), (C[1] - B[1])
    nx, ny = vy, -vx
    # push away from the shape centre
    cx, cy = (A[0] + B[0] + C[0] + D[0]) / 4, (A[1] + B[1] + C[1] + D[1]) / 4
    if ((cx - mx) * nx + (cy - my) * ny) > 0:
        nx, ny = -nx, -ny
    mag = (nx * nx + ny * ny) ** 0.5 or 1.0
    nx, ny = nx / mag, ny / mag
    _label_center(draw, (mx + nx * 72, my + ny * 72), slant_label, font)

    # Height label: keep close to the dashed line
    _label_center(draw, (E[0] + 28, (C[1] + E[1]) / 2), height, font)

    return _img_bytes(img)


def _gen_pyth_trapezium_slant_int(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    '''Right-angled trapezium: find the slanted side (integer answers) using Pythagoras.'''
    triples = [(9, 12, 15), (8, 15, 17), (5, 12, 13), (6, 8, 10)]
    h0, d0, s0 = rng.choice(triples)  # height, difference in bases, slant side
    scale = rng.choice([1, 2])
    h, d, slant = h0 * scale, d0 * scale, s0 * scale

    top = rng.randint(6, 20)
    bottom = top + d

    diagram = _right_trapezium_slant_diagram(str(top), str(bottom), str(h), "x")

    prompt = "Find the length marked x (cm)."
    latex = ""
    answer = rf"x = {slant}\ \mathrm{{cm}}"
    working = [
        ("text", "First find the difference between the parallel sides."),
        ("math", rf"{bottom} - {top} = {d}"),
        ("text", "Now use Pythagoras' theorem on the right-angled triangle."),
        ("math", rf"x^2 = {h}^2 + {d}^2"),
        ("math", rf"x^2 = {h*h} + {d*d} = {slant*slant}"),
        ("math", rf"x = \sqrt{{{slant*slant}}} = {slant}"),
    ]
    return prompt, latex, answer, working, diagram


def _gen_pyth_tv_ratio(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    '''TV/screen ratio worded problem (uses 3-4-5 scaling).'''
    k = rng.choice([5, 6, 8, 9, 10, 12, 15])
    diag = 5 * k
    width = 4 * k
    height = 3 * k

    prompt = f"A television screen is rectangular. The ratio of the width to the height is 4:3. The diagonal length is {diag} inches. Work out the width of the screen."
    latex = ""
    answer = rf"{width}\ \mathrm{{inches}}"
    working = [
        ("text", "Let the width be 4k and the height be 3k."),
        ("math", rf"{diag}^2 = (4k)^2 + (3k)^2"),
        ("math", rf"{diag}^2 = 16k^2 + 9k^2 = 25k^2"),
        ("math", rf"{diag} = 5k"),
        ("math", rf"k = \frac{{{diag}}}{{5}} = {k}"),
        ("math", rf"\mathrm{{Width}} = 4k = 4\times {k} = {width}"),
    ]
    return prompt, latex, answer, working, None

# --- Finding fractions of an amount ---

def _gen_frac_of_amount_numeric(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    level = (params or {}).get("level", "proper")

    if level == "proper":
        den = rng.choice([2, 3, 4, 5, 6, 8, 10, 12])
        num = rng.randint(1, den - 1)
        k = rng.randint(5, 25)
        amount = den * k
    elif level == "proper_simplify":
        # Choose a fraction that can simplify after multiplying
        den = rng.choice([6, 8, 9, 10, 12, 15, 16])
        num = rng.choice([2, 3, 4, 5, 6, 7])
        num = min(num, den - 1)
        k = rng.randint(4, 18)
        amount = den * k
    else:  # "improper"
        den = rng.choice([2, 3, 4, 5, 6, 8])
        num = rng.randint(den + 1, 2 * den + 3)
        k = rng.randint(4, 18)
        amount = den * k

    frac = Fraction(num, den)
    result = frac * amount

    prompt = "Calculate:"
    latex = rf"\frac{{{num}}}{{{den}}}\ \mathrm{{of}}\ {amount}"
    answer = _sanitize_math(_fmt_frac(result))

    unit = amount // den
    working: List[WorkingStep] = [
        ("text", f"Find 1/{den} of {amount} first."),
        ("math", rf"{amount} \div {den} = {unit}"),
        ("text", rf"Multiply by {num}."),
        ("math", rf"{unit} \times {num} = {_sanitize_math(_fmt_frac(result))}"),
    ]
    return prompt, latex, answer, working


def _gen_frac_of_amount_worded(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    level = (params or {}).get("level", "easy")

    contexts = []
    if level == "easy":
        contexts = ["marbles", "sweets", "students", "books"]
        den = rng.choice([2, 3, 4, 5, 6, 8, 10])
        num = rng.randint(1, den - 1)
        amount = den * rng.randint(6, 24)
        item = rng.choice(contexts)
        prompt = f"There are {amount} {item}. {num}/{den} of them are in group A. How many are in group A?"
        latex = rf"\frac{{{num}}}{{{den}}}\ \mathrm{{of}}\ {amount}"
        unit = amount // den
        result = Fraction(num, den) * amount
        answer = _sanitize_math(_fmt_frac(result))
        working: List[WorkingStep] = [
            ("text", f"Find 1/{den} of {amount} first."),
            ("math", rf"{amount} \div {den} = {unit}"),
            ("text", rf"Multiply by {num}."),
            ("math", rf"{unit} \times {num} = {_sanitize_math(_fmt_frac(result))}"),
        ]
        return prompt, latex, answer, working

    # Money/measure contexts (a bit more GCSE-like)
    den = rng.choice([4, 5, 8, 10, 16])
    num = rng.randint(1, den - 1)
    if rng.random() < 0.5:
        # Money
        pounds = den * rng.randint(6, 30)
        amount = pounds
        result = Fraction(num, den) * amount
        prompt = f"A jacket costs £{amount}. Work out {num}/{den} of the price." 
        latex = rf"\frac{{{num}}}{{{den}}}\ \mathrm{{of}}\ {amount}"
        answer = rf"{_sanitize_math(_fmt_frac(result))}\ \mathrm{{pounds}}"
        unit = amount // den
        working = [
            ("text", f"Find 1/{den} of {amount} first."),
            ("math", rf"{amount} \div {den} = {unit}"),
            ("text", rf"Multiply by {num}."),
            ("math", rf"{unit} \times {num} = {_sanitize_math(_fmt_frac(result))}"),
        ]
        return prompt, latex, answer, working
    else:
        # Volume/mass
        unit_name = rng.choice(["ml", "g", "cm"])  # simple units
        amount = den * rng.randint(8, 40)
        result = Fraction(num, den) * amount
        prompt = f"A container holds {amount}{unit_name}. Work out {num}/{den} of this amount." 
        latex = rf"\frac{{{num}}}{{{den}}}\ \mathrm{{of}}\ {amount}"
        answer = rf"{_sanitize_math(_fmt_frac(result))}\ \mathrm{{{unit_name}}}"
        unit = amount // den
        working = [
            ("text", f"Find 1/{den} of {amount} first."),
            ("math", rf"{amount} \div {den} = {unit}"),
            ("text", rf"Multiply by {num}."),
            ("math", rf"{unit} \times {num} = {_sanitize_math(_fmt_frac(result))}"),
        ]
        return prompt, latex, answer, working



# --- Polygon angles ---

def _gen_poly_regular_interior(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    n = rng.choice([3, 4, 5, 6, 8, 9, 10, 12, 15, 18, 20])
    interior = (n - 2) * 180 / n
    interior_str = str(int(round(interior)))
    prompt = f"A regular polygon has {n} sides. Find each interior angle."
    latex = ""
    answer = rf"{interior_str}^\circ"
    working = [
        ("text", "Interior angle of a regular n-gon:"),
        ("math", r"\\frac{(n-2)\\times 180}{n}"),
        ("math", rf"= \\frac{{({n}-2)\\times 180}}{{{n}}} = {interior_str}^\circ"),
    ]
    return prompt, latex, answer, working


def _gen_poly_regular_exterior(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    n = rng.choice([3, 4, 5, 6, 8, 9, 10, 12, 15, 18, 20])
    exterior = 360 / n
    exterior_str = str(int(round(exterior)))
    prompt = f"A regular polygon has {n} sides. Find each exterior angle."
    latex = ""
    answer = rf"{exterior_str}^\circ"
    working = [
        ("text", "Exterior angles sum to 360°."),
        ("math", rf"\\frac{{360}}{{{n}}} = {exterior_str}^\circ"),
    ]
    return prompt, latex, answer, working


def _gen_poly_find_n_from_exterior(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    n = rng.choice([3, 4, 5, 6, 8, 9, 10, 12, 15, 18, 20])
    ext = 360 / n
    ext_str = str(int(round(ext)))
    prompt = f"A regular polygon has an exterior angle of {ext_str}°. Find the number of sides."
    latex = ""
    answer = f"{n}"
    working = [
        ("text", "Exterior angles sum to 360°."),
        ("math", rf"n = \\frac{{360}}{{{ext_str}}} = {n}"),
    ]
    return prompt, latex, answer, working


def _gen_poly_sum_interior(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    n = rng.choice([3, 4, 5, 6, 7, 8, 9, 10, 12])
    s = (n - 2) * 180
    prompt = f"Find the sum of the interior angles of a {n}-gon."
    latex = ""
    answer = rf"{s}^\circ"
    working = [
        ("text", "Sum of interior angles:"),
        ("math", r"(n-2)\\times 180"),
        ("math", rf"= ({n}-2)\\times 180 = {s}^\circ"),
    ]
    return prompt, latex, answer, working


def _gen_poly_missing_irregular(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    n = rng.choice([5, 6, 7])
    total = (n - 2) * 180
    known = []
    remaining = total
    for _ in range(n - 1):
        a = rng.choice([80, 90, 100, 110, 120, 130, 140, 150])
        if remaining - a < 60:
            a = 90
        known.append(a)
        remaining -= a
    missing = remaining
    prompt = f"A {n}-gon has interior angles {', '.join(str(x) for x in known)} and x. Find x."
    latex = ""
    answer = rf"{missing}^\circ"
    working = [
        ("text", f"Sum of interior angles = {total}°."),
        ("math", rf"x = {total} - ({' + '.join(str(x) for x in known)})"),
        ("math", rf"x = {missing}^\circ"),
    ]
    return prompt, latex, answer, working


# --- Reasoning with polygon angles ---

def _gen_poly_tessellation_find_n(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    scenario = rng.choice(["tri+sq+sq", "tri+tri+sq", "hex+sq", "sq+sq+sq"])
    if scenario == "tri+sq+sq":
        known_sum = 60 + 90 + 90
    elif scenario == "tri+tri+sq":
        known_sum = 60 + 60 + 90
    elif scenario == "hex+sq":
        known_sum = 120 + 90
    else:
        known_sum = 90 + 90 + 90

    target_interior = 360 - known_sum
    ext = 180 - target_interior
    n = int(round(360 / ext))

    prompt = "Angles around a point add to 360°. Find the number of sides of the missing regular polygon."
    latex = ""
    answer = f"{n}"
    working = [
        ("text", "Angles around a point add to 360°."),
        ("math", rf"{target_interior} = 360 - {known_sum}"),
        ("text", "Exterior = 180 - interior."),
        ("math", rf"\mathrm{{Exterior}} = 180 - {target_interior} = {ext}^\circ"),
        ("math", rf"n = \\frac{{360}}{{{ext}}} = {n}"),
    ]
    return prompt, latex, answer, working


# --- Algebraic geometry and angle equations ---

def _gen_poly_algebra_interior(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    n = rng.choice([5, 6, 8, 9, 10, 12])
    interior = int(round((n - 2) * 180 / n))
    x = rng.randint(2, 10)
    a = rng.choice([2, 3, 4])
    b = interior - a * x
    if b < -20 or b > 80:
        a = 3
        x = rng.randint(2, 8)
        b = interior - a * x

    prompt = f"A regular {n}-gon has interior angle ({a}x {'+' if b>=0 else '-'} {abs(b)})°. Find x."
    latex = ""
    answer = rf"x = {x}"
    working = [
        ("text", "First find the interior angle."),
        ("math", rf"\\frac{{({n}-2)\\times 180}}{{{n}}} = {interior}^\circ"),
        ("text", "Now form and solve an equation."),
        ("math", rf"{a}x {'+' if b>=0 else '-'} {abs(b)} = {interior}"),
        ("math", rf"{a}x = {interior - b}"),
        ("math", rf"x = \\frac{{{interior - b}}}{{{a}}} = {x}"),
    ]
    return prompt, latex, answer, working


def _gen_poly_algebra_exterior(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    n = rng.choice([5, 6, 8, 9, 10, 12, 15])
    ext = int(round(360 / n))
    x = rng.randint(2, 10)
    a = rng.choice([2, 3, 4])
    b = ext - a * x
    if b < -20 or b > 40:
        a = 2
        x = rng.randint(2, 12)
        b = ext - a * x

    prompt = f"A regular {n}-gon has exterior angle ({a}x {'+' if b>=0 else '-'} {abs(b)})°. Find x."
    latex = ""
    answer = rf"x = {x}"
    working = [
        ("text", "First find the exterior angle."),
        ("math", rf"\\frac{{360}}{{{n}}} = {ext}^\circ"),
        ("text", "Now form and solve an equation."),
        ("math", rf"{a}x {'+' if b>=0 else '-'} {abs(b)} = {ext}"),
        ("math", rf"{a}x = {ext - b}"),
        ("math", rf"x = \\frac{{{ext - b}}}{{{a}}} = {x}"),
    ]
    return prompt, latex, answer, working


# -----------------------------
# Templates / Levels
# -----------------------------

TEMPLATES: List[Template] = [
    Template("seq_add", "Continuing sequences", "add", "Add the same amount", 1, _gen_seq_add),
    Template("seq_sub", "Continuing sequences", "sub", "Subtract the same amount", 2, _gen_seq_sub),
    Template("seq_mul", "Continuing sequences", "mul", "Multiply by the same number", 3, _gen_seq_mul),
    Template("seq_div", "Continuing sequences", "div", "Divide by the same number", 4, _gen_seq_div),
    Template("seq_fibo", "Continuing sequences", "fibo", "Fibonacci", 5, _gen_seq_fibo),

    Template("nth_pp", "Finding the nth term", "pp", "Positive difference, positive 0th term", 1, lambda r, s, p: _gen_nth_term_arith(r, s, {"d_sign": 1, "a0_sign": 1})),
    Template("nth_pn", "Finding the nth term", "pn", "Positive difference, negative 0th term", 2, lambda r, s, p: _gen_nth_term_arith(r, s, {"d_sign": 1, "a0_sign": -1})),
    Template("nth_np", "Finding the nth term", "np", "Negative difference, positive 0th term", 3, lambda r, s, p: _gen_nth_term_arith(r, s, {"d_sign": -1, "a0_sign": 1})),
    Template("nth_nn", "Finding the nth term", "nn", "Negative difference, negative 0th term", 4, lambda r, s, p: _gen_nth_term_arith(r, s, {"d_sign": -1, "a0_sign": -1})),

    Template("use_term_pos", "Using the nth term", "term_pos", "Find a term (positive coefficient)", 1, lambda r, s, p: _gen_use_nth_find_term(r, s, {"a_sign": 1})),
    Template("use_term_neg", "Using the nth term", "term_neg", "Find a term (negative coefficient)", 2, lambda r, s, p: _gen_use_nth_find_term(r, s, {"a_sign": -1})),
    Template("use_n_pos", "Using the nth term", "n_pos", "Find n (positive coefficient)", 3, lambda r, s, p: _gen_use_nth_find_n(r, s, {"a_sign": 1})),
    Template("use_n_neg", "Using the nth term", "n_neg", "Find n (negative coefficient)", 4, lambda r, s, p: _gen_use_nth_find_n(r, s, {"a_sign": -1})),

    Template("use_is_term_pos", "Using the nth term", "is_term_pos", "Is a value a term? (positive coefficient)", 5, lambda r, s, p: _gen_use_nth_is_term(r, s, {"a_sign": 1})),
    Template("use_is_term_neg", "Using the nth term", "is_term_neg", "Is a value a term? (negative coefficient)", 5, lambda r, s, p: _gen_use_nth_is_term(r, s, {"a_sign": -1})),

    Template("eq1_add", "Solving 1 step equations", "add", "x + b = c", 1, _gen_eq_1_add),
    Template("eq1_sub", "Solving 1 step equations", "sub", "x - b = c", 2, _gen_eq_1_sub),
    Template("eq1_mul", "Solving 1 step equations", "mul", "ax = c", 3, _gen_eq_1_mul),
    Template("eq1_div", "Solving 1 step equations", "div", "x/a = c", 4, _gen_eq_1_div),

    Template("eq2_plus", "Solving 2 step equations", "ax_plus", "ax + b = c (b positive)", 1, lambda r, s, p: _gen_eq_2_ax_plus_b(r, s, {"b_sign": 1})),
    Template("eq2_minus", "Solving 2 step equations", "ax_minus", "ax - b = c (b positive)", 2, lambda r, s, p: _gen_eq_2_ax_plus_b(r, s, {"b_sign": -1})),
    Template("eq2_br_plus", "Solving 2 step equations", "a_br_plus", "a(x + b) = c", 3, lambda r, s, p: _gen_eq_2_a_bracket(r, s, {"inside_sign": 1})),
    Template("eq2_br_minus", "Solving 2 step equations", "a_br_minus", "a(x - b) = c", 4, lambda r, s, p: _gen_eq_2_a_bracket(r, s, {"inside_sign": -1})),

    Template("pct_nc_simple", "Finding percentages using non-calculator methods", "simple", "10%, 20%, 25%, 50%", 1, lambda r, s, p: _gen_pct_noncalc(r, s, {"level": "simple"})),
    Template("pct_nc_5_15", "Finding percentages using non-calculator methods", "five_fifteen", "5% and 15%", 2, lambda r, s, p: _gen_pct_noncalc(r, s, {"level": "five_fifteen"})),
    Template("pct_nc_eighths", "Finding percentages using non-calculator methods", "eighths", "12.5% and 37.5%", 3, lambda r, s, p: _gen_pct_noncalc(r, s, {"level": "eighths"})),
    Template("pct_nc_decomp", "Finding percentages using non-calculator methods", "decomp", "Build from 10% and 5%", 4, lambda r, s, p: _gen_pct_noncalc(r, s, {"level": "decomp"})),

    Template("pct_c_int", "Finding percentages using calculator methods", "int", "Whole-number percentages", 1, lambda r, s, p: _gen_pct_calc(r, s, {"level": "int"})),
    Template("pct_c_dec", "Finding percentages using calculator methods", "dec", "Decimal percentages (e.g. 12.5%)", 2, lambda r, s, p: _gen_pct_calc(r, s, {"level": "dec"})),

    Template("inc_nc_simple", "Increasing and decreasing by percentages using non-calculator methods", "inc_simple", "Increase by 10%, 20% or 25%", 1, lambda r, s, p: _gen_inc_dec_noncalc(r, s, {"direction": "increase", "family": "simple"})),
    Template("dec_nc_simple", "Increasing and decreasing by percentages using non-calculator methods", "dec_simple", "Decrease by 10%, 20% or 25%", 2, lambda r, s, p: _gen_inc_dec_noncalc(r, s, {"direction": "decrease", "family": "simple"})),
    Template("inc_nc_mix", "Increasing and decreasing by percentages using non-calculator methods", "inc_mix", "Increase by 5%, 15% or 30%", 3, lambda r, s, p: _gen_inc_dec_noncalc(r, s, {"direction": "increase", "family": "mix"})),
    Template("dec_nc_mix", "Increasing and decreasing by percentages using non-calculator methods", "dec_mix", "Decrease by 5%, 15% or 30%", 4, lambda r, s, p: _gen_inc_dec_noncalc(r, s, {"direction": "decrease", "family": "mix"})),

    Template("inc_c", "Increasing and decreasing by percentages using calculator methods", "inc", "Increase using a multiplier", 1, lambda r, s, p: _gen_inc_dec_calc(r, s, {"direction": "increase"})),
    Template("dec_c", "Increasing and decreasing by percentages using calculator methods", "dec", "Decrease using a multiplier", 2, lambda r, s, p: _gen_inc_dec_calc(r, s, {"direction": "decrease"})),

    Template("cs_even", "Completing the square", "a1_even", "a = 1, even x coefficient", 1, lambda r, s, p: _gen_complete_square_a1(r, s, {"b_parity": "even"})),
    Template("cs_odd", "Completing the square", "a1_odd", "a = 1, odd x coefficient", 2, lambda r, s, p: _gen_complete_square_a1(r, s, {"b_parity": "odd"})),
    Template("cs_a_int", "Completing the square", "a_int", "a \\neq 1, integer half inside", 3, lambda r, s, p: _gen_complete_square_a_not1(r, s, {"frac_inside": False})),
    Template("cs_a_frac", "Completing the square", "a_frac", "a \\neq 1, fractional half inside", 4, lambda r, s, p: _gen_complete_square_a_not1(r, s, {"frac_inside": True})),

    Template("area_rect", "Area of shapes", "rect", "Rectangle", 1, _gen_area_rectangle),
    Template("area_tri", "Area of shapes", "tri", "Triangle", 2, _gen_area_triangle),
    Template("area_para", "Area of shapes", "para", "Parallelogram", 2, _gen_area_parallelogram),
    Template("area_trap", "Area of shapes", "trap", "Trapezium", 3, _gen_area_trapezium),
    Template("area_kite", "Area of shapes", "kite", "Kite / rhombus (diagonals)", 3, _gen_area_kite),
    Template("area_compound", "Area of shapes", "compound", "Compound rectilinear", 4, _gen_area_compound_rectilinear),
    Template("area_find_x", "Area of shapes", "find_x", "Given area, find x", 5, _gen_area_find_x),

    # Pythagoras' theorem
    Template("pyth_hyp_int", "Pythagoras' theorem", "hyp_int", "Find hypotenuse (integer)", 1, _gen_pyth_hyp_int),
    Template("pyth_leg_int", "Pythagoras' theorem", "leg_int", "Find a leg (integer)", 2, _gen_pyth_leg_int),
    Template("pyth_hyp_surd", "Pythagoras' theorem", "hyp_surd", "Find hypotenuse (surd)", 3, _gen_pyth_hyp_surd),
    Template("pyth_leg_surd", "Pythagoras' theorem", "leg_surd", "Find a leg (surd)", 4, _gen_pyth_leg_surd),

    # Pythagoras' theorem (in other shapes / orientations)
    Template("pyth_rect_diag", "Pythagoras' theorem in other shapes", "rect_diag", "Rectangle diagonal (integer)", 1, _gen_pyth_rect_diag_int),
    Template("pyth_rect_side", "Pythagoras' theorem in other shapes", "rect_side", "Rectangle missing side (integer)", 2, _gen_pyth_rect_side_int),
    Template("pyth_isos_height", "Pythagoras' theorem in other shapes", "isos_height", "Isosceles triangle height (integer)", 3, _gen_pyth_isos_height_int),
    Template("pyth_square_perim", "Pythagoras' theorem in other shapes", "sq_perim", "Square perimeter from diagonal (surd)", 4, _gen_pyth_square_perimeter_surd),

Template("pyth_ladder", "Pythagoras' theorem in other shapes", "ladder", "Ladder against a wall (worded, integer)", 2, _gen_pyth_ladder_int),
Template("pyth_trap_slant", "Pythagoras' theorem in other shapes", "trap_slant", "Right-angled trapezium side (integer)", 3, _gen_pyth_trapezium_slant_int),
Template("pyth_tv_ratio", "Pythagoras' theorem in other shapes", "tv_ratio", "Screen ratio (worded)", 4, _gen_pyth_tv_ratio),

    # Fractions of an amount
    Template("frac_amt_proper", "Finding fractions of an amount", "proper", "Proper fractions (whole-number answers)", 1, lambda r, s, p: _gen_frac_of_amount_numeric(r, s, {"level": "proper"})),
    Template("frac_amt_simpl", "Finding fractions of an amount", "proper_simpl", "Proper fractions (include simplifying)", 2, lambda r, s, p: _gen_frac_of_amount_numeric(r, s, {"level": "proper_simplify"})),
    Template("frac_amt_improper", "Finding fractions of an amount", "improper", "Improper fractions", 3, lambda r, s, p: _gen_frac_of_amount_numeric(r, s, {"level": "improper"})),

    Template("frac_amt_word_easy", "Finding fractions of an amount (worded)", "easy", "Worded (counts)", 1, lambda r, s, p: _gen_frac_of_amount_worded(r, s, {"level": "easy"})),
    Template("frac_amt_word_ctx", "Finding fractions of an amount (worded)", "context", "Worded (money / measure)", 2, lambda r, s, p: _gen_frac_of_amount_worded(r, s, {"level": "context"})),

    Template("perim_all", "Perimeter of rectilinear shapes", "all", "All sides given", 1, _gen_rect_perim_all),
    Template("perim_missing", "Perimeter of rectilinear shapes", "missing", "Missing sides to work out", 2, _gen_rect_perim_missing),
    Template("perim_find_x", "Perimeter of rectilinear shapes", "find_x", "Perimeter given, find x", 3, _gen_rect_perim_find_x),

    Template("poly_int", "Interior and exterior angles of polygons", "int", "Interior angle (regular polygon)", 1, _gen_poly_regular_interior),
    Template("poly_ext", "Interior and exterior angles of polygons", "ext", "Exterior angle (regular polygon)", 2, _gen_poly_regular_exterior),
    Template("poly_n_from_ext", "Interior and exterior angles of polygons", "n_from_ext", "Find number of sides from exterior angle", 3, _gen_poly_find_n_from_exterior),
    Template("poly_sum", "Interior and exterior angles of polygons", "sum", "Sum of interior angles", 4, _gen_poly_sum_interior),
    Template("poly_missing", "Interior and exterior angles of polygons", "missing", "Missing interior angle (irregular)", 5, _gen_poly_missing_irregular),

    Template("poly_tess", "Reasoning with polygon angles", "tess", "Angles around a point (find n)", 3, _gen_poly_tessellation_find_n),

    Template("poly_alg_int", "Algebraic geometry and angle equations", "alg_int", "Interior angle with algebra (regular polygon)", 4, _gen_poly_algebra_interior),
    Template("poly_alg_ext", "Algebraic geometry and angle equations", "alg_ext", "Exterior angle with algebra (regular polygon)", 5, _gen_poly_algebra_exterior),
]


TOPIC_ORDER: List[str] = [
    "Continuing sequences",
    "Finding the nth term",
    "Using the nth term",
    "Solving 1 step equations",
    "Solving 2 step equations",
    "Finding fractions of an amount",
    "Finding fractions of an amount (worded)",
    "Finding percentages using non-calculator methods",
    "Finding percentages using calculator methods",
    "Increasing and decreasing by percentages using non-calculator methods",
    "Increasing and decreasing by percentages using calculator methods",
    "Completing the square",
    "Perimeter of rectilinear shapes",
    "Area of shapes",
    "Pythagoras' theorem",
    "Pythagoras' theorem in other shapes",
    "Interior and exterior angles of polygons",
    "Reasoning with polygon angles",
    "Algebraic geometry and angle equations",
]


# -----------------------------
# Topic strands (GCSE-style)
# -----------------------------

# These are the high-level strands used for filtering topics in the UI.
# They broadly align with GCSE domain groupings (Number / Algebra / Ratio & Proportion /
# Geometry & Measures / Probability / Statistics), but are kept as a practical UI taxonomy.
STRAND_ORDER: List[str] = [
    "Number",
    "Algebra",
    "Ratio and proportion",
    "Geometry and measures",
    "Statistics",
    "Probability",
    "Other",
    "All",
]


# Primary strand and (optional) extra tags for cross-domain topics.
TOPIC_STRANDS: Dict[str, Dict[str, Any]] = {
    # Algebra
    "Continuing sequences": {"primary": "Algebra", "tags": ["Algebra"]},
    "Finding the nth term": {"primary": "Algebra", "tags": ["Algebra"]},
    "Using the nth term": {"primary": "Algebra", "tags": ["Algebra"]},
    "Solving 1 step equations": {"primary": "Algebra", "tags": ["Algebra"]},
    "Solving 2 step equations": {"primary": "Algebra", "tags": ["Algebra"]},
    "Completing the square": {"primary": "Algebra", "tags": ["Algebra"]},

    # Ratio & proportion
    "Finding fractions of an amount": {"primary": "Number", "tags": ["Number", "Ratio and proportion"]},
    "Finding fractions of an amount (worded)": {"primary": "Number", "tags": ["Number", "Ratio and proportion"]},
    "Finding percentages using non-calculator methods": {"primary": "Ratio and proportion", "tags": ["Ratio and proportion"]},
    "Finding percentages using calculator methods": {"primary": "Ratio and proportion", "tags": ["Ratio and proportion"]},
    "Increasing and decreasing by percentages using non-calculator methods": {"primary": "Ratio and proportion", "tags": ["Ratio and proportion"]},
    "Increasing and decreasing by percentages using calculator methods": {"primary": "Ratio and proportion", "tags": ["Ratio and proportion"]},

    # Geometry & measures
    "Perimeter of rectilinear shapes": {"primary": "Geometry and measures", "tags": ["Geometry and measures"]},
    "Area of shapes": {"primary": "Geometry and measures", "tags": ["Geometry and measures"]},
    "Pythagoras\' theorem": {"primary": "Geometry and measures", "tags": ["Geometry and measures"]},
    "Pythagoras\' theorem in other shapes": {"primary": "Geometry and measures", "tags": ["Geometry and measures"]},
    "Interior and exterior angles of polygons": {"primary": "Geometry and measures", "tags": ["Geometry and measures"]},
    "Reasoning with polygon angles": {"primary": "Geometry and measures", "tags": ["Geometry and measures"]},
    # Cross-domain: geometry with algebra
    "Algebraic geometry and angle equations": {"primary": "Geometry and measures", "tags": ["Geometry and measures", "Algebra"]},
}


def available_strands() -> List[str]:
    """Return available strand names for UI filtering (includes 'All')."""
    return STRAND_ORDER


def strand_for_topic(topic: str) -> str:
    meta = TOPIC_STRANDS.get(topic)
    if not meta:
        return "Other"
    return str(meta.get("primary") or "Other")


def topics_in_strand(strand: str) -> List[str]:
    """Return topics (in available_topics() order) filtered by strand."""
    all_topics = available_topics()
    if strand == "All":
        return all_topics
    if strand == "Other":
        return [t for t in all_topics if strand_for_topic(t) == "Other"]
    return [t for t in all_topics if strand_for_topic(t) == strand]


def available_topics() -> List[str]:
    topics = {t.topic for t in TEMPLATES}
    order = {name: i for i, name in enumerate(TOPIC_ORDER)}
    return sorted(topics, key=lambda t: (order.get(t, 10**9), t))


def available_levels(topic: str, max_difficulty: int = 5) -> List[Tuple[str, str]]:
    levels = [t for t in TEMPLATES if t.topic == topic and t.difficulty <= max_difficulty]
    seen: set[str] = set()
    out: List[Tuple[str, str]] = []
    for t in sorted(levels, key=lambda x: (x.difficulty, x.level_name)):
        if t.level_id in seen:
            continue
        seen.add(t.level_id)
        out.append((t.level_id, t.level_name))
    return out


def get_template(topic: str, level_id: str, max_difficulty: int = 5) -> Template:
    for t in TEMPLATES:
        if t.topic == topic and t.level_id == level_id and t.difficulty <= max_difficulty:
            return t
    raise ValueError(f"No template found for topic={topic} level_id={level_id} at max_difficulty={max_difficulty}.")


def generate_two_per_topic(
    topics_levels: Dict[str, str],
    max_difficulty: int,
    seed: int,
) -> Tuple[Dict[str, List[GeneratedQuestion]], Dict[str, Optional[Dict[str, Any]]], Dict[str, str]]:
    """Return (grouped_questions, pair_params_map, level_name_map). Ensures pair uniqueness per topic."""
    master = random.Random(seed)

    grouped: Dict[str, List[GeneratedQuestion]] = {}
    pair_params_map: Dict[str, Optional[Dict[str, Any]]] = {}
    level_name_map: Dict[str, str] = {}

    for topic, level_id in topics_levels.items():
        tmpl = get_template(topic, level_id, max_difficulty=max_difficulty)
        level_name_map[topic] = tmpl.level_name

        pair_params = tmpl.pair_params_factory(master) if tmpl.pair_params_factory else None
        pair_params_map[topic] = pair_params

        qs: List[GeneratedQuestion] = []
        sig0: Optional[Tuple[str, str, str]] = None

        for j in range(2):
            # Re-roll second question if it is identical to the first (same prompt/latex/diagram).
            for attempt in range(60):
                qseed = master.randint(1, 10**9)
                res = tmpl.generator(random.Random(qseed), qseed, pair_params)

                diagram = None
                if isinstance(res, tuple) and len(res) == 5:
                    pr, latex, ans, working, diagram = res
                else:
                    pr, latex, ans, working = res

                pr = pr.strip()
                latex = _sanitize_math(latex)
                ans = _sanitize_math(ans)
                working2: List[WorkingStep] = [(k, _sanitize_math(v)) for (k, v) in working]

                cand_sig = _sig(pr, latex, diagram)
                if j == 0:
                    sig0 = cand_sig
                if j == 1 and sig0 is not None and cand_sig == sig0 and attempt < 59:
                    continue  # identical; try again

                qid = f"{topic}__{tmpl.template_id}__{j+1}__{qseed}"
                qs.append(
                    GeneratedQuestion(
                        qid=qid,
                        topic=topic,
                        level_id=tmpl.level_id,
                        level_name=tmpl.level_name,
                        difficulty=tmpl.difficulty,
                        prompt=pr,
                        latex=latex,
                        answer_latex=ans,
                        working=working2,
                        template_id=tmpl.template_id,
                        seed=qseed,
                        diagram_png=diagram,
                    )
                )
                break

        grouped[topic] = qs

    return grouped, pair_params_map, level_name_map


def regenerate_question(
    topic: str,
    template_id: str,
    max_difficulty: int,
    new_seed: int,
    fixed_params: Optional[Dict[str, Any]] = None,
) -> GeneratedQuestion:
    tmpl = next((t for t in TEMPLATES if t.topic == topic and t.template_id == template_id and t.difficulty <= max_difficulty), None)
    if tmpl is None:
        raise ValueError("Template not found for regeneration.")
    res = tmpl.generator(random.Random(new_seed), new_seed, fixed_params)

    diagram = None
    if isinstance(res, tuple) and len(res) == 5:
        pr, latex, ans, working, diagram = res
    else:
        pr, latex, ans, working = res

    pr = pr.strip()
    latex = _sanitize_math(latex)
    ans = _sanitize_math(ans)
    working2: List[WorkingStep] = [(k, _sanitize_math(v)) for (k, v) in working]

    qid = f"{topic}__{template_id}__{new_seed}"
    return GeneratedQuestion(
        qid=qid,
        topic=topic,
        level_id=tmpl.level_id,
        level_name=tmpl.level_name,
        difficulty=tmpl.difficulty,
        prompt=pr,
        latex=latex,
        answer_latex=ans,
        working=working2,
        template_id=tmpl.template_id,
        seed=new_seed,
        diagram_png=diagram,
    )


def generate_questions_by_template(
    topic: str,
    template_id: str,
    max_difficulty: int,
    n: int,
    seed: int,
) -> List[GeneratedQuestion]:
    rng = random.Random(seed)
    out: List[GeneratedQuestion] = []
    for _ in range(n):
        qseed = rng.randint(1, 10**9)
        out.append(regenerate_question(topic, template_id, max_difficulty, qseed, fixed_params=None))
    return out


# --- Module diagnostics (prints to Streamlit logs) ---
QB_BUILD = "v39-qbank-black-diagrams-unique-pairs"
try:
    print(f"QB_BUILD={QB_BUILD}")
    print("QB_TOPICS=" + " | ".join(available_topics()))
except Exception as _e:
    print(f"QB_BUILD={QB_BUILD} (topics unavailable: {_e})")
