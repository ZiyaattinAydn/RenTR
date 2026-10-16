from __future__ import annotations

import pytest

from rentr.quality import QualityError, validate_translation_output


def test_accepts_natural_turkish_and_latin_proper_names() -> None:
    validate_translation_output(
        "I went to her Peoplegram profile.",
        "Onun Peoplegram profiline gittim.",
    )


def test_rejects_new_unexpected_script_characters() -> None:
    with pytest.raises(QualityError, match="beklenmeyen yazı sistemi"):
        validate_translation_output(
            "Damn! When did you get so good at this?",
            "TanıANGER! 你的嘴巴什么时候变得这么棒？",
        )


def test_allows_non_latin_characters_that_are_already_in_source() -> None:
    validate_translation_output("Achievement: 東京", "Başarım: 東京")


def test_rejects_context_metadata_leakage_for_any_provider() -> None:
    with pytest.raises(QualityError, match="metadatasını"):
        validate_translation_output("Hello", "Scene label: start\nText: Merhaba")


def test_rejects_suspicious_context_sized_expansion() -> None:
    with pytest.raises(QualityError, match="şüpheli ölçüde uzadı"):
        validate_translation_output(
            "But then he said you thought it was hot, so...",
            (
                "Ama sonra senin onu sıcak bulduğunu söyledi, yani... "
                "Sanırım sadece şaka yapıyordu ve ardından bağlamdaki başka bir cümleyi "
                "de çevirmeye devam edip kaynakta olmayan uzun bir açıklama ekledi."
            ),
        )


def test_allows_reasonable_translation_length_growth() -> None:
    validate_translation_output(
        "I had been feeling quite horny lately...",
        "Son zamanlarda kendimi oldukça azgın hissediyordum...",
    )


def test_rejects_invented_punctuation_after_leading_control_tag() -> None:
    with pytest.raises(QualityError, match="kontrol etiketinden sonra"):
        validate_translation_output(
            "{image=icon_broken.webp}This is a waste of time",
            "{image=icon_broken.webp}:Bu zaman kaybı.",
        )
