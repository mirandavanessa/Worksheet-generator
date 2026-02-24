from __future__ import annotations

import random
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Dict, List, Tuple, Optional


# -----------------------------
# Helpers (formatting)
# -----------------------------

def _sgn(n: int) -> str:
    return "+" if n >= 0 else "-"

def _fmt_int(n: int) -> str:
    return str(n)

def _fmt_frac(fr: Fraction) -> str:
    fr = fr.limit_denominator()
    if fr.denominator == 1:
        return str(fr.numerator)
    return rf"\frac{{{fr.numerator}}}{{{fr.denominator}}}"

def _fmt_coef(coef: int, var: str = "x") -> str:
    """Format ax with no '1x' and correct sign handled by caller."""
    if coef == 0:
        return "0"
    if coef == 1:
        return var
    if coef == -1:
        return "-" + var
    return f"{coef}{var}"

def _join_terms(terms: List[Tuple[int, str]]) -> str:
    """
    Join signed terms where each term is (signless_coef, latex_term_without_sign)
    The first term may be negative via coef<0 in latex_term, so prefer caller handles.
    This is used sparingly.
    """
    out: List[str] = []
    for i, (sign, body) in enumerate(terms):
        if i == 0:
            out.append(body if sign >= 0 else f"- {body}")
        else:
            out.append(f"{'+' if sign >= 0 else '-'} {body}")
    return " ".join(out)

def _lin_expr(a: int, b: int, var: str = "x") -> str:
    """Return latex for ax + b with clean formatting (no 1x)."""
    if a == 0:
        return _fmt_int(b)
    ax = _fmt_coef(a, var)
    if b == 0:
        return ax
    return f"{ax} {'+' if b>0 else '-'} {abs(b)}"

def _sequence_str(seq: List[int]) -> str:
    return ",\ ".join(str(x) for x in seq) + r",\ \ldots"


# -----------------------------
# Data structures
# -----------------------------

WorkingStep = Tuple[str, str]  # ("text"|"math", content)

@dataclass(frozen=True)
class GeneratedQuestion:
    qid: str
    topic: str
    difficulty: int
    prompt: str                 # plain text (shown above latex)
    latex: str                  # math expression, no $ delimiters
    answer_latex: str           # math expression for final answer, no $ delimiters
    working: List[WorkingStep]  # mixed text/math steps
    template_id: str            # used for "new version" regen
    seed: int                   # seed that generated this instance


@dataclass(frozen=True)
class Template:
    template_id: str
    topic: str
    difficulty: int
    generator: Callable[[random.Random, int], Tuple[str, str, str, List[WorkingStep]]]
    # generator returns (prompt, latex, answer_latex, working)


# -----------------------------
# Topic templates
# -----------------------------

def _gen_continuing_sequences(rng: random.Random, seed: int):
    # Mainly arithmetic; occasional simple patterns.
    kind = rng.choices(
        ["arith", "fibo_like", "alt_add", "square_plus"],
        weights=[70, 10, 10, 10],
        k=1
    )[0]

    if kind == "arith":
        a1 = rng.randint(-10, 20)
        d = rng.choice([1,2,3,4,5,6,8,10,-1,-2,-3,-4,-5])
        seq = [a1 + i*d for i in range(5)]
        next_terms = [a1 + 5*d, a1 + 6*d]
        prompt = "Write the next two terms:"
        latex = _sequence_str(seq)
        answer = ",\ ".join(str(x) for x in next_terms)
        working = [
            ("text", f"Common difference is {d}."),
            ("math", rf"\mathrm{{Next\ terms:}}\ {seq[-1]}{('+' if d>=0 else '')}{d}={next_terms[0]},\ {next_terms[0]}{('+' if d>=0 else '')}{d}={next_terms[1]}"),
        ]
        return prompt, latex, answer, working

    if kind == "fibo_like":
        # simple Fibonacci-style: a,b,a+b,...
        a = rng.randint(1, 12)
        b = rng.randint(1, 12)
        seq = [a, b]
        for _ in range(3):
            seq.append(seq[-1] + seq[-2])
        next_terms = [seq[-1] + seq[-2], (seq[-1] + seq[-2]) + seq[-1]]
        prompt = "Write the next two terms:"
        latex = _sequence_str(seq)
        answer = ",\ ".join(str(x) for x in next_terms)
        working = [
            ("text", "Each term is the sum of the previous two terms."),
            ("math", rf"{seq[-2]}+{seq[-1]}={next_terms[0]},\ {seq[-1]}+{next_terms[0]}={next_terms[1]}"),
        ]
        return prompt, latex, answer, working

    if kind == "alt_add":
        start = rng.randint(-10, 20)
        p = rng.choice([2,3,4,5,6,7])
        q = rng.choice([1,2,3,4,5])
        seq = [start]
        for i in range(4):
            seq.append(seq[-1] + (p if i%2==0 else -q))
        # continue pattern
        next1 = seq[-1] + (p if 4%2==0 else -q)
        next2 = next1 + (p if 5%2==0 else -q)
        prompt = "Write the next two terms:"
        latex = _sequence_str(seq)
        answer = f"{next1},\ {next2}"
        working = [
            ("text", f"Repeat: add {p}, then subtract {q}."),
            ("math", rf"{seq[-1]}+{p}={next1},\ {next1}-{q}={next2}"),
        ]
        return prompt, latex, answer, working

    # square_plus
    n = rng.randint(1, 5)
    k = rng.randint(-5, 10)
    seq = [(n+i)**2 + k for i in range(5)]
    next_terms = [(n+5)**2 + k, (n+6)**2 + k]
    prompt = "Write the next two terms:"
    latex = _sequence_str(seq)
    answer = f"{next_terms[0]},\ {next_terms[1]}"
    working = [
        ("text", f"These are square numbers with {k:+d} added."),
        ("math", rf"( {n+5})^2 {('+' if k>=0 else '-') } {abs(k)} = {next_terms[0]}"),
        ("math", rf"( {n+6})^2 {('+' if k>=0 else '-') } {abs(k)} = {next_terms[1]}"),
    ]
    return prompt, latex, answer, working



def _gen_find_nth_term(rng: random.Random, seed: int):
    # Arithmetic sequence (GCSE standard) – use difference + 0th term method
    a1 = rng.randint(-6, 12)
    d = rng.choice([1,2,3,4,5,6,7,8,9,-1,-2,-3,-4,-5])
    seq = [a1 + i*d for i in range(5)]
    prompt = "Find the nth term of the sequence:"
    latex = _sequence_str(seq)

    # 0th term method: a_0 = a_1 - d, then a_n = dn + a_0
    a0 = a1 - d
    answer = _lin_expr(d, a0, "n")

    d_str = f"{d}" if d >= 0 else f"({d})"
    working = [
        ("text", f"The common difference is {d}."),
        ("math", rf"a_0 = a_1 - d = {a1} - {d_str} = {a0}"),
        ("math", rf"a_n = d n + a_0 = {d}n + {a0}"),
        ("math", rf"a_n = {answer}"),
    ]
    return prompt, latex, answer, working


def _gen_use_nth_term_find_term(rng: random.Random, seed: int):
    # Given nth term, find a specific term
    A = rng.choice([1,2,3,4,5,6,7,8,-1,-2,-3,-4,-5])
    B = rng.randint(-20, 20)
    n = rng.choice([10, 12, 15, 20, 25])
    expr = _lin_expr(A, B, "n")
    value = A*n + B
    prompt = f"Given the nth term is shown, find the {n}th term:"
    latex = expr
    answer = str(value)
    working = [
        ("math", rf"a_n = {expr}"),
        ("math", rf"a_{{{n}}} = {A}	imes {n} {('+' if B>=0 else '-') } {abs(B)} = {value}"),
    ]
    return prompt, latex, answer, working


def _gen_use_nth_term_find_n(rng: random.Random, seed: int):
    # Given nth term, find which term equals a value (solve for n)
    A = rng.choice([2,3,4,5,6,7,8,9])
    B = rng.randint(-20, 20)
    n = rng.choice([8, 9, 10, 11, 12, 15, 20])
    target = A*n + B
    expr = _lin_expr(A, B, "n")
    prompt = f"The nth term is shown. Which term is {target}?"
    latex = expr
    answer = rf"n = {n}"
    working = [
        ("math", rf"{expr} = {target}"),
        ("math", rf"{A}n {('+' if B>=0 else '-') } {abs(B)} = {target}"),
        ("math", rf"{A}n = {target - B}"),
        ("math", rf"n = rac{{{target - B}}}{{{A}}} = {n}"),
    ]
    return prompt, latex, answer, working


def _gen_one_step_equation(rng: random.Random, seed: int):
    kind = rng.choice(["add", "sub", "mul", "div"])
    x = rng.randint(-12, 12)
    if kind == "add":
        b = rng.randint(-15, 15)
        c = x + b
        prompt = "Solve the equation:"
        latex = rf"x {('+' if b>=0 else '-') } {abs(b)} = {c}"
        answer = rf"x = {x}"
        working = [
            ("math", rf"x {('+' if b>=0 else '-') } {abs(b)} = {c}"),
            ("text", f"{'Subtract' if b>=0 else 'Add'} {abs(b)} from both sides."),
            ("math", rf"x = {c} {('-' if b>=0 else '+')} {abs(b)} = {x}"),
        ]
        return prompt, latex, answer, working

    if kind == "sub":
        b = rng.randint(-15, 15)
        c = x - b
        prompt = "Solve the equation:"
        latex = rf"x {('-' if b>=0 else '+')} {abs(b)} = {c}"
        answer = rf"x = {x}"
        working = [
            ("math", rf"x {('-' if b>=0 else '+')} {abs(b)} = {c}"),
            ("text", f"{'Add' if b>=0 else 'Subtract'} {abs(b)} on both sides."),
            ("math", rf"x = {c} {('+' if b>=0 else '-')} {abs(b)} = {x}"),
        ]
        return prompt, latex, answer, working

    if kind == "mul":
        a = rng.choice([2,3,4,5,6,7,8,9,-2,-3,-4,-5])
        c = a * x
        prompt = "Solve the equation:"
        latex = rf"{_fmt_coef(a,'x')} = {c}"
        answer = rf"x = {x}"
        working = [
            ("math", rf"{_fmt_coef(a,'x')} = {c}"),
            ("text", f"Divide both sides by {a}."),
            ("math", rf"x = \frac{{{c}}}{{{a}}} = {x}"),
        ]
        return prompt, latex, answer, working

    # div: x/a = c  -> x = ac
    a = rng.choice([2,3,4,5,6,7,8,9])
    c = rng.randint(-10, 10)
    x = a*c
    prompt = "Solve the equation:"
    latex = rf"\frac{{x}}{{{a}}} = {c}"
    answer = rf"x = {x}"
    working = [
        ("math", rf"\frac{{x}}{{{a}}} = {c}"),
        ("text", f"Multiply both sides by {a}."),
        ("math", rf"x = {c}\times {a} = {x}"),
    ]
    return prompt, latex, answer, working


def _gen_two_step_equation(rng: random.Random, seed: int):
    kind = rng.choice(["ax_b", "a_xplusb"])
    x = rng.randint(-10, 10)
    if kind == "ax_b":
        a = rng.choice([2,3,4,5,6,7,8,9,-2,-3,-4,-5])
        b = rng.randint(-20, 20)
        c = a*x + b
        prompt = "Solve the equation:"
        latex = rf"{_lin_expr(a, b, 'x')} = {c}"
        answer = rf"x = {x}"
        working = [
            ("math", rf"{_lin_expr(a, b, 'x')} = {c}"),
            ("text", f"{'Subtract' if b>=0 else 'Add'} {abs(b)} from both sides."),
            ("math", rf"{_fmt_coef(a,'x')} = {c - b}"),
            ("text", f"Divide both sides by {a}."),
            ("math", rf"x = \frac{{{c - b}}}{{{a}}} = {x}"),
        ]
        return prompt, latex, answer, working

    # a(x+b)=c
    a = rng.choice([2,3,4,5,6,7,8,9])
    b = rng.randint(-12, 12)
    c = a*(x + b)
    prompt = "Solve the equation:"
    latex = rf"{a}(x {('+' if b>=0 else '-') } {abs(b)}) = {c}"
    answer = rf"x = {x}"
    working = [
        ("math", rf"{a}(x {('+' if b>=0 else '-') } {abs(b)}) = {c}"),
        ("text", f"Divide both sides by {a}."),
        ("math", rf"x {('+' if b>=0 else '-') } {abs(b)} = {c//a}"),
        ("text", f"{'Subtract' if b>=0 else 'Add'} {abs(b)} from both sides."),
        ("math", rf"x = {c//a} {('-' if b>=0 else '+')} {abs(b)} = {x}"),
    ]
    return prompt, latex, answer, working


def _gen_percent_noncalc(rng: random.Random, seed: int):
    # Prefer friendly %: 10, 20, 25, 50, 5, 15, 12.5
    pct = rng.choice([5,10,15,20,25,50,12.5])
    # Choose amount so answers are clean
    amount = rng.choice([40,60,80,120,160,200,240,320,360,400,480,600,720,800])
    prompt = "Find:"
    latex = rf"{pct}\%\ \mathrm{{of}}\ {amount}"
    # compute
    value = amount * (pct/100)
    # format answer: integer or .5 or .25 etc
    if abs(value - round(value)) < 1e-9:
        ans = str(int(round(value)))
    else:
        # use Fraction
        fr = Fraction(str(value)).limit_denominator()
        ans = _fmt_frac(fr) if fr.denominator != 1 else str(fr.numerator)
        # If it's a terminating .5, show as decimal too? keep fractional for non-calc maybe
        # We'll show exact decimal if denominator is 2 or 4 or 8.
        if fr.denominator in (2,4,8):
            ans = str(float(fr))
    answer = ans
    working: List[WorkingStep] = []
    if pct == 10:
        working = [("text", "10% is one tenth."), ("math", rf"{amount}\div 10 = {amount//10}")]
    elif pct == 20:
        working = [("text", "20% = 2 × 10%."), ("math", rf"10\%:\ {amount}\div 10 = {amount//10}"), ("math", rf"20\%:\ 2\times {amount//10} = {int(value)}")]
    elif pct == 25:
        working = [("text", "25% is a quarter."), ("math", rf"{amount}\div 4 = {int(value)}")]
    elif pct == 50:
        working = [("text", "50% is a half."), ("math", rf"{amount}\div 2 = {int(value)}")]
    elif pct == 5:
        working = [("text", "5% is half of 10%."), ("math", rf"10\%:\ {amount}\div 10 = {amount//10}"), ("math", rf"5\%:\ \frac{{{amount//10}}}{{2}} = {value}")]
    elif pct == 15:
        working = [("text", "15% = 10% + 5%."), ("math", rf"10\%:\ {amount}\div 10 = {amount//10}"), ("math", rf"5\%:\ \frac{{{amount//10}}}{{2}} = {amount//20}"), ("math", rf"15\%:\ {amount//10} + {amount//20} = {value}")]
    else:  # 12.5
        working = [("text", "12.5% is one eighth."), ("math", rf"{amount}\div 8 = {value}")]
    return prompt, latex, str(value).rstrip('0').rstrip('.') if isinstance(value, float) else answer, working


def _gen_percent_calc(rng: random.Random, seed: int):
    pct = rng.choice([7,12,17,18,23,34,42,65])
    amount = rng.randint(120, 950)
    prompt = "Find (calculator method):"
    latex = rf"{pct}\%\ \mathrm{{of}}\ {amount}"
    value = amount * pct / 100
    # 2 d.p. by default for calculator questions
    ans = f"{value:.2f}".rstrip('0').rstrip('.')
    working = [
        ("text", f"Convert {pct}% to a decimal."),
        ("math", rf"{pct}\% = {pct/100}"),
        ("math", rf"{amount}\times {pct/100} = {ans}"),
    ]
    return prompt, latex, ans, working


def _gen_inc_dec_noncalc(rng: random.Random, seed: int):
    inc = rng.choice(["increase", "decrease"])
    pct = rng.choice([5,10,15,20,25,30])
    amount = rng.choice([80,120,160,200,240,300,320,360,400,480,600,720])
    prompt = f"{inc.capitalize()} {amount} by {pct}% (non-calculator)."
    latex = ""
    delta = amount * pct/100
    new = amount + delta if inc == "increase" else amount - delta
    # keep integer results
    ans = str(int(new))
    working: List[WorkingStep] = [
        ("text", f"Find {pct}% of {amount}."),
        ("math", rf"10\%:\ {amount}\div 10 = {amount//10}"),
    ]
    if pct == 5:
        working.append(("math", rf"5\%:\ \frac{{{amount//10}}}{{2}} = {amount//20}"))
        delta_val = amount//20
    elif pct == 10:
        delta_val = amount//10
    elif pct == 15:
        working.append(("math", rf"5\%:\ \frac{{{amount//10}}}{{2}} = {amount//20}"))
        delta_val = amount//10 + amount//20
        working.append(("math", rf"15\%:\ {amount//10}+{amount//20} = {delta_val}"))
    elif pct == 20:
        delta_val = 2*(amount//10)
        working.append(("math", rf"20\%:\ 2\times {amount//10} = {delta_val}"))
    elif pct == 25:
        delta_val = amount//4
        working = [("text", "25% is a quarter."), ("math", rf"{amount}\div 4 = {delta_val}")]
    else:  # 30
        delta_val = 3*(amount//10)
        working.append(("math", rf"30\%:\ 3\times {amount//10} = {delta_val}"))

    if inc == "increase":
        working.append(("text", "Add the percentage change to the original amount."))
        working.append(("math", rf"{amount} + {delta_val} = {ans}"))
    else:
        working.append(("text", "Subtract the percentage change from the original amount."))
        working.append(("math", rf"{amount} - {delta_val} = {ans}"))
    return prompt, latex, ans, working


def _gen_inc_dec_calc(rng: random.Random, seed: int):
    inc = rng.choice(["increase", "decrease"])
    pct = rng.choice([7,12,18,23,35,42])
    amount = rng.randint(120, 900)
    prompt = f"{inc.capitalize()} {amount} by {pct}% (calculator)."
    latex = ""
    multiplier = 1 + pct/100 if inc == "increase" else 1 - pct/100
    new = amount * multiplier
    ans = f"{new:.2f}".rstrip('0').rstrip('.')
    working = [
        ("text", f"Use a multiplier."),
        ("math", rf"\mathrm{{Multiplier}} = {multiplier}"),
        ("math", rf"{amount}\times {multiplier} = {ans}"),
    ]
    return prompt, latex, ans, working


def _gen_complete_square(rng: random.Random, seed: int):
    # Coefficient of x^2 is 1 (GCSE). Encourage fractional half when b is odd.
    b = rng.choice([-9,-7,-5,-3,-1,1,3,5,7,9, -8,-6,-4,-2,2,4,6,8])
    c = rng.randint(-12, 20)
    prompt = "Complete the square:"
    expr = rf"x^2 {('+' if b>0 else '-') } {abs(b)}x {('+' if c>=0 else '-') } {abs(c)}" if c != 0 else rf"x^2 {('+' if b>0 else '-') } {abs(b)}x"
    half = Fraction(b, 2)
    half_l = _fmt_frac(half) if half.denominator != 1 else str(half.numerator)
    # Build bracket term
    bracket = rf"(x {('+' if half>0 else '-') } {abs(half)})" if half.denominator == 1 else rf"(x {('+' if half>0 else '-') } \frac{{{abs(half.numerator)}}}{{{half.denominator}}})"
    # Working per preferred style (odd b -> fraction method with common denominator)
    working: List[WorkingStep] = [("math", expr)]
    if half.denominator != 1:
        # 5-line method
        working.append(("math", rf"= {bracket}^2 - (\frac{{{abs(half.numerator)}}}{{{half.denominator}}})^2 {('+' if c>=0 else '-') } {abs(c)}"))
        working.append(("math", rf"= {bracket}^2 - \frac{{{half.numerator**2}}}{{{half.denominator**2}}} {('+' if c>=0 else '-') } {abs(c)}"))
        # Convert c to /den^2
        den2 = half.denominator**2
        c_frac = Fraction(c, 1)
        c_as = Fraction(c * den2, den2)
        working.append(("math", rf"= {bracket}^2 - \frac{{{half.numerator**2}}}{{{den2}}} {('+' if c>=0 else '-') } \frac{{{abs(c_as.numerator)}}}{{{den2}}}"))
        const = Fraction(c,1) - Fraction(half.numerator**2, den2)
        # Simplify
        working.append(("math", rf"= {bracket}^2 {('+' if const>=0 else '-') } {_fmt_frac(abs(const))}"))
        answer = rf"{bracket}^2 {('+' if const>=0 else '-') } {_fmt_frac(abs(const))}"
    else:
        h = half.numerator
        working.append(("math", rf"= (x {('+' if h>0 else '-') } {abs(h)})^2 - {h}^2 {('+' if c>=0 else '-') } {abs(c)}"))
        const = c - h*h
        working.append(("math", rf"= (x {('+' if h>0 else '-') } {abs(h)})^2 {('+' if const>=0 else '-') } {abs(const)}"))
        answer = rf"(x {('+' if h>0 else '-') } {abs(h)})^2 {('+' if const>=0 else '-') } {abs(const)}"

    return prompt, expr, answer, working


TEMPLATES: List[Template] = [
    Template("seq_continue_1", "Continuing sequences", 1, lambda r, s: _gen_continuing_sequences(r, s)),
    Template("seq_continue_2", "Continuing sequences", 2, lambda r, s: _gen_continuing_sequences(r, s)),

    Template("nth_find_1", "Finding the nth term", 2, lambda r, s: _gen_find_nth_term(r, s)),
    Template("nth_find_2", "Finding the nth term", 3, lambda r, s: _gen_find_nth_term(r, s)),

    Template("nth_use_term", "Using the nth term", 2, lambda r, s: _gen_use_nth_term_find_term(r, s)),
    Template("nth_use_n", "Using the nth term", 3, lambda r, s: _gen_use_nth_term_find_n(r, s)),

    Template("eq_one_1", "Solving 1 step equations", 1, lambda r, s: _gen_one_step_equation(r, s)),
    Template("eq_one_2", "Solving 1 step equations", 2, lambda r, s: _gen_one_step_equation(r, s)),

    Template("eq_two_1", "Solving 2 step equations", 2, lambda r, s: _gen_two_step_equation(r, s)),
    Template("eq_two_2", "Solving 2 step equations", 3, lambda r, s: _gen_two_step_equation(r, s)),

    Template("pct_noncalc_1", "Finding percentages using non-calculator methods", 2, lambda r, s: _gen_percent_noncalc(r, s)),
    Template("pct_noncalc_2", "Finding percentages using non-calculator methods", 3, lambda r, s: _gen_percent_noncalc(r, s)),

    Template("pct_calc_1", "Finding percentages using calculator methods", 2, lambda r, s: _gen_percent_calc(r, s)),
    Template("pct_calc_2", "Finding percentages using calculator methods", 3, lambda r, s: _gen_percent_calc(r, s)),

    Template("incdec_noncalc_1", "Increasing and decreasing by percentages using non-calculator methods", 2, lambda r, s: _gen_inc_dec_noncalc(r, s)),
    Template("incdec_noncalc_2", "Increasing and decreasing by percentages using non-calculator methods", 3, lambda r, s: _gen_inc_dec_noncalc(r, s)),

    Template("incdec_calc_1", "Increasing and decreasing by percentages using calculator methods", 2, lambda r, s: _gen_inc_dec_calc(r, s)),
    Template("incdec_calc_2", "Increasing and decreasing by percentages using calculator methods", 3, lambda r, s: _gen_inc_dec_calc(r, s)),

    Template("comp_sq_1", "Completing the square", 4, lambda r, s: _gen_complete_square(r, s)),
]


def available_topics() -> List[str]:
    return sorted({t.topic for t in TEMPLATES})

def _templates_for(topic: str, max_difficulty: int) -> List[Template]:
    return [t for t in TEMPLATES if t.topic == topic and t.difficulty <= max_difficulty]

def generate_two_per_topic(topics: List[str], max_difficulty: int, seed: int) -> Dict[str, List[GeneratedQuestion]]:
    """
    For each topic: generate exactly two questions (side-by-side).
    """
    rng = random.Random(seed)
    out: Dict[str, List[GeneratedQuestion]] = {}
    for topic in topics:
        cands = _templates_for(topic, max_difficulty)
        if not cands:
            continue
        qs: List[GeneratedQuestion] = []
        for j in range(2):
            tmpl = rng.choice(cands)
            qseed = rng.randint(1, 10**9)
            pr, latex, ans, working = tmpl.generator(random.Random(qseed), qseed)
            qid = f"{topic}_{j+1}_{qseed}"
            qs.append(
                GeneratedQuestion(
                    qid=qid,
                    topic=topic,
                    difficulty=tmpl.difficulty,
                    prompt=pr,
                    latex=latex,
                    answer_latex=ans,
                    working=working,
                    template_id=tmpl.template_id,
                    seed=qseed,
                )
            )
        out[topic] = qs
    return out

def regenerate_question(topic: str, template_id: str, max_difficulty: int, new_seed: int) -> GeneratedQuestion:
    """
    Regenerate one question using the same template_id, but new numbers (new_seed).
    """
    tmpl = next((t for t in TEMPLATES if t.template_id == template_id and t.topic == topic and t.difficulty <= max_difficulty), None)
    if tmpl is None:
        # fallback to any template in topic
        cands = _templates_for(topic, max_difficulty)
        if not cands:
            raise ValueError("No templates available for this topic/difficulty.")
        tmpl = cands[0]
    pr, latex, ans, working = tmpl.generator(random.Random(new_seed), new_seed)
    qid = f"{topic}_{template_id}_{new_seed}"
    return GeneratedQuestion(
        qid=qid,
        topic=topic,
        difficulty=tmpl.difficulty,
        prompt=pr,
        latex=latex,
        answer_latex=ans,
        working=working,
        template_id=tmpl.template_id,
        seed=new_seed,
    )


def generate_questions_by_template(topic: str, template_id: str, max_difficulty: int, n: int, seed: int) -> List[GeneratedQuestion]:
    """Generate n fresh questions using the same template_id (same type/level)."""
    rng = random.Random(seed)
    out: List[GeneratedQuestion] = []
    for _ in range(n):
        qseed = rng.randint(1, 10**9)
        out.append(
            regenerate_question(
                topic=topic,
                template_id=template_id,
                max_difficulty=max_difficulty,
                new_seed=qseed,
            )
        )
    return out
