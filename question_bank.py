from __future__ import annotations

import random
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Dict, List, Tuple, Optional, Any

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
    return f"{ax} {'+' if b>0 else '-'} {abs(b)}"


def _sequence_str(seq: List[int]) -> str:
    # Use thin-spaces (\,) between terms to avoid accidental line-breaks (\\)
    # and to keep output compatible with both KaTeX (Streamlit) and matplotlib mathtext.
    return ",\\,".join(str(x) for x in seq) + r",\\,\\ldots"


def _sanitize_math(s: str) -> str:
    """Sanitise LaTeX so it works in both Streamlit (KaTeX) and Matplotlib mathtext."""
    return (
        s.replace("\t", " ")
        .replace("\x0c", "")
        # collapse accidental double-backslashes (e.g. \frac, \times, or line-breaks)
        .replace("\\\\", "\\")
        .replace("\\tfrac", "\\frac")
        .replace("\\dfrac", "\\frac")
    )


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


@dataclass(frozen=True)
class Template:
    template_id: str
    topic: str
    level_id: str
    level_name: str
    difficulty: int
    generator: Callable[[random.Random, int, Optional[Dict[str, Any]]], Tuple[str, str, str, List[WorkingStep]]]
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
    # Pair-locked ratio r, but starting value varies each regeneration.
    r = int(params["r"]) if params and "r" in params else rng.choice([2, 3])

    # Keep values easy (avoid very large terms).
    # We show 5 terms and ask for the next 2, so control the 5th term.
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
    answer = f"{nxt[0]},\, {nxt[1]}"
    working = [
        ("text", f"Multiply by {r} each time."),
        ("math", rf"{seq[-1]}\times {r}={nxt[0]}\quad {nxt[0]}\times {r}={nxt[1]}"),
    ]
    return prompt, latex, answer, working


def _gen_seq_div(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    # Pair-locked divisor r, but starting value varies each regeneration.
    # We guarantee the next two terms remain integers (no truncation).
    r = int(params["r"]) if params and "r" in params else rng.choice([2, 3])

    # We build 5 terms by dividing 4 times, then ask for the next 2.
    # Let term5 = k. To keep the next two terms integers, k must be a multiple of r^2.
    if r == 2:
        k_choices = [4, 8, 12, 16, 20]
    else:  # r == 3
        k_choices = [9, 18, 27]

    k = rng.choice(k_choices)
    a1 = k * (r ** 4)

    seq = [a1]
    for _ in range(4):
        seq.append(seq[-1] // r)

    nxt = [seq[-1] // r, seq[-1] // (r * r)]
    prompt = "Write the next two terms:"
    latex = _sequence_str(seq)
    answer = f"{nxt[0]},\, {nxt[1]}"
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
        ("math", rf"a_{{{n}}} = {A}\\times {n} {'+' if B>=0 else '-'} {abs(B)} = {value}"),
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




# --- Using the nth term (check membership) ---

def _gen_use_nth_is_term(rng: random.Random, seed: int, params: Optional[Dict[str, Any]]):
    """Given an nth term, decide whether a value is a term of the sequence."""
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
        # choose an offset so the resulting n is not an integer
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
    frac = Fraction(rhs, A)  # reduced; denominator positive
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
        ("math", rf"x = {c}\\times {a} = {x}"),
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
    else:  # decomp
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


# -----------------------------
# Templates / Levels
# -----------------------------

TEMPLATES: List[Template] = [
    # Continuing sequences levels (pair-locked step/ratio)
    Template(
        template_id="seq_add",
        topic="Continuing sequences",
        level_id="add",
        level_name="Add the same amount",
        difficulty=1,
        generator=_gen_seq_add,
        pair_params_factory=lambda r: {"d": r.choice([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12])},
    ),
    Template(
        template_id="seq_sub",
        topic="Continuing sequences",
        level_id="sub",
        level_name="Subtract the same amount",
        difficulty=2,
        generator=_gen_seq_sub,
        pair_params_factory=lambda r: {"s": r.choice([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12])},
    ),
    Template(
        template_id="seq_mul",
        topic="Continuing sequences",
        level_id="mul",
        level_name="Multiply by the same number",
        difficulty=3,
        generator=_gen_seq_mul,
        pair_params_factory=lambda r: {"r": r.choice([2, 3])},
    ),
    Template(
        template_id="seq_div",
        topic="Continuing sequences",
        level_id="div",
        level_name="Divide by the same number",
        difficulty=4,
        generator=_gen_seq_div,
        pair_params_factory=lambda r: {"r": r.choice([2, 3])},
    ),
    Template(
        template_id="seq_fibo",
        topic="Continuing sequences",
        level_id="fibo",
        level_name="Fibonacci",
        difficulty=5,
        generator=_gen_seq_fibo,
    ),

    # Finding nth term levels (difference sign + 0th term sign)
    Template(
        template_id="nth_pp",
        topic="Finding the nth term",
        level_id="pp",
        level_name="Positive difference, positive 0th term",
        difficulty=1,
        generator=lambda r, s, p: _gen_nth_term_arith(r, s, {"d_sign": 1, "a0_sign": 1}),
    ),
    Template(
        template_id="nth_pn",
        topic="Finding the nth term",
        level_id="pn",
        level_name="Positive difference, negative 0th term",
        difficulty=2,
        generator=lambda r, s, p: _gen_nth_term_arith(r, s, {"d_sign": 1, "a0_sign": -1}),
    ),
    Template(
        template_id="nth_np",
        topic="Finding the nth term",
        level_id="np",
        level_name="Negative difference, positive 0th term",
        difficulty=3,
        generator=lambda r, s, p: _gen_nth_term_arith(r, s, {"d_sign": -1, "a0_sign": 1}),
    ),
    Template(
        template_id="nth_nn",
        topic="Finding the nth term",
        level_id="nn",
        level_name="Negative difference, negative 0th term",
        difficulty=4,
        generator=lambda r, s, p: _gen_nth_term_arith(r, s, {"d_sign": -1, "a0_sign": -1}),
    ),

    # Using nth term
    Template(
        template_id="use_term_pos",
        topic="Using the nth term",
        level_id="term_pos",
        level_name="Find a term (positive coefficient)",
        difficulty=1,
        generator=lambda r, s, p: _gen_use_nth_find_term(r, s, {"a_sign": 1}),
    ),
    Template(
        template_id="use_term_neg",
        topic="Using the nth term",
        level_id="term_neg",
        level_name="Find a term (negative coefficient)",
        difficulty=2,
        generator=lambda r, s, p: _gen_use_nth_find_term(r, s, {"a_sign": -1}),
    ),
    Template(
        template_id="use_n_pos",
        topic="Using the nth term",
        level_id="n_pos",
        level_name="Find n (positive coefficient)",
        difficulty=3,
        generator=lambda r, s, p: _gen_use_nth_find_n(r, s, {"a_sign": 1}),
    ),
    Template(
        template_id="use_n_neg",
        topic="Using the nth term",
        level_id="n_neg",
        level_name="Find n (negative coefficient)",
        difficulty=4,
        generator=lambda r, s, p: _gen_use_nth_find_n(r, s, {"a_sign": -1}),
    ),


    Template(
        template_id="use_is_term_pos",
        topic="Using the nth term",
        level_id="is_term_pos",
        level_name="Is a value a term? (positive coefficient)",
        difficulty=5,
        generator=lambda r, s, p: _gen_use_nth_is_term(r, s, {"a_sign": 1}),
    ),
    Template(
        template_id="use_is_term_neg",
        topic="Using the nth term",
        level_id="is_term_neg",
        level_name="Is a value a term? (negative coefficient)",
        difficulty=5,
        generator=lambda r, s, p: _gen_use_nth_is_term(r, s, {"a_sign": -1}),
    ),
    # 1-step equations
    Template("eq1_add", "Solving 1 step equations", "add", "x + b = c", 1, _gen_eq_1_add),
    Template("eq1_sub", "Solving 1 step equations", "sub", "x - b = c", 2, _gen_eq_1_sub),
    Template("eq1_mul", "Solving 1 step equations", "mul", "ax = c", 3, _gen_eq_1_mul),
    Template("eq1_div", "Solving 1 step equations", "div", "x/a = c", 4, _gen_eq_1_div),

    # 2-step equations
    Template(
        "eq2_plus",
        "Solving 2 step equations",
        "ax_plus",
        "ax + b = c (b positive)",
        1,
        lambda r, s, p: _gen_eq_2_ax_plus_b(r, s, {"b_sign": 1}),
    ),
    Template(
        "eq2_minus",
        "Solving 2 step equations",
        "ax_minus",
        "ax - b = c (b positive)",
        2,
        lambda r, s, p: _gen_eq_2_ax_plus_b(r, s, {"b_sign": -1}),
    ),
    Template(
        "eq2_br_plus",
        "Solving 2 step equations",
        "a_br_plus",
        "a(x + b) = c",
        3,
        lambda r, s, p: _gen_eq_2_a_bracket(r, s, {"inside_sign": 1}),
    ),
    Template(
        "eq2_br_minus",
        "Solving 2 step equations",
        "a_br_minus",
        "a(x - b) = c",
        4,
        lambda r, s, p: _gen_eq_2_a_bracket(r, s, {"inside_sign": -1}),
    ),

    # Percent of an amount (non-calc)
    Template(
        "pct_nc_simple",
        "Finding percentages using non-calculator methods",
        "simple",
        "10%, 20%, 25%, 50%",
        1,
        lambda r, s, p: _gen_pct_noncalc(r, s, {"level": "simple"}),
    ),
    Template(
        "pct_nc_5_15",
        "Finding percentages using non-calculator methods",
        "five_fifteen",
        "5% and 15%",
        2,
        lambda r, s, p: _gen_pct_noncalc(r, s, {"level": "five_fifteen"}),
    ),
    Template(
        "pct_nc_eighths",
        "Finding percentages using non-calculator methods",
        "eighths",
        "12.5% and 37.5%",
        3,
        lambda r, s, p: _gen_pct_noncalc(r, s, {"level": "eighths"}),
    ),
    Template(
        "pct_nc_decomp",
        "Finding percentages using non-calculator methods",
        "decomp",
        "Build from 10% and 5%",
        4,
        lambda r, s, p: _gen_pct_noncalc(r, s, {"level": "decomp"}),
    ),

    # Percent of an amount (calc)
    Template(
        "pct_c_int",
        "Finding percentages using calculator methods",
        "int",
        "Whole-number percentages",
        1,
        lambda r, s, p: _gen_pct_calc(r, s, {"level": "int"}),
    ),
    Template(
        "pct_c_dec",
        "Finding percentages using calculator methods",
        "dec",
        "Decimal percentages (e.g. 12.5%)",
        2,
        lambda r, s, p: _gen_pct_calc(r, s, {"level": "dec"}),
    ),

    # Inc/dec non-calc
    Template(
        "inc_nc_simple",
        "Increasing and decreasing by percentages using non-calculator methods",
        "inc_simple",
        "Increase by 10%, 20% or 25%",
        1,
        lambda r, s, p: _gen_inc_dec_noncalc(r, s, {"direction": "increase", "family": "simple"}),
    ),
    Template(
        "dec_nc_simple",
        "Increasing and decreasing by percentages using non-calculator methods",
        "dec_simple",
        "Decrease by 10%, 20% or 25%",
        2,
        lambda r, s, p: _gen_inc_dec_noncalc(r, s, {"direction": "decrease", "family": "simple"}),
    ),
    Template(
        "inc_nc_mix",
        "Increasing and decreasing by percentages using non-calculator methods",
        "inc_mix",
        "Increase by 5%, 15% or 30%",
        3,
        lambda r, s, p: _gen_inc_dec_noncalc(r, s, {"direction": "increase", "family": "mix"}),
    ),
    Template(
        "dec_nc_mix",
        "Increasing and decreasing by percentages using non-calculator methods",
        "dec_mix",
        "Decrease by 5%, 15% or 30%",
        4,
        lambda r, s, p: _gen_inc_dec_noncalc(r, s, {"direction": "decrease", "family": "mix"}),
    ),

    # Inc/dec calc
    Template(
        "inc_c",
        "Increasing and decreasing by percentages using calculator methods",
        "inc",
        "Increase using a multiplier",
        1,
        lambda r, s, p: _gen_inc_dec_calc(r, s, {"direction": "increase"}),
    ),
    Template(
        "dec_c",
        "Increasing and decreasing by percentages using calculator methods",
        "dec",
        "Decrease using a multiplier",
        2,
        lambda r, s, p: _gen_inc_dec_calc(r, s, {"direction": "decrease"}),
    ),

    # Completing the square
    Template(
        "cs_even",
        "Completing the square",
        "a1_even",
        "a = 1, even x coefficient",
        1,
        lambda r, s, p: _gen_complete_square_a1(r, s, {"b_parity": "even"}),
    ),
    Template(
        "cs_odd",
        "Completing the square",
        "a1_odd",
        "a = 1, odd x coefficient",
        2,
        lambda r, s, p: _gen_complete_square_a1(r, s, {"b_parity": "odd"}),
    ),
    Template(
        "cs_a_int",
        "Completing the square",
        "a_int",
        "a \\neq 1, integer half inside",
        3,
        lambda r, s, p: _gen_complete_square_a_not1(r, s, {"frac_inside": False}),
    ),
    Template(
        "cs_a_frac",
        "Completing the square",
        "a_frac",
        "a \\neq 1, fractional half inside",
        4,
        lambda r, s, p: _gen_complete_square_a_not1(r, s, {"frac_inside": True}),
    ),
]


# -----------------------------
# Public API
# -----------------------------


def available_topics() -> List[str]:
    return sorted({t.topic for t in TEMPLATES})


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
    """Return (grouped_questions, pair_params_map, level_name_map)."""
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
        for j in range(2):
            qseed = master.randint(1, 10**9)
            pr, latex, ans, working = tmpl.generator(random.Random(qseed), qseed, pair_params)

            pr = pr.strip()
            latex = _sanitize_math(latex)
            ans = _sanitize_math(ans)
            working2: List[WorkingStep] = [(k, _sanitize_math(v)) for (k, v) in working]

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
                )
            )
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

    pr, latex, ans, working = tmpl.generator(random.Random(new_seed), new_seed, fixed_params)

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
