"""Local SQLite translation memory with human-edit locking and review candidates."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from threading import RLock

from rentr.domain import TranslationUnit


class TranslationMemoryError(ValueError):
    """Raised when a memory mutation would violate a preservation rule."""


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    """One locally persisted source/target pair."""

    unit_id: str
    source_hash: str
    source_text: str
    translated_text: str
    provider: str
    locked: bool
    updated_at: str


@dataclass(frozen=True, slots=True)
class ReviewCandidate:
    """A non-exact memory match that must be reviewed by a person."""

    entry: MemoryEntry
    similarity: float


@dataclass(frozen=True, slots=True)
class MemoryRevision:
    revision_id: int
    unit_id: str
    source_hash: str
    translated_text: str
    provider: str
    locked: bool
    created_at: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS translation_memory (
    unit_id TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    source_text TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    provider TEXT NOT NULL,
    locked INTEGER NOT NULL DEFAULT 0 CHECK (locked IN (0, 1)),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (unit_id, source_hash)
);

CREATE INDEX IF NOT EXISTS idx_translation_memory_source_hash
ON translation_memory(source_hash);

CREATE TABLE IF NOT EXISTS translation_history (
    revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    provider TEXT NOT NULL,
    locked INTEGER NOT NULL CHECK (locked IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_translation_history_unit
ON translation_history(unit_id, source_hash, revision_id DESC);
"""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class TranslationMemory:
    """Small repository shared by CLI now and the desktop UI later."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = FULL")
        self._connection.executescript(_SCHEMA)
        self._connection.commit()

    def __enter__(self) -> TranslationMemory:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _entry(row: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            unit_id=str(row["unit_id"]),
            source_hash=str(row["source_hash"]),
            source_text=str(row["source_text"]),
            translated_text=str(row["translated_text"]),
            provider=str(row["provider"]),
            locked=bool(row["locked"]),
            updated_at=str(row["updated_at"]),
        )

    def get(self, unit: TranslationUnit) -> MemoryEntry | None:
        """Return only an exact unit-id and source-hash match."""
        with self._lock:
            row = self._connection.execute(
                """
                SELECT unit_id, source_hash, source_text, translated_text,
                       provider, locked, updated_at
                FROM translation_memory
                WHERE unit_id = ? AND source_hash = ?
                """,
                (unit.unit_id, unit.source_hash),
            ).fetchone()
        return self._entry(row) if row is not None else None

    def save(
        self,
        unit: TranslationUnit,
        translated_text: str,
        *,
        provider: str,
        locked: bool = False,
    ) -> MemoryEntry:
        """Persist an exact translation unless an existing human lock forbids overwrite."""
        if not translated_text.strip():
            raise TranslationMemoryError("boş çeviri belleğe kaydedilemez")
        if not provider.strip():
            raise TranslationMemoryError("sağlayıcı adı boş olamaz")

        with self._lock:
            existing = self.get(unit)
            if (
                existing is not None
                and existing.locked
                and existing.translated_text != translated_text
            ):
                raise TranslationMemoryError("kilitli insan çevirisinin üzerine yazılamaz")

            effective_locked = locked or (existing.locked if existing is not None else False)
            updated_at = _utc_now()
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO translation_memory (
                        unit_id, source_hash, source_text, translated_text,
                        provider, locked, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(unit_id, source_hash) DO UPDATE SET
                        source_text = excluded.source_text,
                        translated_text = excluded.translated_text,
                        provider = excluded.provider,
                        locked = excluded.locked,
                        updated_at = excluded.updated_at
                    """,
                    (
                        unit.unit_id,
                        unit.source_hash,
                        unit.source_text,
                        translated_text,
                        provider,
                        int(effective_locked),
                        updated_at,
                    ),
                )
                self._connection.execute(
                    """
                    INSERT INTO translation_history (
                        unit_id, source_hash, translated_text, provider, locked, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        unit.unit_id,
                        unit.source_hash,
                        translated_text,
                        provider,
                        int(effective_locked),
                        updated_at,
                    ),
                )

            saved = self.get(unit)
            if saved is None:  # pragma: no cover - SQLite invariant guard
                raise TranslationMemoryError("çeviri belleği kaydı doğrulanamadı")
            return saved

    def set_locked(self, unit: TranslationUnit, *, locked: bool = True) -> MemoryEntry:
        """Lock or unlock an existing exact entry."""
        with self._lock:
            with self._connection:
                cursor = self._connection.execute(
                    """
                    UPDATE translation_memory
                    SET locked = ?, updated_at = ?
                    WHERE unit_id = ? AND source_hash = ?
                    """,
                    (int(locked), _utc_now(), unit.unit_id, unit.source_hash),
                )
            if cursor.rowcount != 1:
                raise TranslationMemoryError("kilitlenecek çeviri bellekte bulunamadı")
            entry = self.get(unit)
            if entry is None:  # pragma: no cover - SQLite invariant guard
                raise TranslationMemoryError("kilitlenen kayıt yeniden okunamadı")
            return entry

    def find_similar(
        self,
        source_text: str,
        *,
        threshold: float = 0.72,
        limit: int = 5,
    ) -> tuple[ReviewCandidate, ...]:
        """Return ranked fuzzy matches as review-only suggestions."""
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("benzerlik eşiği 0 ile 1 arasında olmalı")
        if limit < 1:
            raise ValueError("limit 1 veya daha büyük olmalı")

        with self._lock:
            rows = self._connection.execute(
                """
                SELECT unit_id, source_hash, source_text, translated_text,
                       provider, locked, updated_at
                FROM translation_memory
                """
            ).fetchall()
        candidates = (
            ReviewCandidate(
                entry=self._entry(row),
                similarity=SequenceMatcher(
                    None,
                    source_text.casefold(),
                    str(row["source_text"]).casefold(),
                ).ratio(),
            )
            for row in rows
            if str(row["source_text"]) != source_text
        )
        eligible = (candidate for candidate in candidates if candidate.similarity >= threshold)
        return tuple(
            sorted(
                eligible,
                key=lambda candidate: (-candidate.similarity, candidate.entry.unit_id),
            )[:limit]
        )

    def history(self, unit: TranslationUnit) -> tuple[MemoryRevision, ...]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT revision_id, unit_id, source_hash, translated_text,
                       provider, locked, created_at
                FROM translation_history
                WHERE unit_id = ? AND source_hash = ?
                ORDER BY revision_id DESC
                """,
                (unit.unit_id, unit.source_hash),
            ).fetchall()
        return tuple(
            MemoryRevision(
                revision_id=int(row["revision_id"]),
                unit_id=str(row["unit_id"]),
                source_hash=str(row["source_hash"]),
                translated_text=str(row["translated_text"]),
                provider=str(row["provider"]),
                locked=bool(row["locked"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        )

    def restore_revision(self, unit: TranslationUnit, revision_id: int) -> MemoryEntry:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT translated_text FROM translation_history
                WHERE revision_id = ? AND unit_id = ? AND source_hash = ?
                """,
                (revision_id, unit.unit_id, unit.source_hash),
            ).fetchone()
            if row is None:
                raise TranslationMemoryError("geri alınacak çeviri sürümü bulunamadı")
            restored_text = str(row["translated_text"])
            updated_at = _utc_now()
            with self._connection:
                cursor = self._connection.execute(
                    """
                    UPDATE translation_memory
                    SET translated_text = ?, provider = 'history-restore',
                        locked = 1, updated_at = ?
                    WHERE unit_id = ? AND source_hash = ?
                    """,
                    (restored_text, updated_at, unit.unit_id, unit.source_hash),
                )
                if cursor.rowcount != 1:
                    raise TranslationMemoryError("geri alınacak güncel kayıt bulunamadı")
                self._connection.execute(
                    """
                    INSERT INTO translation_history (
                        unit_id, source_hash, translated_text, provider, locked, created_at
                    ) VALUES (?, ?, ?, 'history-restore', 1, ?)
                    """,
                    (unit.unit_id, unit.source_hash, restored_text, updated_at),
                )
            restored = self.get(unit)
            if restored is None:  # pragma: no cover - SQLite invariant guard
                raise TranslationMemoryError("geri alınan kayıt doğrulanamadı")
            return restored

