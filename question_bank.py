from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple


@dataclass(frozen=True)
class GeneratedQuestion:
    topic: str
    difficulty: int
    prompt: str                 # e.g. "Solve:"
    latex: str                  # the question expression
    answer_latex: str           # final answer
    working_steps_latex: List[str]  # step-by-step working (each line rendered separately)


@dataclass(frozen=True)
class Template:
    id: str
    topic: str
    difficulty: int
    generator: Callable[[random.Random], Tuple[str, str, str, List[str]]]  # (prompt, latex, answer, working)


def _lin_eq(rng: random.Random, a_min=2, a_max=9, x_min=-8, x_max=12, b_min=-20, b_max=20) -> Tuple[str, str, str, List[str]]:
    """
    Generate equations of the form ax + b = c with integer solution x.
    """
    a = rng.randint(a_min, a_max)
    x = rng.randint(x_min, x_max)
    b = rng.randint(b_min, b_max)
    c = a * x + b

    prompt = r"\text{Solve:}"
    if b == 0:
        q = rf"{a}x = {c}"
        steps = [
            q,
            rf"\frac{{{a}x}}{{{a}}} = \frac{{{c}}}{{{a}}}",
            rf"x = {x}",
        ]
    else:
        sign = "+" if b > 0 else "-"
        q = rf"{a}x {sign} {abs(b)} = {c}"
        c2 = c - b
        # show 'subtract b' generically as a clean arithmetic result line
        steps = [
            q,
            rf"{a}x = {c2}",
            rf"x = \frac{{{c2}}}{{{a}}}",
            rf"x = {x}",
        ]

    ans = rf"x = {x}"
    return prompt, q, ans, steps


def _expand_single(rng: random.Random) -> Tuple[str, str, str, List[str]]:
    a = rng.choice([2, 3, 4, 5, 6])
    b = rng.choice([-9, -8, -7, -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 7, 8, 9])

    prompt = r"\text{Expand and simplify:}"
    q = rf"{a}\left(x {'+' if b > 0 else '-'} {abs(b)}\right)"
    prod = a * b
    ans = rf"{a}x {'+' if prod > 0 else '-'} {abs(prod)}"

    steps = [
        q,
        rf"= {a}x {'+' if prod > 0 else '-'} {abs(prod)}",
    ]
    return prompt, q, ans, steps


def _expand_double(rng: random.Random) -> Tuple[str, str, str, List[str]]:
    a = rng.choice([1, 2, 3])
    b = rng.choice([-5, -4, -3, -2, -1, 1, 2, 3, 4, 5])
    c = rng.choice([1, 2, 3])
    d = rng.choice([-5, -4, -3, -2, -1, 1, 2, 3, 4, 5])

    prompt = r"\text{Expand and simplify:}"
    q = rf"\left({a}x {'+' if b > 0 else '-'} {abs(b)}\right)\left({c}x {'+' if d > 0 else '-'} {abs(d)}\right)"

    ac = a * c
    ad = a * d
    bc = b * c
    bd = b * d
    xcoef = ad + bc

    # Build final simplified answer
    parts = [rf"{ac}x^2"]
    if xcoef != 0:
        parts.append(rf"{'+' if xcoef > 0 else '-'} {abs(xcoef)}x")
    if bd != 0:
        parts.append(rf"{'+' if bd > 0 else '-'} {abs(bd)}")
    ans = " ".join(parts)

    steps = [
        q,
        rf"= ({a}x)({c}x) + ({a}x)({'+' if d>0 else '-'} {abs(d)}) + ({'+' if b>0 else '-'} {abs(b)})({c}x) + ({'+' if b>0 else '-'} {abs(b)})({'+' if d>0 else '-'} {abs(d)})",
        rf"= {ac}x^2 {'+' if ad>0 else '-'} {abs(ad)}x {'+' if bc>0 else '-'} {abs(bc)}x {'+' if bd>0 else '-'} {abs(bd)}",
        rf"= {ans}",
    ]
    return prompt, q, ans, steps


def _factorise_common_factor(rng: random.Random) -> Tuple[str, str, str, List[str]]:
    g = rng.choice([2, 3, 4, 5, 6])
    a = rng.choice([1, 2, 3, 4, 5, 6, 7, 8, 9])
    b = rng.choice([1, 2, 3, 4, 5, 6, 7, 8, 9])

    prompt = r"\text{Factorise fully:}"
    q = rf"{g*a}x + {g*b}"
    ans = rf"{g}\left({a}x + {b}\right)"
    steps = [
        q,
        rf"= {g}\left({a}x + {b}\right)",
    ]
    return prompt, q, ans, steps


def _indices_simplify(rng: random.Random) -> Tuple[str, str, str, List[str]]:
    base = rng.choice(["x", "a", "m"])
    p = rng.randint(1, 7)
    q = rng.randint(1, 7)

    prompt = r"\text{Simplify:}"
    qn = rf"{base}^{p}\times {base}^{q}"
    ans = rf"{base}^{{{p+q}}}"
    steps = [
        qn,
        rf"= {base}^{{{p}+{q}}}",
        rf"= {ans}",
    ]
    return prompt, qn, ans, steps


def _fraction_of_amount(rng: random.Random) -> Tuple[str, str, str, List[str]]:
    den = rng.choice([2, 3, 4, 5, 8, 10])
    num = rng.randint(1, den - 1)
    k = rng.choice([6, 8, 9, 10, 12, 15, 16, 18, 20, 24, 25, 30, 32, 36, 40, 45, 48, 50, 60, 64, 72, 80, 90, 100])
    amount = den * k

    prompt = r"\text{Calculate:}"
    q = rf"\frac{{{num}}}{{{den}}}\times {amount}"
    ans_val = num * k
    ans = rf"{ans_val}"

    steps = [
        q,
        rf"= {num}\times ({amount}\div {den})",
        rf"= {num}\times {k}",
        rf"= {ans_val}",
    ]
    return prompt, q, ans, steps


TEMPLATES: List[Template] = [
    Template("lin_eq_easy", "Linear equations", 1, lambda r: _lin_eq(r, a_min=2, a_max=5, x_min=-5, x_max=10, b_min=-10, b_max=10)),
    Template("lin_eq_std", "Linear equations", 2, lambda r: _lin_eq(r, a_min=2, a_max=9, x_min=-8, x_max=12, b_min=-20, b_max=20)),
    Template("expand_single", "Expanding brackets", 1, _expand_single),
    Template("expand_double", "Expanding brackets", 3, _expand_double),
    Template("factorise_cf", "Factorising", 2, _factorise_common_factor),
    Template("indices_mul", "Indices", 2, _indices_simplify),
    Template("frac_of_amount", "Fractions", 2, _fraction_of_amount),
]

TEMPLATES_BY_ID: Dict[str, Template] = {t.id: t for t in TEMPLATES}


def available_topics() -> List[str]:
    return sorted({t.topic for t in TEMPLATES})


def available_templates(topics: List[str], max_difficulty: int) -> List[Template]:
    return [t for t in TEMPLATES if t.topic in topics and t.difficulty <= max_difficulty]


def generate_question_from_template(template_id: str, seed: int) -> GeneratedQuestion:
    tmpl = TEMPLATES_BY_ID[template_id]
    rng = random.Random(seed)
    prompt, latex, ans, working = tmpl.generator(rng)
    return GeneratedQuestion(
        topic=tmpl.topic,
        difficulty=tmpl.difficulty,
        prompt=prompt,
        latex=latex,
        answer_latex=ans,
        working_steps_latex=working,
    )


def generate_set_meta(topics: List[str], max_difficulty: int, n: int, set_seed: int) -> List[Dict[str, int]]:
    """
    Returns a list of dicts: {"template_id": <str>, "seed": <int>}
    This is what the Streamlit app stores in session_state.
    """
    rng = random.Random(set_seed)
    candidates = available_templates(topics, max_difficulty)
    if not candidates:
        return []

    meta: List[Dict[str, int]] = []
    for _ in range(n):
        tmpl = rng.choice(candidates)
        q_seed = rng.randint(1, 10**9)
        meta.append({"template_id": tmpl.id, "seed": q_seed})
    return meta
