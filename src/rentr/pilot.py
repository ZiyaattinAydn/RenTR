"""Deterministic representative pilot selection for real-game acceptance tests."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from rentr.domain import TranslationKind, TranslationUnit
from rentr.protection import ProtectionError, protect_text
from rentr.triage import requires_provider_translation

_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_CONTEXT_SENSITIVE = re.compile(
    r"\b(?:fuck|fucking|fucked|shit|damn|bitch|asshole|slut|horny|sex|sexy|hot|"
    r"cock|dick|pussy|cum|cumming|blowjob|suck|naked|orgasm|jerk\s+off)\b",
    re.IGNORECASE,
)


class PilotCategory(StrEnum):
    """Why a unit belongs in the representative acceptance-test sample."""

    CONTEXT_SENSITIVE = "context_sensitive"
    AMBIGUOUS_SHORT = "ambiguous_short"
    PROTECTED_SYNTAX = "protected_syntax"
    UI_STRING = "ui_string"
    GENERAL_DIALOGUE = "general_dialogue"


@dataclass(frozen=True, slots=True)
class PilotSelection:
    """One selected provider unit with its original inventory position."""

    index: int
    unit: TranslationUnit
    category: PilotCategory


def _evenly_spaced(indices: list[int], count: int) -> list[int]:
    if count <= 0 or not indices:
        return []
    if len(indices) <= count:
        return indices.copy()
    step = len(indices) / count
    return [indices[min(int((slot + 0.5) * step), len(indices) - 1)] for slot in range(count)]


def _has_protected_syntax(text: str) -> bool:
    try:
        return bool(protect_text(text).tokens)
    except ProtectionError:
        return False


def _is_ambiguous_short(text: str, *, occurrence_count: int) -> bool:
    words = _WORD.findall(text)
    return occurrence_count > 1 and 1 <= len(words) <= 4 and len(text.strip()) <= 32


def select_pilot_units(
    units: Iterable[TranslationUnit],
    *,
    limit: int = 100,
) -> tuple[PilotSelection, ...]:
    """Select a deterministic, category-balanced provider-only pilot sample.

    Selection is spread across the complete inventory instead of taking the first N
    lines, so large branching games exercise late chapters as well as early ones.
    Exact duplicate dialogue is deliberately *not* collapsed because short phrases
    can require different Turkish translations in different contexts.
    """
    if limit < 1:
        raise ValueError("pilot limiti 1 veya daha büyük olmalı")

    inventory = tuple(units)
    provider_indices = [
        index
        for index, unit in enumerate(inventory)
        if unit.translated_text is None and requires_provider_translation(unit.source_text)
    ]
    if not provider_indices:
        return ()

    source_counts = Counter(inventory[index].source_text for index in provider_indices)
    candidates: dict[PilotCategory, list[int]] = {
        category: [] for category in PilotCategory
    }
    for index in provider_indices:
        unit = inventory[index]
        text = unit.source_text
        if _CONTEXT_SENSITIVE.search(text):
            candidates[PilotCategory.CONTEXT_SENSITIVE].append(index)
        if _is_ambiguous_short(text, occurrence_count=source_counts[text]):
            candidates[PilotCategory.AMBIGUOUS_SHORT].append(index)
        if _has_protected_syntax(text):
            candidates[PilotCategory.PROTECTED_SYNTAX].append(index)
        if unit.kind is TranslationKind.STRING:
            candidates[PilotCategory.UI_STRING].append(index)
        if unit.kind is TranslationKind.DIALOGUE:
            candidates[PilotCategory.GENERAL_DIALOGUE].append(index)

    # Percentages are intentionally quality-heavy: ORS-like games need context,
    # ambiguity and token safety exercised before throughput is considered.
    quotas = {
        PilotCategory.CONTEXT_SENSITIVE: round(limit * 0.20),
        PilotCategory.AMBIGUOUS_SHORT: round(limit * 0.20),
        PilotCategory.PROTECTED_SYNTAX: round(limit * 0.20),
        PilotCategory.UI_STRING: round(limit * 0.15),
    }
    quotas[PilotCategory.GENERAL_DIALOGUE] = max(0, limit - sum(quotas.values()))

    selected: dict[int, PilotCategory] = {}
    category_order = (
        PilotCategory.CONTEXT_SENSITIVE,
        PilotCategory.AMBIGUOUS_SHORT,
        PilotCategory.PROTECTED_SYNTAX,
        PilotCategory.UI_STRING,
        PilotCategory.GENERAL_DIALOGUE,
    )
    for category in category_order:
        available = [index for index in candidates[category] if index not in selected]
        for index in _evenly_spaced(available, quotas[category]):
            selected[index] = category

    if len(selected) < limit:
        remaining = [index for index in provider_indices if index not in selected]
        for index in _evenly_spaced(remaining, limit - len(selected)):
            selected[index] = PilotCategory.GENERAL_DIALOGUE

    return tuple(
        PilotSelection(index=index, unit=inventory[index], category=selected[index])
        for index in sorted(selected)[:limit]
    )
