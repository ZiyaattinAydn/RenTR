"""Protect Ren'Py control syntax before text is sent to a translator."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class ProtectionError(ValueError):
    """Raised when protected syntax is malformed or altered."""


class ProtectionKind(StrEnum):
    """Ren'Py fragments that a translation provider must not rewrite."""

    TEXT_TAG = "text_tag"
    INTERPOLATION = "interpolation"
    PERCENT_FORMAT = "percent_format"
    ESCAPE = "escape"


@dataclass(frozen=True, slots=True)
class ProtectionToken:
    """One source fragment replaced by a deterministic opaque placeholder."""

    index: int
    kind: ProtectionKind
    original: str
    placeholder: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("token index negatif olamaz")
        if not self.original:
            raise ValueError("korunan özgün parça boş olamaz")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("token kaynak aralığı geçersiz")


@dataclass(frozen=True, slots=True)
class ProtectedText:
    """Provider-safe text and the ordered restoration contract."""

    source_text: str
    protected_text: str
    tokens: tuple[ProtectionToken, ...]


_PERCENT_FORMAT = re.compile(
    r"%"
    r"(?:\([^)]+\))?"
    r"[#0\- +]*"
    r"(?:\d+|\*)?"
    r"(?:\.(?:\d+|\*))?"
    r"[hlL]?"
    r"[diouxXeEfFgGcrsa]"
)
_PLACEHOLDER = re.compile(r"__RENTR_[0-9]{4}__")


def _placeholder(index: int) -> str:
    return f"__RENTR_{index:04d}__"


def _consume_balanced(
    text: str,
    *,
    start: int,
    opener: str,
    closer: str,
    label: str,
) -> int:
    """Return the exclusive end of one non-nested Ren'Py construct."""
    cursor = start + 1
    while cursor < len(text):
        character = text[cursor]
        if character == "\\" and cursor + 1 < len(text):
            cursor += 2
            continue
        if character == closer:
            if cursor == start + 1:
                raise ProtectionError(f"Boş {label} desteklenmiyor: konum {start}")
            return cursor + 1
        if character == opener:
            raise ProtectionError(f"İç içe {label} desteklenmiyor: konum {cursor}")
        cursor += 1
    raise ProtectionError(f"Kapanmamış {label}: konum {start}")


def protect_text(text: str) -> ProtectedText:
    """Replace control syntax with ordered placeholders without evaluating it."""
    protected: list[str] = []
    tokens: list[ProtectionToken] = []
    cursor = 0

    def append_token(kind: ProtectionKind, end: int) -> None:
        index = len(tokens)
        placeholder = _placeholder(index)
        original = text[cursor:end]
        tokens.append(
            ProtectionToken(
                index=index,
                kind=kind,
                original=original,
                placeholder=placeholder,
                start=cursor,
                end=end,
            )
        )
        protected.append(placeholder)

    while cursor < len(text):
        character = text[cursor]

        if text[cursor : cursor + 2] in {"{{", "[["}:
            protected.append(text[cursor : cursor + 2])
            cursor += 2
            continue

        if character == "{":
            end = _consume_balanced(
                text,
                start=cursor,
                opener="{",
                closer="}",
                label="Ren'Py text tag'i",
            )
            append_token(ProtectionKind.TEXT_TAG, end)
            cursor = end
            continue

        if character == "[":
            end = _consume_balanced(
                text,
                start=cursor,
                opener="[",
                closer="]",
                label="Ren'Py interpolasyonu",
            )
            append_token(ProtectionKind.INTERPOLATION, end)
            cursor = end
            continue

        if character == "%":
            if text[cursor : cursor + 2] == "%%":
                append_token(ProtectionKind.ESCAPE, cursor + 2)
                cursor += 2
                continue
            percent_match = _PERCENT_FORMAT.match(text, cursor)
            if percent_match is not None:
                append_token(ProtectionKind.PERCENT_FORMAT, percent_match.end())
                cursor = percent_match.end()
                continue

        if character == "\\" and cursor + 1 < len(text):
            append_token(ProtectionKind.ESCAPE, cursor + 2)
            cursor += 2
            continue

        if character in {"\n", "\r", "\t"}:
            append_token(ProtectionKind.ESCAPE, cursor + 1)
            cursor += 1
            continue

        protected.append(character)
        cursor += 1

    return ProtectedText(
        source_text=text,
        protected_text="".join(protected),
        tokens=tuple(tokens),
    )


def _validate_placeholder_layout(translated_text: str, protected: ProtectedText) -> None:
    """Keep boundary anchors and source-adjacent token groups structurally stable."""
    if not protected.tokens:
        return

    source = protected.protected_text
    first = protected.tokens[0].placeholder
    last = protected.tokens[-1].placeholder
    translated_stripped = translated_text.strip()

    first_source_index = source.index(first)
    if not source[:first_source_index].strip() and not translated_stripped.startswith(first):
        raise ProtectionError("Çeviri başlangıçtaki Ren'Py kontrol tokenını yerinden oynattı")

    last_source_index = source.index(last) + len(last)
    if not source[last_source_index:].strip() and not translated_stripped.endswith(last):
        raise ProtectionError("Çeviri sondaki Ren'Py kontrol tokenını yerinden oynattı")

    for token in protected.tokens:
        source_before = source[: source.index(token.placeholder)]
        source_after_start = source.index(token.placeholder) + len(token.placeholder)
        source_after = source[source_after_start:]
        source_inline_left = bool(source_before) and not source_before[-1].isspace()
        source_inline_right = bool(source_after) and not source_after[0].isspace()
        if source_inline_left and source_inline_right:
            translated_index = translated_text.index(token.placeholder)
            translated_before = translated_text[:translated_index]
            translated_after = translated_text[translated_index + len(token.placeholder) :]
            if (
                not translated_before
                or translated_before[-1].isspace()
                or not translated_after
                or translated_after[0].isspace()
            ):
                raise ProtectionError(
                    "Çeviri satır içindeki Ren'Py kontrol tokenını kelime/ifade bağından kopardı"
                )

    for left, right in zip(protected.tokens, protected.tokens[1:], strict=False):
        source_left_end = source.index(left.placeholder) + len(left.placeholder)
        source_right_start = source.index(right.placeholder)
        if source[source_left_end:source_right_start].strip():
            continue

        translated_left_end = translated_text.index(left.placeholder) + len(left.placeholder)
        translated_right_start = translated_text.index(right.placeholder)
        if translated_text[translated_left_end:translated_right_start].strip():
            raise ProtectionError(
                "Çeviri kaynakta bitişik olan Ren'Py kontrol tokenlarının arasına metin ekledi"
            )


def restore_text(translated_text: str, protected: ProtectedText) -> str:
    """Restore exact tokens after rejecting missing, changed, reordered, or moved controls."""
    found = tuple(match.group(0) for match in _PLACEHOLDER.finditer(translated_text))
    expected = tuple(token.placeholder for token in protected.tokens)
    if found != expected:
        raise ProtectionError(
            "Çeviri koruma tokenlarını eksik, fazla, değiştirilmiş veya sırası bozulmuş döndürdü"
        )

    _validate_placeholder_layout(translated_text, protected)

    restored = translated_text
    for token in protected.tokens:
        restored = restored.replace(token.placeholder, token.original, 1)

    if _PLACEHOLDER.search(restored) is not None:
        raise ProtectionError("Çeviri çıktısında beklenmeyen RenTR tokenı kaldı")
    return restored


def _boundary_placeholder_segments(protected: ProtectedText) -> tuple[str, str]:
    """Return source prefix/suffix scaffolds made only of placeholders/whitespace.

    This intentionally excludes internal controls. It is safe to reconstruct a control that
    wraps/anchors the whole line or sits at the absolute beginning/end because translation does
    not need word alignment to know its destination.
    """

    source = protected.protected_text
    placeholder_pattern = r"__RENTR_[0-9]{4}__"
    prefix_match = re.match(rf"^(?P<segment>(?:(?:{placeholder_pattern})\s*)+)", source)
    suffix_match = re.search(rf"(?P<segment>(?:\s*(?:{placeholder_pattern}))+)$", source)
    prefix = prefix_match.group("segment") if prefix_match is not None else ""
    suffix = suffix_match.group("segment") if suffix_match is not None else ""

    # One control-only line can be both prefix and suffix. Such lines should have been passthrough
    # already; avoid duplicating the scaffold if this helper is reached defensively.
    if prefix and suffix and len(prefix) == len(source) and len(suffix) == len(source):
        return source, ""
    return prefix, suffix


def restore_text_with_boundary_salvage(
    translated_text: str,
    protected: ProtectedText,
) -> str:
    """Restore controls, repairing only deterministic line-boundary placeholder damage.

    Providers occasionally drop or move an image/style/timing placeholder even when the Turkish
    text itself is usable. We still fail closed for *internal* controls because their target
    location needs semantic alignment. Absolute prefix/suffix controls, however, have an
    unambiguous destination and can be reconstructed without asking an LLM to guess.
    """

    try:
        return restore_text(translated_text, protected)
    except ProtectionError as original_error:
        if not protected.tokens:
            raise

        expected = tuple(token.placeholder for token in protected.tokens)
        found = tuple(match.group(0) for match in _PLACEHOLDER.finditer(translated_text))
        if any(item not in expected for item in found):
            raise original_error

        prefix, suffix = _boundary_placeholder_segments(protected)
        boundary = tuple(_PLACEHOLDER.findall(prefix + suffix))
        if not boundary:
            raise original_error

        boundary_tokens = tuple(
            token for token in protected.tokens if token.placeholder in boundary
        )
        if any(token.kind is not ProtectionKind.TEXT_TAG for token in boundary_tokens):
            # Interpolation, printf escapes and literal escapes carry data/format semantics and
            # must never be reconstructed from position alone.
            raise original_error

        if any(placeholder in found for placeholder in boundary):
            # Salvage only omitted boundary controls. A present-but-moved control or a control
            # cluster with model text inserted around it remains a hard failure.
            raise original_error

        internal = tuple(item for item in expected if item not in boundary)
        found_internal = tuple(item for item in found if item in internal)
        if found_internal != internal:
            # Missing/reordered internal markup is still unsafe to repair deterministically.
            raise original_error

        candidate = translated_text
        candidate = candidate.strip()
        if prefix:
            candidate = prefix + candidate.lstrip()
        if suffix:
            candidate = candidate.rstrip() + suffix

        try:
            return restore_text(candidate, protected)
        except ProtectionError:
            raise original_error from None
