from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


@dataclass(frozen=True)
class GuardrailInput:
    dialogue: str
    pedagogical_move: str
    proposed_hint_level: int
    allowed_help_level: int
    canonical_answer: str
    banned_strings: list[str] = field(default_factory=list)
    concept_mastered: bool = False
    teacher_check: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GuardrailResult:
    dialogue: str
    pedagogical_move: str
    proposed_hint_level: int
    guardrail_fires: tuple[str, ...]


def apply_guardrails(payload: GuardrailInput) -> GuardrailResult:
    fires: list[str] = []
    dialogue = payload.dialogue
    pedagogical_move = payload.pedagogical_move
    hint_level = payload.proposed_hint_level

    if hint_level > payload.allowed_help_level:
        hint_level = payload.allowed_help_level
        fires.append("hint_ceiling")

    if payload.teacher_check:
        teacher_check_fire = _teacher_check_fire(payload.teacher_check, pedagogical_move)
        if teacher_check_fire:
            dialogue = "Let's stay with the authored hint for this turn."
            pedagogical_move = "reflect"
            hint_level = 0
            fires.append(teacher_check_fire)

    false_mastery = not payload.concept_mastered and _claims_mastery(dialogue)

    if _contains_answer_leak(dialogue, payload.canonical_answer, payload.banned_strings):
        dialogue = "Let's keep working from the hint rather than the final answer."
        fires.append("answer_leak")

    if _contains_prompt_injection_echo(dialogue):
        dialogue = "Let's stay with the current problem and the allowed hint."
        fires.append("prompt_injection_echo")

    if false_mastery:
        dialogue = "You completed this step; mastery still depends on the remaining checks."
        pedagogical_move = "reflect"
        fires.append("false_mastery_claim")

    return GuardrailResult(
        dialogue=dialogue,
        pedagogical_move=pedagogical_move,
        proposed_hint_level=hint_level,
        guardrail_fires=tuple(fires),
    )


def _contains_answer_leak(dialogue: str, canonical_answer: str, banned_strings: list[str]) -> bool:
    lowered = dialogue.lower()
    values = [canonical_answer, *banned_strings]
    for value in values:
        if value and str(value).lower() in lowered:
            return True
    return False


def _contains_prompt_injection_echo(dialogue: str) -> bool:
    lowered = dialogue.lower()
    return "ignore prior rules" in lowered or "raise my xp" in lowered or "mark me mastered" in lowered


def _claims_mastery(dialogue: str) -> bool:
    if re.search(r"\b(cannot|can't|do not|don't|won't|will not)\b.{0,40}\b(mastered|mastery)\b", dialogue, re.I):
        return False
    return re.search(
        r"\b(you have mastered|you've mastered|you mastered|mastered this skill|achieved mastery|mark me mastered)\b",
        dialogue,
        re.I,
    ) is not None


def _teacher_check_fire(teacher_check: dict[str, Any], pedagogical_move: str) -> str | None:
    if teacher_check.get("leak_risk") != "none":
        return "teacher_check_leak_risk"
    if teacher_check.get("uses_only_authored_scaffold") is not True:
        return "teacher_check_unauthored_scaffold"
    chosen_move = teacher_check.get("chosen_pedagogical_move")
    if chosen_move and chosen_move != pedagogical_move:
        return "teacher_check_move_mismatch"
    return None
