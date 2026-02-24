from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Callable, List, Tuple


@dataclass(frozen=True)
class GeneratedQuestion:
    topic: str
    difficulty: int
    prompt: str          # e.g. "Solve:"
    latex: str           # e.g. "3x+5=20"
    answer_latex: str    # e.g. "x=5"


@dataclass(frozen=True)
class Template:
    topic: str
    difficulty: int
    generator: Callable[[random.Random], Tuple[str, str, str]]  # (prompt, latex, answer_latex)


def _linear_equation(rng: random.Random, a_min=2, a_max=9, x_min=-8, x_max=12, b_min=-20, b_max=20):
    a = rng.randint(a_min, a_max)
    x = rng.randint(x_min, x_max)
    b = rng.randint(b_min, b_max)
    c = a * x + b
    prompt = "Solve:"
    if b == 0:
        latex = rf"{a}x = {c}"
    else:
        sign = "+" if b > 0 else "-"
        latex = rf"{a}x {sign} {abs(b)} = {c}"
    answer = rf"x = {x}"
    return prompt, latex, answer


def _expand_single_bracket(rng: random.Random):
    a = rng.choice([2, 3, 4, 5, 6])
    b = rng.choice([-9, -8, -7, -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 7, 8, 9])
    prompt = "Expand and simplify:"
    op = "+" if b > 0 else "-"
    latex = rf"{a}\left(x {op} {abs(b)}\right)"
    k = a * b
    op2 = "+" if k > 0 else "-"
    answer = rf"{a}x {op2} {abs(k)}"
    return prompt, latex, answer


def _expand_double_bracket(rng: random.Random):
    a = rng.choice([1, 2, 3])
    b = rng.choice([-5, -4, -3, -2, -1, 1, 2, 3, 4, 5])
    c = rng.choice([1, 2, 3])
    d = rng.choice([-5, -4, -3, -2, -1, 1, 2, 3, 4, 5])
    prompt = "Expand and simplify:"
    opb = "+" if b > 0 else "-"
    opd = "+" if d > 0 else "-"
    latex = rf"\left({a}x {opb} {abs(b)}\right)\left({c}x {opd} {abs(d)}\right)"

    ac = a * c
    xcoef = a * d + b * c
    bd = b * d

    parts = [rf"{ac}x^2"]
    if xcoef != 0:
        parts.append(rf"{'+' if xcoef > 0 else '-'} {abs(xcoef)}x")
    if bd != 0:
        parts.append(rf"{'+' if bd > 0 else '-'} {abs(bd)}")
    answer = " ".join(parts)
    return prompt, latex, answer


def _factorise_common_factor(rng: random.Random):
    g = rng.choice([2, 3, 4, 5, 6])
    a = rng.choice([1, 2, 3, 4, 5, 6, 7, 8, 9])
    b = rng.choice([1, 2, 3, 4, 5, 6, 7, 8, 9])
    prompt = "Factorise fully:"
    latex = rf"{g*a}x + {g*b}"
    answer = rf"{g}\left({a}x + {b}\right)"
    return prompt, latex, answer


def _indices_simplify(rng: random.Random):
    base = rng.choice(["x", "a", "m"])
    p = rng.randint(1, 7)
    q = rng.randint(1, 7)
    prompt = "Simplify:"
    latex = rf"{base}^{p}\times {base}^{q}"
    answer = rf"{base}^{{{p+q}}}"
    return prompt, latex, answer


def _fraction_of_amount(rng: random.Random):
    den = rng.choice([2, 3, 4, 5, 8, 10])
    num = rng.randint(1, den - 1)
    k = rng.choice([6, 8, 9, 10, 12, 15, 16, 18, 20, 24, 25, 30, 32, 36, 40, 45, 48, 50, 60, 64, 72, 80, 90, 100])
    amount = den * k
    prompt = "Calculate:"
    latex = rf"\frac{{{num}}}{{{den}}}\times {amount}"
    answer = rf"{num*k}"
    return prompt, latex, answer


TEMPLATES: List[Template] = [
    Template("Linear equations", 1, lambda r: _linear_equation(r, a_min=2, a_max=5, x_min=-5, x_max=10, b_min=-10, b_max=10)),
    Template("Linear equations", 2, lambda r: _linear_equation(r, a_min=2, a_max=9, x_min=-8, x_max=12, b_min=-20, b_max=20)),
    Template("Expanding brackets", 1, _expand_single_bracket),
    Template("Expanding brackets", 3, _expand_double_bracket),
    Template("Factorising", 2, _factorise_common_factor),
    Template("Indices", 2, _indices_simplify),
    Template("Fractions", 2, _fraction_of_amount),
]


def available_topics() -> List[str]:
    return sorted({t.topic for t in TEMPLATES})


def generate_questions(topics: List[str], max_difficulty: int, n: int, seed: int) -> List[GeneratedQuestion]:
    rng = random.Random(seed)
    candidates = [t for t in TEMPLATES if t.topic in topics and t.difficulty <= max_difficulty]
    if not candidates:
        return []

    qs: List[GeneratedQuestion] = []
    for _ in range(n):
        tmpl = rng.choice(candidates)
        prompt, latex, ans = tmpl.generator(rng)
        qs.append(GeneratedQuestion(tmpl.topic, tmpl.difficulty, prompt, latex, ans))
    return qs
