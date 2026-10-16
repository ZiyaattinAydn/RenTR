from pathlib import Path

import pytest

from rentr.domain import (
    TranslationKind,
    TranslationStatus,
    TranslationUnit,
    build_source_hash,
)
from rentr.parser import parse_template, parse_template_text
from rentr.renderer import TemplateRenderError, render_template

FIXTURES = Path(__file__).parent / "fixtures"
EDGE_FIXTURE = FIXTURES / "parser_edge_cases.rpy"
GOLDEN_FIXTURE = FIXTURES / "parser_edge_cases.rendered.rpy"
SUPPORTED_FIXTURES = (
    FIXTURES / "first_choice_a.rpy",
    FIXTURES / "existing_translation_a.rpy",
    EDGE_FIXTURE,
)


def _semantic_record(unit: TranslationUnit) -> tuple[object, ...]:
    return (
        unit.unit_id,
        unit.kind,
        unit.source_text,
        unit.speaker,
        unit.label,
        unit.translated_text,
        unit.translated_segments,
        unit.status,
        unit.source_hash,
    )


def test_edge_fixture_renders_exact_golden_template() -> None:
    rendered = render_template(parse_template(EDGE_FIXTURE))

    assert rendered == GOLDEN_FIXTURE.read_text(encoding="utf-8")


@pytest.mark.parametrize("fixture", SUPPORTED_FIXTURES, ids=lambda path: path.stem)
def test_parse_render_parse_preserves_supported_semantics(fixture: Path) -> None:
    original = parse_template(fixture)
    rendered = render_template(original)
    reparsed = parse_template_text(rendered, file_path=fixture)

    assert [_semantic_record(unit) for unit in reparsed] == [
        _semantic_record(unit) for unit in original
    ]


def test_same_units_always_render_identical_bytes() -> None:
    units = parse_template(EDGE_FIXTURE)

    assert render_template(units).encode() == render_template(units).encode()


def test_empty_inventory_is_rejected() -> None:
    with pytest.raises(TemplateRenderError, match="boş envanter"):
        render_template(())


def test_duplicate_dialogue_block_id_is_rejected() -> None:
    unit = TranslationUnit(
        unit_id="start_a1b2c3d4",
        source_text="Hello.",
        file_path=Path("script.rpy"),
        line_number=1,
        kind=TranslationKind.DIALOGUE,
        label="start",
    )

    with pytest.raises(TemplateRenderError, match="yinelenen diyalog kimliği"):
        render_template((unit, unit))


def test_multiple_segments_are_rejected_for_string_units() -> None:
    unit = TranslationUnit(
        unit_id=f"strings:{build_source_hash('Save')[:16]}:1",
        source_text="Save",
        file_path=Path("script.rpy"),
        line_number=1,
        kind=TranslationKind.STRING,
        translated_segments=("Kaydet", "Şimdi"),
        status=TranslationStatus.TRANSLATED,
    )

    with pytest.raises(TemplateRenderError, match="string hedefi tek segment"):
        render_template((unit,))


def test_noncanonical_string_identity_is_rejected() -> None:
    unit = TranslationUnit(
        unit_id="strings:wrong:1",
        source_text="Save",
        file_path=Path("script.rpy"),
        line_number=1,
        kind=TranslationKind.STRING,
    )

    with pytest.raises(TemplateRenderError, match="string kimliği"):
        render_template((unit,))


def test_empty_translated_segment_is_rejected() -> None:
    unit = TranslationUnit(
        unit_id="start_a1b2c3d4",
        source_text="Hello.",
        file_path=Path("script.rpy"),
        line_number=1,
        kind=TranslationKind.DIALOGUE,
        label="start",
        translated_segments=("",),
        status=TranslationStatus.TRANSLATED,
    )

    with pytest.raises(TemplateRenderError, match="Boş hedef segmenti"):
        render_template((unit,))


@pytest.mark.parametrize("language", ["Turkish", "türkçe", "turkish;rm"])
def test_invalid_language_name_is_rejected(language: str) -> None:
    units = parse_template(EDGE_FIXTURE)

    with pytest.raises(TemplateRenderError, match="Dil adı"):
        render_template(units, language=language)
