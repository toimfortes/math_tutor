from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata


UNICODE_FRACTIONS = {
    "¼": "1/4",
    "½": "1/2",
    "¾": "3/4",
    "⅐": "1/7",
    "⅑": "1/9",
    "⅒": "1/10",
    "⅓": "1/3",
    "⅔": "2/3",
    "⅕": "1/5",
    "⅖": "2/5",
    "⅗": "3/5",
    "⅘": "4/5",
    "⅙": "1/6",
    "⅚": "5/6",
    "⅛": "1/8",
    "⅜": "3/8",
    "⅝": "5/8",
    "⅞": "7/8",
}


@dataclass(frozen=True)
class NormalizedAnswer:
    raw: str
    normalized: str
    warnings: tuple[str, ...] = field(default_factory=tuple)


def normalize_answer(raw: str, *, answer_type: str) -> NormalizedAnswer:
    warnings: list[str] = []
    text = unicodedata.normalize("NFKC", str(raw)).strip()
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = text.replace("⁄", "/")

    for char, replacement in UNICODE_FRACTIONS.items():
        if char in text:
            text = text.replace(char, replacement)
            warnings.append("unicode_fraction")

    text = re.sub(r"\s+", " ", text)
    lower = text.lower().strip()

    for prefix in ("the answer is", "answer is", "i think", "it's", "it is"):
        if lower.startswith(prefix):
            text = text[len(prefix) :].strip(" :,.")
            lower = text.lower()
            warnings.append("prose_wrapper_stripped")
            break

    if answer_type == "expression":
        match = re.match(r"^[a-zA-Z]\s*=\s*(.+)$", text)
        if match:
            text = match.group(1).strip()
            warnings.append("equation_prefix_stripped")

    if answer_type in {"numeric", "expression"}:
        text = _strip_trailing_units(text)

    if answer_type == "ordered_pair":
        text = _normalize_ordered_pair(text)

    return NormalizedAnswer(raw=str(raw), normalized=text.strip(), warnings=tuple(warnings))


def _strip_trailing_units(text: str) -> str:
    match = re.match(r"^(.+?)(?:\s+(?:litres?|liters?|metres?|meters?|km|m|s|seconds?|crates?|supplies?|units?))\.?$", text, re.I)
    if match:
        return match.group(1).strip()
    return text


def _normalize_ordered_pair(text: str) -> str:
    match = re.match(r"^\(?\s*([^,]+?)\s*,\s*([^)]+?)\s*\)?$", text)
    if not match:
        return text.strip()
    return f"({match.group(1).strip()}, {match.group(2).strip()})"
