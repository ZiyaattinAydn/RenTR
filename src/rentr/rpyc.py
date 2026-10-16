"""Static RPYC container preflight; no pickle loading or game execution."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class RpycError(ValueError):
    """Raised when a compiled script container is malformed."""


class RpycFormat(StrEnum):
    RPC2 = "rpc2"
    LEGACY_ZLIB = "legacy-zlib"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RpycSection:
    slot: int
    offset: int
    length: int


@dataclass(frozen=True, slots=True)
class RpycInspection:
    path: Path
    format: RpycFormat
    file_size: int
    sections: tuple[RpycSection, ...]
    safe_to_unpickle: bool = False


_RPC2_HEADER = b"RENPY RPC2"
_SECTION = struct.Struct("<III")
_MAX_SECTIONS = 32


def inspect_rpyc(path: Path) -> RpycInspection:
    """Validate only container offsets; intentionally never decode its pickle AST."""
    resolved = path.expanduser().resolve()
    if not resolved.is_file() or resolved.is_symlink():
        raise RpycError(f"RPYC dosyası bulunamadı veya sembolik bağlantı: {resolved}")
    size = resolved.stat().st_size
    with resolved.open("rb") as handle:
        header = handle.read(len(_RPC2_HEADER))
        if header != _RPC2_HEADER:
            handle.seek(0)
            prefix = handle.read(2)
            detected = RpycFormat.LEGACY_ZLIB if prefix.startswith(b"x") else RpycFormat.UNKNOWN
            return RpycInspection(resolved, detected, size, ())

        sections: list[RpycSection] = []
        seen_slots: set[int] = set()
        for _ in range(_MAX_SECTIONS + 1):
            raw = handle.read(_SECTION.size)
            if len(raw) != _SECTION.size:
                raise RpycError("RPYC2 bölüm tablosu erken bitti")
            slot, offset, length = _SECTION.unpack(raw)
            if slot == 0:
                break
            if slot in seen_slots:
                raise RpycError(f"RPYC2 yinelenen bölüm slotu: {slot}")
            if offset < len(_RPC2_HEADER) or length == 0 or offset + length > size:
                raise RpycError(f"RPYC2 bölüm aralığı geçersiz: slot={slot}")
            seen_slots.add(slot)
            sections.append(RpycSection(slot, offset, length))
        else:
            raise RpycError("RPYC2 bölüm sayısı güvenlik sınırını aşıyor")
    if not sections:
        raise RpycError("RPYC2 kullanılabilir bölüm içermiyor")
    return RpycInspection(resolved, RpycFormat.RPC2, size, tuple(sections))
