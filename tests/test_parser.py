import warnings
from pathlib import Path

import pytest

from rentr.domain import TranslationKind, TranslationStatus
from rentr.parser import TemplateParseError, parse_template, parse_template_text

FIXTURE = Path(__file__).parent / "fixtures" / "first_choice_a.rpy"
TRANSLATED_FIXTURE = Path(__file__).parent / "fixtures" / "existing_translation_a.rpy"
EDGE_FIXTURE = Path(__file__).parent / "fixtures" / "parser_edge_cases.rpy"


def test_choice_a_extracts_dialogue_and_old_string_only() -> None:
    units = parse_template(FIXTURE)

    assert len(units) == 2
    assert [unit.source_text for unit in units] == [
        "Hello, [player_name]!",
        "Start Game",
    ]
    assert [unit.kind for unit in units] == [
        TranslationKind.DIALOGUE,
        TranslationKind.STRING,
    ]


def test_dialogue_keeps_translation_metadata() -> None:
    dialogue, string = parse_template(FIXTURE)

    assert dialogue.unit_id == "start_9e6e3c3d"
    assert dialogue.speaker == "eileen"
    assert dialogue.label == "start"
    assert dialogue.line_number == 4
    assert dialogue.file_path == FIXTURE
    assert string.speaker is None
    assert string.label is None
    assert string.line_number == 9


def test_duplicate_translation_identifier_keeps_scene_label() -> None:
    unit = parse_template_text(
        'translate turkish v8stalkfaprequest_60f1ef95_1:\n'
        '    # guy "Context-sensitive line."\n'
        '    guy ""\n',
        file_path=Path("duplicate-identifier.rpy"),
    )[0]

    assert unit.unit_id == "v8stalkfaprequest_60f1ef95_1"
    assert unit.label == "v8stalkfaprequest"


def test_empty_translation_targets_are_not_units() -> None:
    units = parse_template(FIXTURE)

    assert all(unit.source_text for unit in units)
    assert "" not in {unit.source_text for unit in units}
    assert all(unit.translated_text is None for unit in units)
    assert all(unit.status is TranslationStatus.PENDING for unit in units)



def test_source_equal_generated_targets_are_pending_placeholders() -> None:
    dialogue, string = parse_template_text(
        'translate turkish scene_a1b2c3d4:\n'
        '    # eileen "You look... different"\n'
        '    eileen "You look... different"\n'
        '\n'
        'translate turkish strings:\n'
        '    old "Ready?"\n'
        '    new "Ready?"\n',
        file_path=Path("generated-template.rpy"),
    )

    assert dialogue.translated_text is None
    assert dialogue.translated_segments == ()
    assert dialogue.status is TranslationStatus.PENDING
    assert string.translated_text is None
    assert string.status is TranslationStatus.PENDING

def test_existing_dialogue_and_string_translations_are_preserved() -> None:
    dialogue, string = parse_template(TRANSLATED_FIXTURE)

    assert dialogue.source_text == "Welcome back."
    assert dialogue.translated_text == "Tekrar hoş geldin."
    assert dialogue.status is TranslationStatus.TRANSLATED
    assert string.source_text == "Preferences"
    assert string.translated_text == "Tercihler"
    assert string.status is TranslationStatus.TRANSLATED


def test_translation_does_not_change_source_identity() -> None:
    first = parse_template_text(
        'translate turkish start_a1b2c3d4:\n    # e "Hello"\n    e "Merhaba"\n',
        file_path=Path("first.rpy"),
    )[0]
    second = parse_template_text(
        'translate turkish start_a1b2c3d4:\n    # e "Hello"\n    e "Selam"\n',
        file_path=Path("second.rpy"),
    )[0]

    assert first.source_hash == second.source_hash


def test_mismatched_dialogue_speaker_is_rejected() -> None:
    with pytest.raises(TemplateParseError, match="konuşmacı uyuşmuyor"):
        parse_template_text(
            'translate turkish start_a1b2c3d4:\n    # eileen "Hello"\n    lucy "Merhaba"\n',
            file_path=Path("broken-speaker.rpy"),
        )


def test_repeated_ui_strings_receive_unique_ids() -> None:
    units = parse_template_text(
        'translate turkish strings:\n    old "Save"\n    new ""\n    old "Save"\n    new ""\n',
        file_path=Path("strings.rpy"),
    )

    assert len(units) == 2
    assert units[0].unit_id != units[1].unit_id


def test_malformed_old_string_fails_with_line_number() -> None:
    with pytest.raises(TemplateParseError, match="Satır 2"):
        parse_template_text(
            'translate turkish strings:\n    old "Unclosed\n',
            file_path=Path("broken.rpy"),
        )


def test_narrator_and_backtick_sources_are_explicitly_supported() -> None:
    narrator, _, _, backtick, _ = parse_template(EDGE_FIXTURE)

    assert narrator.source_text == "The hall was silent."
    assert narrator.speaker is None
    assert backtick.source_text == "A narrator can use backticks."
    assert backtick.speaker is None


def test_renpy_escapes_are_decoded_without_python_syntax_warnings() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _, escaped, _, _, raw_string = parse_template(EDGE_FIXTURE)

    assert escaped.source_text == ('She said, "Wait."\nFolder: C:\\Games\\RenTR; protected \\%.')
    assert raw_string.source_text == r"Literal \n stays protected as \%."
    assert not [item for item in caught if issubclass(item.category, SyntaxWarning)]


def test_split_existing_translation_preserves_all_target_segments() -> None:
    _, _, split, _, _ = parse_template(EDGE_FIXTURE)

    assert split.translated_segments == ("Bu yanıtın", "iki bölümü var.")
    assert split.translated_text == "Bu yanıtın\niki bölümü var."
    assert split.status is TranslationStatus.TRANSLATED


def test_voice_statement_is_not_misclassified_as_dialogue() -> None:
    units = parse_template_text(
        "translate turkish arrival_a1b2c3d4:\n"
        '    # voice "arrival.ogg"\n'
        '    # eileen "We are here."\n'
        '    voice "arrival-tr.ogg"\n'
        '    eileen ""\n',
        file_path=Path("voice.rpy"),
    )

    assert len(units) == 1
    assert units[0].source_text == "We are here."


def test_later_split_target_with_mismatched_speaker_is_rejected() -> None:
    with pytest.raises(TemplateParseError, match="konuşmacı uyuşmuyor"):
        parse_template_text(
            "translate turkish split_a1b2c3d4:\n"
            '    # eileen "A long answer."\n'
            '    eileen "Uzun"\n'
            '    lucy "bir yanıt."\n',
            file_path=Path("broken-split.rpy"),
        )
