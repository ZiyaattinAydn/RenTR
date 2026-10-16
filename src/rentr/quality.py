"""Fail-closed quality checks that are safe to run after token restoration."""

from __future__ import annotations

import re
import unicodedata


class QualityError(ValueError):
    """Raised when provider output violates a deterministic quality invariant."""


_PROMPT_LABELS = (
    "Speaker:",
    "Scene label:",
    "Previous source:",
    "Next source:",
    "Character:",
    "Character notes:",
    "Review-only similar translations:",
    "Required term:",
    "Text:",
)


_CONTROL_FRAGMENT = re.compile(r"\{[^{}]*\}|\[[^\[\]]*\]")


def _visible_length(text: str) -> int:
    return len(_CONTROL_FRAGMENT.sub("", text).strip())


def _reject_suspicious_expansion(source_text: str, translated_text: str) -> None:
    source_length = _visible_length(source_text)
    translated_length = _visible_length(translated_text)
    if source_length < 20:
        return
    if translated_length > source_length * 2.75 and translated_length - source_length > 60:
        raise QualityError(
            "Çeviri kaynak metne göre şüpheli ölçüde uzadı; "
            "bağlam devamı veya ek bilgi sızmış olabilir"
        )


_SUSPICIOUS_SCRIPT_MARKERS = (
    "ARABIC",
    "ARMENIAN",
    "BENGALI",
    "CJK",
    "CYRILLIC",
    "DEVANAGARI",
    "ETHIOPIC",
    "GEORGIAN",
    "GREEK",
    "GUJARATI",
    "GURMUKHI",
    "HANGUL",
    "HEBREW",
    "HIRAGANA",
    "KATAKANA",
    "MALAYALAM",
    "SINHALA",
    "TAMIL",
    "TELUGU",
    "THAI",
)


def _unexpected_script_characters(source_text: str, translated_text: str) -> tuple[str, ...]:
    source_characters = set(source_text)
    unexpected: list[str] = []
    seen: set[str] = set()
    for character in translated_text:
        if character in source_characters or character in seen or not character.isalpha():
            continue
        name = unicodedata.name(character, "")
        if any(marker in name for marker in _SUSPICIOUS_SCRIPT_MARKERS):
            unexpected.append(character)
            seen.add(character)
    return tuple(unexpected)




def _reject_boundary_punctuation_invention(source_text: str, translated_text: str) -> None:
    """Reject stray punctuation inserted immediately after a leading Ren'Py tag cluster."""

    leading = re.compile(r"^(?P<tags>(?:\{[^{}]*\})+)(?P<rest>.*)$", re.DOTALL)
    source_match = leading.match(source_text)
    translated_match = leading.match(translated_text)
    if source_match is None or translated_match is None:
        return
    source_rest = source_match.group("rest").lstrip()
    translated_rest = translated_match.group("rest").lstrip()
    if not source_rest or not translated_rest:
        return
    if source_rest[0].isalnum() and translated_rest[0] in ":;,":
        raise QualityError(
            "Çeviri başlangıçtaki Ren'Py kontrol etiketinden sonra kaynakta olmayan "
            "noktalama ekledi"
        )


def validate_translation_output(source_text: str, translated_text: str) -> None:
    """Reject deterministic corruption without trying to judge literary quality."""
    if not translated_text.strip():
        raise QualityError("Çeviri çıktısı boş")

    lines = tuple(line.strip() for line in translated_text.splitlines())
    leaked = next(
        (
            label
            for label in _PROMPT_LABELS
            if label not in source_text and any(line.startswith(label) for line in lines)
        ),
        None,
    )
    if leaked is not None:
        raise QualityError(f"Çeviri bağlam metadatasını çıktıya sızdırdı: {leaked}")

    unexpected = _unexpected_script_characters(source_text, translated_text)
    if unexpected:
        rendered = " ".join(repr(character) for character in unexpected[:8])
        raise QualityError(
            "Çeviri kaynakta olmayan beklenmeyen yazı sistemi karakterleri içeriyor: "
            f"{rendered}"
        )

    _reject_suspicious_expansion(source_text, translated_text)
    _reject_boundary_punctuation_invention(source_text, translated_text)
