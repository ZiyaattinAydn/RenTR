from __future__ import annotations

from pathlib import Path

from rentr.domain import TranslationKind, TranslationUnit
from rentr.pilot import PilotCategory, select_pilot_units


def _unit(
    index: int,
    text: str,
    *,
    kind: TranslationKind = TranslationKind.DIALOGUE,
    translated_text: str | None = None,
) -> TranslationUnit:
    return TranslationUnit(
        unit_id=f"scene_{index:08x}",
        source_text=text,
        file_path=Path("game/tl/turkish/script.rpy"),
        line_number=index + 1,
        kind=kind,
        speaker="lena" if kind is TranslationKind.DIALOGUE else None,
        label="scene" if kind is TranslationKind.DIALOGUE else None,
        translated_text=translated_text,
    )


def test_pilot_is_provider_only_bounded_and_category_balanced() -> None:
    units = [
        _unit(0, "{image=icon_pay.webp}"),
        _unit(1, "Yeah..."),
        _unit(2, "Yeah..."),
        _unit(3, "Fuck me."),
        _unit(4, "Hello [name]."),
        _unit(5, "Preferences", kind=TranslationKind.STRING),
    ]
    units.extend(_unit(index, f"General dialogue number {index}") for index in range(6, 40))

    selections = select_pilot_units(units, limit=10)

    assert len(selections) == 10
    assert all(selection.unit.source_text != "{image=icon_pay.webp}" for selection in selections)
    categories = {selection.category for selection in selections}
    assert PilotCategory.CONTEXT_SENSITIVE in categories
    assert PilotCategory.AMBIGUOUS_SHORT in categories
    assert PilotCategory.PROTECTED_SYNTAX in categories
    assert PilotCategory.UI_STRING in categories


def test_pilot_selection_is_deterministic() -> None:
    units = tuple(_unit(index, f"Line number {index}") for index in range(60))

    first = select_pilot_units(units, limit=12)
    second = select_pilot_units(units, limit=12)

    assert [item.index for item in first] == [item.index for item in second]


def test_pilot_excludes_existing_translations_even_when_linguistic() -> None:
    units = (
        _unit(0, "Already translated.", translated_text="Zaten çevrildi."),
        _unit(1, "Fresh line."),
    )

    selections = select_pilot_units(units, limit=2)

    assert [selection.unit.source_text for selection in selections] == ["Fresh line."]
