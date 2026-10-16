"""Versioned Turkish glossary and character voice assets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast


class LocalizationAssetError(ValueError):
    """Raised when a glossary or character asset is unsafe or malformed."""


class AddressStyle(StrEnum):
    """Turkish second-person form requested for one character."""

    AUTO = "auto"
    SEN = "sen"
    SIZ = "siz"


@dataclass(frozen=True, slots=True)
class GlossaryEntry:
    source: str
    target: str
    case_sensitive: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.target.strip():
            raise LocalizationAssetError("sözlük kaynak ve hedefi boş olamaz")

    def matches(self, text: str) -> bool:
        haystack = text if self.case_sensitive else text.casefold()
        needle = self.source if self.case_sensitive else self.source.casefold()
        return needle in haystack


@dataclass(frozen=True, slots=True)
class Glossary:
    version: str
    entries: tuple[GlossaryEntry, ...]

    def matching(self, source_text: str) -> tuple[GlossaryEntry, ...]:
        return tuple(entry for entry in self.entries if entry.matches(source_text))


@dataclass(frozen=True, slots=True)
class CharacterCard:
    speaker: str
    display_name: str
    address_style: AddressStyle = AddressStyle.AUTO
    traits: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.speaker.strip() or not self.display_name.strip():
            raise LocalizationAssetError("karakter konuşmacısı ve adı boş olamaz")


@dataclass(frozen=True, slots=True)
class LocalizationAssets:
    glossary: Glossary | None = None
    characters: tuple[CharacterCard, ...] = ()

    def character_for(self, speaker: str | None) -> CharacterCard | None:
        if speaker is None:
            return None
        return next((card for card in self.characters if card.speaker == speaker), None)


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LocalizationAssetError(f"Yerelleştirme dosyası okunamadı: {path}: {error}") from error
    if not isinstance(payload, dict):
        raise LocalizationAssetError(f"Yerelleştirme dosyası JSON nesnesi olmalı: {path}")
    if payload.get("schema_version") != 1:
        raise LocalizationAssetError(f"Desteklenmeyen yerelleştirme şeması: {path}")
    return cast(dict[str, object], payload)


def load_glossary(path: Path) -> Glossary:
    payload = _load_json(path)
    version = payload.get("version")
    terms = payload.get("terms")
    if not isinstance(version, str) or not version.strip() or not isinstance(terms, list):
        raise LocalizationAssetError("Sözlük version ve terms alanlarını içermeli")
    entries: list[GlossaryEntry] = []
    seen: set[str] = set()
    for index, raw in enumerate(terms):
        if not isinstance(raw, dict):
            raise LocalizationAssetError(f"Sözlük terimi nesne olmalı: {index}")
        source = raw.get("source")
        target = raw.get("target")
        case_sensitive = raw.get("case_sensitive", False)
        notes = raw.get("notes", "")
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or not isinstance(case_sensitive, bool)
            or not isinstance(notes, str)
        ):
            raise LocalizationAssetError(f"Sözlük terimi alanları geçersiz: {index}")
        key = source if case_sensitive else source.casefold()
        if key in seen:
            raise LocalizationAssetError(f"Yinelenen sözlük kaynağı: {source}")
        seen.add(key)
        entries.append(GlossaryEntry(source, target, case_sensitive, notes))
    return Glossary(version=version, entries=tuple(entries))


def load_character_cards(path: Path) -> tuple[CharacterCard, ...]:
    payload = _load_json(path)
    raw_characters = payload.get("characters")
    if not isinstance(raw_characters, list):
        raise LocalizationAssetError("Karakter dosyası characters listesi içermeli")
    cards: list[CharacterCard] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_characters):
        if not isinstance(raw, dict):
            raise LocalizationAssetError(f"Karakter kartı nesne olmalı: {index}")
        speaker = raw.get("speaker")
        display_name = raw.get("display_name")
        style = raw.get("address_style", "auto")
        traits = raw.get("traits", [])
        notes = raw.get("notes", "")
        if (
            not isinstance(speaker, str)
            or not isinstance(display_name, str)
            or not isinstance(style, str)
            or not isinstance(traits, list)
            or not all(isinstance(trait, str) for trait in traits)
            or not isinstance(notes, str)
        ):
            raise LocalizationAssetError(f"Karakter kartı alanları geçersiz: {index}")
        if speaker in seen:
            raise LocalizationAssetError(f"Yinelenen konuşmacı kartı: {speaker}")
        seen.add(speaker)
        try:
            address_style = AddressStyle(style)
        except ValueError as error:
            raise LocalizationAssetError(f"Geçersiz hitap biçimi: {style}") from error
        cards.append(
            CharacterCard(
                speaker=speaker,
                display_name=display_name,
                address_style=address_style,
                traits=tuple(cast(list[str], traits)),
                notes=notes,
            )
        )
    return tuple(cards)
