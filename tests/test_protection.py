from __future__ import annotations

import pytest

from rentr.protection import (
    ProtectionError,
    ProtectionKind,
    protect_text,
    restore_text,
)


def test_protects_renpy_tags_interpolation_formats_and_escapes() -> None:
    source = "{color=#fff}Hello, [player_name]!{/color} HP: %(hp)03d / %s\\nNext"

    protected = protect_text(source)

    assert protected.protected_text == (
        "__RENTR_0000__Hello, __RENTR_0001__!__RENTR_0002__ "
        "HP: __RENTR_0003__ / __RENTR_0004____RENTR_0005__Next"
    )
    assert tuple(token.kind for token in protected.tokens) == (
        ProtectionKind.TEXT_TAG,
        ProtectionKind.INTERPOLATION,
        ProtectionKind.TEXT_TAG,
        ProtectionKind.PERCENT_FORMAT,
        ProtectionKind.PERCENT_FORMAT,
        ProtectionKind.ESCAPE,
    )
    assert restore_text(protected.protected_text, protected) == source


def test_restores_tokens_inside_translated_text() -> None:
    protected = protect_text("Hello, [name]! {i}Ready?{/i}")
    translated = "Merhaba, __RENTR_0000__! __RENTR_0001__Hazır mısın?__RENTR_0002__"

    assert restore_text(translated, protected) == "Merhaba, [name]! {i}Hazır mısın?{/i}"


@pytest.mark.parametrize(
    "translated",
    [
        "Merhaba!",
        "__RENTR_0001__ __RENTR_0000__",
        "__RENTR_0000__ __RENTR_0000__ __RENTR_0001__",
        "__RENTR_9999__ __RENTR_0001__",
    ],
)
def test_rejects_missing_reordered_duplicate_or_changed_tokens(translated: str) -> None:
    protected = protect_text("[name] has %s points")

    with pytest.raises(ProtectionError):
        restore_text(translated, protected)


@pytest.mark.parametrize("source", ["Hello [name", "{color=#fff text", "[]", "{}"])
def test_rejects_malformed_control_syntax(source: str) -> None:
    with pytest.raises(ProtectionError):
        protect_text(source)


def test_preserves_literal_double_openers() -> None:
    protected = protect_text("Cost: 100%%, literal [[ and {{")

    assert [token.original for token in protected.tokens] == ["%%"]
    assert restore_text(protected.protected_text, protected) == "Cost: 100%%, literal [[ and {{"


def test_protects_decoded_line_breaks_and_tabs() -> None:
    protected = protect_text("First\nSecond\tValue")

    assert [token.original for token in protected.tokens] == ["\n", "\t"]
    assert restore_text(protected.protected_text, protected) == "First\nSecond\tValue"


def test_rejects_moving_boundary_control_token() -> None:
    protected = protect_text("{image=icon_broken.webp}I can't")

    with pytest.raises(ProtectionError, match="başlangıçtaki"):
        restore_text("Yapamam __RENTR_0000__", protected)


def test_rejects_inserting_text_between_source_adjacent_controls() -> None:
    protected = protect_text("I had to-{w=0.5}{nw}")

    with pytest.raises(ProtectionError, match="arasına metin"):
        restore_text("Yapmalıydım-__RENTR_0000__gerekti__RENTR_0001__", protected)


def test_allows_whitespace_between_source_adjacent_controls() -> None:
    protected = protect_text("I had to-{w=0.5} {nw}")

    assert restore_text(
        "Yapmalıydım-__RENTR_0000__  __RENTR_0001__",
        protected,
    ) == "Yapmalıydım-{w=0.5}  {nw}"


def test_rejects_detaching_inline_wait_token_from_stutter_fragment() -> None:
    protected = protect_text("No, d--{w=0.5}don't be ridiculous.")

    with pytest.raises(ProtectionError, match="satır içindeki"):
        restore_text("Hayır, __RENTR_0000__saçmalama.", protected)


def test_allows_inline_wait_token_when_translation_keeps_inline_attachment() -> None:
    protected = protect_text("Y-{w=0.3}yes...")

    assert restore_text("E-__RENTR_0000__evet...", protected) == "E-{w=0.3}evet..."


def test_boundary_salvage_restores_missing_prefix_image() -> None:
    from rentr.protection import restore_text_with_boundary_salvage

    protected = protect_text("{image=icon_friend.webp}What about me?")

    assert restore_text_with_boundary_salvage("Peki ya ben?", protected) == (
        "{image=icon_friend.webp}Peki ya ben?"
    )


def test_boundary_salvage_restores_missing_suffix_emoji() -> None:
    from rentr.protection import restore_text_with_boundary_salvage

    protected = protect_text("Good night, Louise {image=emoji_smile.webp}")

    assert restore_text_with_boundary_salvage("İyi geceler, Louise.", protected) == (
        "İyi geceler, Louise. {image=emoji_smile.webp}"
    )


def test_boundary_salvage_restores_whole_line_style_wrapper() -> None:
    from rentr.protection import restore_text_with_boundary_salvage

    protected = protect_text("{i}Hello there.{/i}")

    assert restore_text_with_boundary_salvage("Selam.", protected) == "{i}Selam.{/i}"


def test_boundary_salvage_does_not_guess_missing_internal_wait() -> None:
    from rentr.protection import restore_text_with_boundary_salvage

    protected = protect_text("No, d--{w=0.5}don't be ridiculous.")

    with pytest.raises(ProtectionError):
        restore_text_with_boundary_salvage("Hayır, saçmalama.", protected)


def test_boundary_salvage_does_not_guess_partial_inline_style_pair() -> None:
    from rentr.protection import restore_text_with_boundary_salvage

    protected = protect_text("Maybe we should have {i}the talk{/i} tonight.")

    with pytest.raises(ProtectionError):
        restore_text_with_boundary_salvage("Belki bu gece konuşmalıyız.", protected)
