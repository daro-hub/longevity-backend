"""Unit conversions and the single rounding policy used everywhere else in
the domain package. Keeping rounding in one place matters: macro_targets
rounds grams to integers and then recomputes kcal from those rounded grams
(see energy.py / macros.py docstrings) — if two different rounding policies
existed, the validator in the LLM plan pipeline would chase a target that no
integer-gram plan could ever hit exactly.
"""

from __future__ import annotations


def round_grams(value: float) -> int:
    """Round a gram quantity to the nearest whole gram. Food is not
    typically dosed to fractional grams, and downstream (the LLM plan
    validator) works entirely in integer grams.
    """
    return round(value)


def round_kcal(value: float) -> int:
    return round(value)


def round_ml(value: float) -> int:
    return round(value)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
