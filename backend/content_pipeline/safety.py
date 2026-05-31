"""Deterministic safety checks for authored/gold content."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable


UNSAFE_GOLD_TERMS = [
    "wwii",
    "war",
    "warfare",
    "weapon",
    "battle",
    "ammunition",
    "rounds",
    "shell",
    "armoured",
    "armored",
    "gun",
    "targeting",
    "combat",
    "front line",
    "recon",
    "march",
    "projectile",
    "downrange",
    "spotter",
    "flare",
    "launch",
    "launches",
    "launcher",
    "thrown",
    "ballistic",
    "missile",
    "munition",
    "high-speed",
]


def find_unsafe_terms(text: str, terms: Iterable[str] = UNSAFE_GOLD_TERMS) -> list[str]:
    lower = text.lower()
    return [
        term
        for term in terms
        if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", lower)
    ]


def check_gold_file(path: Path) -> list[str]:
    data = json.loads(path.read_text())
    return find_unsafe_terms(json.dumps(data, ensure_ascii=False))


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    gold = root / "backend/content_pipeline/gold/linear_functions.json"
    found = check_gold_file(gold)
    if found:
        raise SystemExit(f"Unsafe terms remain in gold set: {', '.join(found)}")
    print("gold theme safety scan passed")


if __name__ == "__main__":
    main()
