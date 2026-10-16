"""Core domain types shared by the CLI and future desktop interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from pathlib import Path


class TranslationStatus(StrEnum):
    """Lifecycle state of one translation unit."""

    PENDING = "pending"
    TRANSLATED = "translated"
    VALIDATED = "validated"
    REVIEW = "review"
    APPROVED = "approved"
    FAILED = "failed"


class TranslationKind(StrEnum):
    """Ren'Py source unit category."""

    DIALOGUE = "dialogue"
    STRING = "string"


def build_source_hash(
    source_text: str,
    *,
    speaker: str | None = None,
    label: str | None = None,
) -> str:
    """Build a deterministic identity input without exposing source text."""
    components = (source_text, speaker or "", label or "")
    payload = "\x1f".join(components).encode("utf-8")
    return sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class TranslationUnit:
    """One source text unit discovered in a Ren'Py translation template."""

    unit_id: str
    source_text: str
    file_path: Path
    line_number: int
    kind: TranslationKind
    speaker: str | None = None
    label: str | None = None
    translated_text: str | None = None
    translated_segments: tuple[str, ...] = ()
    status: TranslationStatus = TranslationStatus.PENDING
    source_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.unit_id.strip():
            raise ValueError("unit_id boş olamaz")
        if self.line_number < 1:
            raise ValueError("line_number 1 veya daha büyük olmalı")

        if self.translated_text is not None and not self.translated_segments:
            object.__setattr__(self, "translated_segments", (self.translated_text,))
        elif self.translated_text is None and self.translated_segments:
            object.__setattr__(self, "translated_text", "\n".join(self.translated_segments))
        elif (
            self.translated_text is not None
            and self.translated_segments
            and self.translated_text != "\n".join(self.translated_segments)
        ):
            raise ValueError("translated_text ve translated_segments uyuşmuyor")

        object.__setattr__(
            self,
            "source_hash",
            build_source_hash(
                self.source_text,
                speaker=self.speaker,
                label=self.label,
            ),
        )
