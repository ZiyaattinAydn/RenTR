"""Small, stateful parser for Ren'Py-generated translation templates."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from rentr.domain import TranslationKind, TranslationStatus, TranslationUnit, build_source_hash

_TRANSLATE_HEADER = re.compile(
    r"^\s*translate\s+(?P<language>[A-Za-z_][A-Za-z0-9_]*)\s+"
    r"(?P<block_id>[A-Za-z0-9_]+)\s*:\s*$"
)
_LABELLED_ID = re.compile(r"^(?P<label>.+)_[0-9a-fA-F]{8}(?:_\d+)?$")
_PREFIX_SEQUENCE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\s+[A-Za-z_][A-Za-z0-9_]*)*")
_STRING_DELIMITERS = {'"', "'", "`"}
_NON_DIALOGUE_STATEMENTS = {"voice"}


class TemplateParseError(ValueError):
    """Raised when a supported source line is structurally invalid."""


@dataclass(frozen=True, slots=True)
class _Block:
    language: str
    block_id: str

    @property
    def is_strings(self) -> bool:
        return self.block_id == "strings"


def _derive_label(block_id: str) -> str | None:
    match = _LABELLED_ID.fullmatch(block_id)
    return match.group("label") if match else None


@dataclass(frozen=True, slots=True)
class _StringLiteral:
    start: int
    end: int
    delimiter: str
    content: str
    raw: bool


def _scan_string_literals(statement: str, *, line_number: int) -> tuple[_StringLiteral, ...]:
    literals: list[_StringLiteral] = []
    index = 0

    while index < len(statement):
        if statement[index] not in _STRING_DELIMITERS:
            index += 1
            continue

        delimiter = statement[index]
        literal_start = index
        raw = False
        if index > 0 and statement[index - 1] in {"r", "R"}:
            before_raw = statement[index - 2] if index > 1 else ""
            if not (before_raw.isalnum() or before_raw == "_"):
                raw = True
                literal_start -= 1

        content_start = index + 1
        cursor = content_start
        while cursor < len(statement):
            character = statement[cursor]
            if character == "\\":
                cursor += 2
                continue
            if character == delimiter:
                literals.append(
                    _StringLiteral(
                        start=literal_start,
                        end=cursor + 1,
                        delimiter=delimiter,
                        content=statement[content_start:cursor],
                        raw=raw,
                    )
                )
                index = cursor + 1
                break
            cursor += 1
        else:
            raise TemplateParseError(f"Satır {line_number}: kapanmamış Ren'Py metni")

    return tuple(literals)


def _decode_renpy_string(literal: _StringLiteral, *, line_number: int) -> str:
    if literal.raw:
        return literal.content

    decoded: list[str] = []
    index = 0
    escape_values = {"n": "\n", "r": "\r", "t": "\t"}
    while index < len(literal.content):
        character = literal.content[index]
        if character != "\\":
            decoded.append(character)
            index += 1
            continue

        if index + 1 >= len(literal.content):
            raise TemplateParseError(f"Satır {line_number}: tamamlanmamış kaçış dizisi")

        escaped = literal.content[index + 1]
        if escaped in escape_values:
            decoded.append(escape_values[escaped])
        elif escaped == "\\" or escaped in _STRING_DELIMITERS:
            decoded.append(escaped)
        else:
            decoded.extend(("\\", escaped))
        index += 2

    return "".join(decoded)


def _parse_string_statement(statement: str, *, line_number: int) -> tuple[list[str], str]:
    literals = _scan_string_literals(statement, line_number=line_number)
    if len(literals) != 1:
        raise TemplateParseError(f"Satır {line_number}: tam olarak bir kaynak metin bekleniyordu")

    literal = literals[0]
    prefix_text = statement[: literal.start].strip()
    if prefix_text and not _PREFIX_SEQUENCE.fullmatch(prefix_text):
        raise TemplateParseError(f"Satır {line_number}: desteklenmeyen metin öneki")

    prefixes = prefix_text.split() if prefix_text else []
    return prefixes, _decode_renpy_string(literal, line_number=line_number)


def _string_unit_id(source_text: str, occurrence: int) -> str:
    source_hash = build_source_hash(source_text)
    return f"strings:{source_hash[:16]}:{occurrence}"


def _next_content_line(lines: list[str], *, start_index: int) -> tuple[int, str] | None:
    for index in range(start_index, len(lines)):
        raw_line = lines[index]
        if _TRANSLATE_HEADER.fullmatch(raw_line):
            return None
        stripped = raw_line.strip()
        if stripped:
            return index + 1, stripped
    return None


def _translation_state(target_text: str | None) -> TranslationStatus:
    return TranslationStatus.TRANSLATED if target_text is not None else TranslationStatus.PENDING


def _dialogue_target_segments(
    lines: list[str],
    *,
    start_index: int,
    speaker: str | None,
) -> tuple[str, ...]:
    segments: list[str] = []
    for index in range(start_index, len(lines)):
        raw_line = lines[index]
        if _TRANSLATE_HEADER.fullmatch(raw_line):
            break

        statement = raw_line.strip()
        if not statement:
            continue
        if statement.startswith("#"):
            break
        if not any(delimiter in statement for delimiter in _STRING_DELIMITERS):
            continue

        prefixes, target_text = _parse_string_statement(
            statement,
            line_number=index + 1,
        )
        if prefixes and prefixes[0] in _NON_DIALOGUE_STATEMENTS:
            continue

        target_speaker = prefixes[0] if prefixes else None
        if target_speaker != speaker:
            raise TemplateParseError(f"Satır {index + 1}: kaynak ve hedef konuşmacı uyuşmuyor")
        if target_text:
            segments.append(target_text)

    return tuple(segments)


def parse_template_text(text: str, *, file_path: Path) -> tuple[TranslationUnit, ...]:
    """Parse supported source units without evaluating Ren'Py or Python code."""
    units: list[TranslationUnit] = []
    string_occurrences: defaultdict[str, int] = defaultdict(int)
    dialogue_occurrences: defaultdict[str, int] = defaultdict(int)
    current_block: _Block | None = None
    lines = text.splitlines()

    for index, raw_line in enumerate(lines):
        line_number = index + 1
        header_match = _TRANSLATE_HEADER.fullmatch(raw_line)
        if header_match:
            current_block = _Block(
                language=header_match.group("language"),
                block_id=header_match.group("block_id"),
            )
            continue

        if current_block is None:
            continue

        stripped = raw_line.strip()
        if not stripped:
            continue

        if current_block.is_strings:
            if not stripped.startswith("old "):
                continue

            prefixes, source_text = _parse_string_statement(
                stripped,
                line_number=line_number,
            )
            if prefixes != ["old"]:
                raise TemplateParseError(f"Satır {line_number}: geçersiz old metin satırı")

            translated_text: str | None = None
            target_line = _next_content_line(lines, start_index=index + 1)
            if target_line is not None:
                target_line_number, target_statement = target_line
                if target_statement.startswith("new "):
                    target_prefixes, target_text = _parse_string_statement(
                        target_statement,
                        line_number=target_line_number,
                    )
                    if target_prefixes != ["new"]:
                        raise TemplateParseError(
                            f"Satır {target_line_number}: geçersiz new metin satırı"
                        )
                    translated_text = target_text or None
                    if translated_text == source_text:
                        translated_text = None

            string_occurrences[source_text] += 1
            units.append(
                TranslationUnit(
                    unit_id=_string_unit_id(
                        source_text,
                        string_occurrences[source_text],
                    ),
                    source_text=source_text,
                    file_path=file_path,
                    line_number=line_number,
                    kind=TranslationKind.STRING,
                    translated_text=translated_text,
                    status=_translation_state(translated_text),
                )
            )
            continue

        if not stripped.startswith("#"):
            continue

        source_statement = stripped.removeprefix("#").lstrip()
        if not any(delimiter in source_statement for delimiter in _STRING_DELIMITERS):
            continue

        prefixes, source_text = _parse_string_statement(
            source_statement,
            line_number=line_number,
        )
        if prefixes and prefixes[0] in _NON_DIALOGUE_STATEMENTS:
            continue

        speaker = prefixes[0] if prefixes else None
        translated_segments = _dialogue_target_segments(
            lines,
            start_index=index + 1,
            speaker=speaker,
        )
        translated_text = "\n".join(translated_segments) or None
        if translated_text == source_text:
            translated_text = None
            translated_segments = ()

        dialogue_occurrences[current_block.block_id] += 1
        occurrence = dialogue_occurrences[current_block.block_id]
        unit_id = (
            current_block.block_id if occurrence == 1 else f"{current_block.block_id}:{occurrence}"
        )
        units.append(
            TranslationUnit(
                unit_id=unit_id,
                source_text=source_text,
                file_path=file_path,
                line_number=line_number,
                kind=TranslationKind.DIALOGUE,
                speaker=speaker,
                label=_derive_label(current_block.block_id),
                translated_text=translated_text,
                translated_segments=translated_segments,
                status=_translation_state(translated_text),
            )
        )

    return tuple(units)


def parse_template(file_path: Path) -> tuple[TranslationUnit, ...]:
    """Read one UTF-8 Ren'Py translation template and return its source units."""
    return parse_template_text(file_path.read_text(encoding="utf-8"), file_path=file_path)
