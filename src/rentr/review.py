"""Deterministic, explainable risk scoring for human translation review."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rentr.domain import TranslationKind, TranslationUnit
from rentr.localization import LocalizationAssets
from rentr.pipeline import TranslationOrigin, TranslationReport


class ReviewReason(StrEnum):
    MACHINE_TRANSLATION = "machine_translation"
    CONTROL_SYNTAX = "control_syntax"
    EXTREME_LENGTH_RATIO = "extreme_length_ratio"
    GLOSSARY_MISMATCH = "glossary_mismatch"
    UNKNOWN_CHARACTER = "unknown_character"
    LONG_TEXT = "long_text"


@dataclass(frozen=True, slots=True)
class ReviewItem:
    unit_id: str
    source_text: str
    translated_text: str
    score: int
    reasons: tuple[ReviewReason, ...]
    file_path: str
    line_number: int


def _score_unit(
    unit: TranslationUnit,
    translated_text: str,
    *,
    origin: TranslationOrigin,
    assets: LocalizationAssets,
) -> ReviewItem:
    reasons: list[ReviewReason] = []
    score = 0
    if origin in {TranslationOrigin.PROVIDER, TranslationOrigin.REPAIRED}:
        score += 20
        reasons.append(ReviewReason.MACHINE_TRANSLATION)
    if any(character in unit.source_text for character in "{[%\\"):
        score += 20
        reasons.append(ReviewReason.CONTROL_SYNTAX)
    ratio = len(translated_text) / max(1, len(unit.source_text))
    if ratio < 0.45 or ratio > 2.4:
        score += 25
        reasons.append(ReviewReason.EXTREME_LENGTH_RATIO)
    if len(unit.source_text) > 180:
        score += 15
        reasons.append(ReviewReason.LONG_TEXT)
    if unit.speaker is not None and assets.character_for(unit.speaker) is None:
        score += 10
        reasons.append(ReviewReason.UNKNOWN_CHARACTER)
    if assets.glossary is not None:
        matching = assets.glossary.matching(unit.source_text)
        missing = [
            entry
            for entry in matching
            if entry.target.casefold() not in translated_text.casefold()
        ]
        if missing:
            score += 30
            reasons.append(ReviewReason.GLOSSARY_MISMATCH)
    if unit.kind is TranslationKind.STRING:
        score = min(score, 90)
    return ReviewItem(
        unit_id=unit.unit_id,
        source_text=unit.source_text,
        translated_text=translated_text,
        score=min(score, 100),
        reasons=tuple(reasons),
        file_path=str(unit.file_path),
        line_number=unit.line_number,
    )


def build_review_queue(
    report: TranslationReport,
    *,
    assets: LocalizationAssets | None = None,
    minimum_score: int = 1,
) -> tuple[ReviewItem, ...]:
    """Build a stable highest-risk-first queue from successful translations."""
    if not 0 <= minimum_score <= 100:
        raise ValueError("minimum_score 0 ile 100 arasında olmalı")
    localization = assets or LocalizationAssets()
    items = (
        _score_unit(
            result.unit,
            result.translated_text,
            origin=result.origin,
            assets=localization,
        )
        for result in report.results
        if result.succeeded and result.translated_text is not None
    )
    return tuple(
        sorted(
            (item for item in items if item.score >= minimum_score),
            key=lambda item: (-item.score, item.file_path, item.line_number, item.unit_id),
        )
    )
