from __future__ import annotations

import hashlib
import io
import random
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

_BG = (0, 0, 0)
_FG = (255, 255, 255)


def _default_font(size: int = 18):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=size)
    except Exception:
        return ImageFont.load_default()


def _img_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _rectilinear_notch_diagram(W: str, H: str, L1: str, w: str, L2: str, d: str) -> bytes:
    """Rectilinear notch shape with labels. Black background, white lines."""
    img = Image.new("RGB", (520, 240), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(18)

    x0, y0 = 60, 200
    x1, y1 = 460, 40

    notch_left = 220
    notch_w = 90
    notch_d = 60

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

    def mid(a, b):
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)

    mx, my = mid(p0, p1)
    draw.text((mx - 12, my + 8), W, fill=_FG, font=font)

    mx, my = mid(p1, p2)
    draw.text((mx + 10, my - 10), H, fill=_FG, font=font)

    mx, my = mid(p7, p6)
    draw.text((mx - 12, my - 28), L1, fill=_FG, font=font)

    mx, my = mid(p5, p4)
    draw.text((mx - 8, my + 10), w, fill=_FG, font=font)

    mx, my = mid(p3, p2)
    draw.text((mx - 8, my - 28), L2, fill=_FG, font=font)

    mx, my = mid(p3, p4)
    draw.text((mx + 10, my - 10), d, fill=_FG, font=font)

    return _img_bytes(img)


def _rectangle_diagram(L: str, W: str) -> bytes:
    """Axis-aligned rectangle labelled with length (bottom) and width (right)."""
    img = Image.new("RGB", (420, 220), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(18)

    x0, y0 = 70, 180
    x1, y1 = 350, 60
    draw.rectangle([x0, y1, x1, y0], outline=_FG, width=4)

    draw.text(((x0 + x1) / 2 - 10, y0 + 8), L, fill=_FG, font=font)
    draw.text((x1 + 10, (y0 + y1) / 2 - 10), W, fill=_FG, font=font)
    return _img_bytes(img)


def _triangle_diagram(base: str, height: str) -> bytes:
    """Triangle with a height dropped to the base (perpendicular)."""
    img = Image.new("RGB", (420, 240), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(18)

    A = (80, 190)
    B = (340, 190)
    C = (260, 70)

    draw.line([A, B, C, A], fill=_FG, width=4)

    foot = (C[0], A[1])
    draw.line([C, foot], fill=_FG, width=2)

    ra = 10
    draw.line(
        [(foot[0], foot[1]), (foot[0] - ra, foot[1]), (foot[0] - ra, foot[1] - ra)],
        fill=_FG,
        width=2,
    )

    draw.text(((A[0] + B[0]) / 2 - 10, A[1] + 8), base, fill=_FG, font=font)
    draw.text((foot[0] + 10, (C[1] + foot[1]) / 2 - 10), height, fill=_FG, font=font)
    return _img_bytes(img)


def _parallelogram_diagram(base: str, height: str) -> bytes:
    img = Image.new("RGB", (460, 240), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(18)

    A = (110, 190)
    B = (360, 190)
    D = (70, 80)
    C = (320, 80)

    draw.line([A, B, C, D, A], fill=_FG, width=4)

    foot = (D[0], A[1])
    draw.line([D, foot], fill=_FG, width=2)

    ra = 10
    draw.line([(foot[0], foot[1]), (foot[0] + ra, foot[1]), (foot[0] + ra, foot[1] - ra)], fill=_FG, width=2)

    draw.text(((A[0] + B[0]) / 2 - 10, A[1] + 8), base, fill=_FG, font=font)
    draw.text((foot[0] - 25, (D[1] + foot[1]) / 2 - 10), height, fill=_FG, font=font)
    return _img_bytes(img)


def _trapezium_diagram(a: str, b: str, h: str) -> bytes:
    """Trapezium with parallel sides a (top) and b (bottom) and height h."""
    img = Image.new("RGB", (480, 260), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(18)

    A = (120, 200)
    B = (380, 200)
    D = (160, 80)
    C = (320, 80)

    draw.line([A, B, C, D, A], fill=_FG, width=4)

    foot = (D[0], A[1])
    draw.line([D, foot], fill=_FG, width=2)

    ra = 10
    draw.line([(foot[0], foot[1]), (foot[0] + ra, foot[1]), (foot[0] + ra, foot[1] - ra)], fill=_FG, width=2)

    draw.text(((D[0] + C[0]) / 2 - 10, D[1] - 28), a, fill=_FG, font=font)
    draw.text(((A[0] + B[0]) / 2 - 10, A[1] + 8), b, fill=_FG, font=font)
    draw.text((foot[0] - 25, (D[1] + foot[1]) / 2 - 10), h, fill=_FG, font=font)
    return _img_bytes(img)


def _kite_diagram(d1: str, d2: str) -> bytes:
    """Kite/rhombus with diagonals labelled."""
    img = Image.new("RGB", (420, 260), _BG)
    draw = ImageDraw.Draw(img)
    font = _default_font(18)

    top = (210, 60)
    right = (330, 130)
    bottom = (210, 210)
    left = (90, 130)

    draw.line([top, right, bottom, left, top], fill=_FG, width=4)

    draw.line([top, bottom], fill=_FG, width=2)
    draw.line([left, right], fill=_FG, width=2)

    draw.text((225, 125), d1, fill=_FG, font=font)
    draw.text((170, 145), d2, fill=_FG, font=font)
    return _img_bytes(img)


# -----------------------------
# Data models
# -----------------------------

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
    "Finding percentages using non-calculator methods",
    "Finding percentages using calculator methods",
    "Increasing and decreasing by percentages using non-calculator methods",
    "Increasing and decreasing by percentages using calculator methods",
    "Completing the square",
    "Perimeter of rectilinear shapes",
    "Area of shapes",
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
    "Finding percentages using non-calculator methods": {"primary": "Ratio and proportion", "tags": ["Ratio and proportion"]},
    "Finding percentages using calculator methods": {"primary": "Ratio and proportion", "tags": ["Ratio and proportion"]},
    "Increasing and decreasing by percentages using non-calculator methods": {"primary": "Ratio and proportion", "tags": ["Ratio and proportion"]},
    "Increasing and decreasing by percentages using calculator methods": {"primary": "Ratio and proportion", "tags": ["Ratio and proportion"]},

    # Geometry & measures
    "Perimeter of rectilinear shapes": {"primary": "Geometry and measures", "tags": ["Geometry and measures"]},
    "Area of shapes": {"primary": "Geometry and measures", "tags": ["Geometry and measures"]},
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
