from __future__ import annotations

from pathlib import Path

from rentr.domain import TranslationKind, TranslationUnit
from rentr.localization import Glossary, GlossaryEntry, LocalizationAssets
from rentr.pipeline import TranslationOrigin, TranslationReport, TranslationResult
from rentr.review import ReviewReason, build_review_queue


def _result(source: str, target: str, *, unit_id: str) -> TranslationResult:
    unit = TranslationUnit(
        unit_id=unit_id,
        source_text=source,
        file_path=Path("script.rpy"),
        line_number=1,
        kind=TranslationKind.STRING,
    )
    return TranslationResult(unit, target, TranslationOrigin.PROVIDER, 1)


def test_queue_is_risk_sorted_and_explains_glossary_mismatch() -> None:
    assets = LocalizationAssets(
        glossary=Glossary("1", (GlossaryEntry("Save", "Kaydet"),))
    )
    normal = _result("Continue", "Devam Et", unit_id="normal")
    risky = _result("Save [name]", "Merhaba [name]", unit_id="risky")

    queue = build_review_queue(TranslationReport((normal, risky)), assets=assets)

    assert [item.unit_id for item in queue] == ["risky", "normal"]
    assert ReviewReason.GLOSSARY_MISMATCH in queue[0].reasons
    assert ReviewReason.CONTROL_SYNTAX in queue[0].reasons


def test_queue_can_filter_low_risk_items() -> None:
    human_unit = TranslationUnit(
        unit_id="human",
        source_text="Hello",
        file_path=Path("script.rpy"),
        line_number=1,
        kind=TranslationKind.STRING,
    )
    report = TranslationReport(
        (TranslationResult(human_unit, "Merhaba", TranslationOrigin.EXISTING, 0),)
    )

    assert build_review_queue(report, minimum_score=1) == ()


def test_repaired_translation_still_counts_as_machine_translation() -> None:
    unit = TranslationUnit(
        unit_id="u-repaired",
        source_text="Hello",
        file_path=Path("script.rpy"),
        line_number=1,
        kind=TranslationKind.STRING,
    )
    report = TranslationReport(
        (TranslationResult(unit, "Merhaba", TranslationOrigin.REPAIRED, 1),)
    )

    queue = build_review_queue(report, minimum_score=1)

    assert len(queue) == 1
    assert ReviewReason.MACHINE_TRANSLATION in queue[0].reasons
