from pathlib import Path

import pytest

from rentr.domain import TranslationKind, TranslationStatus, TranslationUnit, build_source_hash


def test_translation_unit_starts_pending_and_builds_hash() -> None:
    unit = TranslationUnit(
        unit_id="start_01",
        source_text="Hello, [player_name]!",
        file_path=Path("game/tl/turkish/script.rpy"),
        line_number=12,
        kind=TranslationKind.DIALOGUE,
        speaker="eileen",
        label="start",
    )

    assert unit.status is TranslationStatus.PENDING
    assert unit.translated_text is None
    assert unit.translated_segments == ()
    assert len(unit.source_hash) == 64
    assert unit.source_hash == build_source_hash(
        "Hello, [player_name]!",
        speaker="eileen",
        label="start",
    )


def test_hash_changes_when_context_changes() -> None:
    first = build_source_hash("Fine.", speaker="alice", label="chapter_one")
    second = build_source_hash("Fine.", speaker="bob", label="chapter_one")

    assert first != second


def test_split_translation_segments_build_combined_review_text() -> None:
    unit = TranslationUnit(
        unit_id="start_02",
        source_text="A long answer.",
        file_path=Path("script.rpy"),
        line_number=4,
        kind=TranslationKind.DIALOGUE,
        translated_segments=("Uzun", "bir yanıt."),
        status=TranslationStatus.TRANSLATED,
    )

    assert unit.translated_text == "Uzun\nbir yanıt."


def test_inconsistent_combined_text_and_segments_are_rejected() -> None:
    with pytest.raises(ValueError, match="translated_text ve translated_segments"):
        TranslationUnit(
            unit_id="start_03",
            source_text="Hello.",
            file_path=Path("script.rpy"),
            line_number=5,
            kind=TranslationKind.DIALOGUE,
            translated_text="Merhaba.",
            translated_segments=("Selam.",),
            status=TranslationStatus.TRANSLATED,
        )


@pytest.mark.parametrize("unit_id", ["", " ", "\t"])
def test_translation_unit_rejects_blank_id(unit_id: str) -> None:
    with pytest.raises(ValueError, match="unit_id boş olamaz"):
        TranslationUnit(
            unit_id=unit_id,
            source_text="Hello",
            file_path=Path("script.rpy"),
            line_number=1,
            kind=TranslationKind.DIALOGUE,
        )


@pytest.mark.parametrize("line_number", [0, -1, -100])
def test_translation_unit_rejects_invalid_line_number(line_number: int) -> None:
    with pytest.raises(ValueError, match="line_number 1 veya daha büyük olmalı"):
        TranslationUnit(
            unit_id="start_01",
            source_text="Hello",
            file_path=Path("script.rpy"),
            line_number=line_number,
            kind=TranslationKind.DIALOGUE,
        )
