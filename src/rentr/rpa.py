"""Fail-closed static reader for standard Ren'Py RPA-3.0 archives."""

from __future__ import annotations

import io
import os
import pickle
import re
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class RpaError(ValueError):
    """Raised when an archive cannot be parsed or extracted safely."""


_RPA3_HEADER = re.compile(rb"^RPA-3\.0 ([0-9a-fA-F]{16}) ([0-9a-fA-F]{8})\n$")
_MAX_HEADER_BYTES = 128
_MAX_COMPRESSED_INDEX_BYTES = 64 * 1024 * 1024
_MAX_INDEX_BYTES = 256 * 1024 * 1024
_MAX_ENTRY_COUNT = 200_000
_MAX_MEMBER_BYTES = 256 * 1024 * 1024
_MAX_PREFIX_BYTES = 1024 * 1024
_MAX_TOTAL_SCRIPT_BYTES = 1024 * 1024 * 1024
_SCRIPT_SUFFIXES = {".rpy", ".rpyc", ".rpym", ".rpymc"}


@dataclass(frozen=True, slots=True)
class RpaSegment:
    offset: int
    length: int
    prefix: bytes = b""

    @property
    def output_length(self) -> int:
        return len(self.prefix) + self.length


@dataclass(frozen=True, slots=True)
class RpaMember:
    archive_name: str
    relative_path: Path
    segments: tuple[RpaSegment, ...]

    @property
    def output_length(self) -> int:
        return sum(segment.output_length for segment in self.segments)


@dataclass(frozen=True, slots=True)
class RpaArchive:
    path: Path
    version: str
    index_offset: int
    key: int
    members: tuple[RpaMember, ...]


@dataclass(frozen=True, slots=True)
class RpaExtractionPlan:
    archive: RpaArchive
    workspace_root: Path
    destination_game_dir: Path
    members: tuple[RpaMember, ...]
    total_output_bytes: int


@dataclass(frozen=True, slots=True)
class RpaExtractionReceipt:
    archive_path: Path
    extracted_files: tuple[Path, ...]


class _RestrictedUnpickler(pickle.Unpickler):
    """RPA indexes may contain containers and primitives, never executable globals."""

    def find_class(self, module: str, name: str) -> object:
        if (module, name) == ("_codecs", "encode"):
            return _safe_pickle_bytes
        raise RpaError(
            f"RPA indeksinde çalıştırılabilir pickle globali reddedildi: {module}.{name}"
        )

    def persistent_load(self, pid: object) -> object:
        raise RpaError(f"RPA indeksinde persistent pickle kimliği reddedildi: {pid!r}")


def _safe_pickle_bytes(value: object, encoding: object, errors: object = "strict") -> bytes:
    """Decode Python 3 protocol-2 bytes without exposing arbitrary pickle globals."""
    if not isinstance(value, str) or encoding != "latin1" or errors != "strict":
        raise RpaError("RPA pickle bytes dönüşümü güvenli latin1 biçiminde değil")
    return value.encode("latin1")


def _safe_unpickle(payload: bytes) -> object:
    buffer = io.BytesIO(payload)
    try:
        result = _RestrictedUnpickler(
            buffer,
            fix_imports=False,
            encoding="bytes",
            errors="strict",
        ).load()
    except RpaError:
        raise
    except (EOFError, pickle.UnpicklingError, ValueError) as error:
        raise RpaError(f"RPA indeksi güvenli biçimde okunamadı: {error}") from error
    if buffer.read(1):
        raise RpaError("RPA pickle indeksinden sonra beklenmeyen veri bulundu")
    return result


def _decompress_index(compressed: bytes) -> bytes:
    if len(compressed) > _MAX_COMPRESSED_INDEX_BYTES:
        raise RpaError("RPA sıkıştırılmış indeksi güvenlik sınırını aşıyor")
    decompressor = zlib.decompressobj()
    try:
        result = decompressor.decompress(compressed, _MAX_INDEX_BYTES + 1)
    except zlib.error as error:
        raise RpaError(f"RPA indeksi zlib olarak açılamadı: {error}") from error
    if len(result) > _MAX_INDEX_BYTES or decompressor.unconsumed_tail:
        raise RpaError("RPA indeksi açma sınırını aşıyor")
    try:
        result += decompressor.flush(_MAX_INDEX_BYTES - len(result) + 1)
    except zlib.error as error:
        raise RpaError(f"RPA indeksi zlib olarak tamamlanamadı: {error}") from error
    if len(result) > _MAX_INDEX_BYTES or not decompressor.eof:
        raise RpaError("RPA indeksi açma sınırını aşıyor veya tamamlanmamış")
    if decompressor.unused_data:
        raise RpaError("RPA indeksinden sonra beklenmeyen veri bulundu")
    return result


def _decode_name(raw_name: object) -> str:
    if isinstance(raw_name, str):
        name = raw_name
    elif isinstance(raw_name, bytes):
        try:
            name = raw_name.decode("utf-8")
        except UnicodeDecodeError as error:
            raise RpaError("RPA dosya adı UTF-8 değil") from error
    else:
        raise RpaError("RPA indeksinde dosya adı string değil")
    if "\\" in name or "\x00" in name or ":" in name:
        raise RpaError(f"Güvensiz RPA dosya adı: {name!r}")
    pure = PurePosixPath(name)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise RpaError(f"Çalışma alanı dışına çıkabilen RPA dosya adı: {name!r}")
    return pure.as_posix()


def _decode_segment(raw: object, *, key: int, index_offset: int) -> RpaSegment:
    if not isinstance(raw, tuple) or len(raw) not in {2, 3}:
        raise RpaError("RPA dosya segmenti 2 veya 3 elemanlı tuple olmalı")
    encoded_offset, encoded_length = raw[:2]
    prefix = raw[2] if len(raw) == 3 else b""
    if not isinstance(encoded_offset, int) or not isinstance(encoded_length, int):
        raise RpaError("RPA segment offset/uzunluğu integer olmalı")
    if isinstance(prefix, str):
        prefix = prefix.encode("latin-1")
    if not isinstance(prefix, bytes) or len(prefix) > _MAX_PREFIX_BYTES:
        raise RpaError("RPA segment prefix'i geçersiz veya çok büyük")
    offset = encoded_offset ^ key
    length = encoded_length ^ key
    if offset < 0 or length < 0 or length > _MAX_MEMBER_BYTES:
        raise RpaError("RPA segment aralığı geçersiz")
    if offset + length > index_offset:
        raise RpaError("RPA segmenti arşiv veri alanının dışına taşıyor")
    return RpaSegment(offset, length, prefix)


def inspect_rpa(path: Path) -> RpaArchive:
    """Read and validate only the standard archive index; never execute game code."""
    archive_path = path.expanduser().resolve()
    if not archive_path.is_file() or archive_path.is_symlink():
        raise RpaError(f"RPA arşivi bulunamadı veya sembolik bağlantı: {archive_path}")
    archive_size = archive_path.stat().st_size
    with archive_path.open("rb") as handle:
        header = handle.readline(_MAX_HEADER_BYTES)
        if not header.endswith(b"\n"):
            raise RpaError("RPA başlığı eksik veya güvenlik sınırından uzun")
        match = _RPA3_HEADER.fullmatch(header)
        if match is None:
            version = header.split(maxsplit=1)[0].decode("ascii", errors="replace")
            raise RpaError(f"Desteklenmeyen RPA sürümü: {version}")
        index_offset = int(match.group(1), 16)
        key = int(match.group(2), 16)
        if index_offset < len(header) or index_offset >= archive_size:
            raise RpaError("RPA indeks offseti arşiv sınırları dışında")
        handle.seek(index_offset)
        compressed_index = handle.read()

    raw_index = _safe_unpickle(_decompress_index(compressed_index))
    if not isinstance(raw_index, dict) or len(raw_index) > _MAX_ENTRY_COUNT:
        raise RpaError("RPA indeksi sözlük değil veya çok fazla dosya içeriyor")
    members: list[RpaMember] = []
    casefold_names: set[str] = set()
    for raw_name, raw_segments in raw_index.items():
        name = _decode_name(raw_name)
        folded = name.casefold()
        if folded in casefold_names:
            raise RpaError(f"Windows'ta çakışan RPA dosya adı: {name}")
        casefold_names.add(folded)
        if not isinstance(raw_segments, (list, tuple)) or not raw_segments:
            raise RpaError(f"RPA dosyasının segment listesi geçersiz: {name}")
        segments = tuple(
            _decode_segment(segment, key=key, index_offset=index_offset)
            for segment in raw_segments
        )
        members.append(RpaMember(name, Path(*PurePosixPath(name).parts), segments))
    return RpaArchive(
        path=archive_path,
        version="RPA-3.0",
        index_offset=index_offset,
        key=key,
        members=tuple(sorted(members, key=lambda member: member.archive_name)),
    )


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def plan_script_extraction(
    archive: RpaArchive,
    destination_game_dir: Path,
    *,
    workspace_root: Path,
) -> RpaExtractionPlan:
    root = workspace_root.expanduser().resolve()
    destination = destination_game_dir.expanduser().resolve()
    if not root.is_dir() or not _is_within(destination, root):
        raise RpaError("RPA çıkarma hedefi izole çalışma alanının içinde olmalı")
    members = tuple(
        member
        for member in archive.members
        if member.relative_path.suffix.casefold() in _SCRIPT_SUFFIXES
    )
    total = sum(member.output_length for member in members)
    if total > _MAX_TOTAL_SCRIPT_BYTES:
        raise RpaError("RPA script çıkarma toplamı güvenlik sınırını aşıyor")
    for member in members:
        output = (destination / member.relative_path).resolve()
        if not _is_within(output, destination):
            raise RpaError(f"RPA hedef yolu çalışma alanından çıkıyor: {member.archive_name}")
        if output.exists() or output.is_symlink():
            raise RpaError(f"RPA hedefi zaten mevcut; üzerine yazılmayacak: {output}")
    return RpaExtractionPlan(archive, root, destination, members, total)


def extract_scripts(plan: RpaExtractionPlan) -> RpaExtractionReceipt:
    """Extract only script artifacts atomically and remove partial results on failure."""
    created: list[Path] = []
    partials: list[Path] = []
    try:
        with plan.archive.path.open("rb") as archive_handle:
            for member in plan.members:
                output = plan.destination_game_dir / member.relative_path
                output.parent.mkdir(parents=True, exist_ok=True)
                partial = output.with_name(f".{output.name}.rentr-extract")
                if partial.exists() or output.exists():
                    raise RpaError(f"RPA çıkarma hedefi artık boş değil: {output}")
                partials.append(partial)
                with partial.open("xb") as target:
                    for segment in member.segments:
                        target.write(segment.prefix)
                        archive_handle.seek(segment.offset)
                        remaining = segment.length
                        while remaining:
                            chunk = archive_handle.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise RpaError(f"RPA segmenti erken bitti: {member.archive_name}")
                            target.write(chunk)
                            remaining -= len(chunk)
                    target.flush()
                    os.fsync(target.fileno())
                partial.replace(output)
                partials.remove(partial)
                created.append(output)
    except BaseException:
        for partial in partials:
            partial.unlink(missing_ok=True)
        for output in created:
            output.unlink(missing_ok=True)
        raise
    return RpaExtractionReceipt(plan.archive.path, tuple(created))
