from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from rentr.domain import TranslationKind, TranslationUnit
from rentr.memory import TranslationMemory, TranslationMemoryError


def _unit(source: str = "Start Game", *, unit_id: str = "strings:one:1") -> TranslationUnit:
    return TranslationUnit(
        unit_id=unit_id,
        source_text=source,
        file_path=Path("script.rpy"),
        line_number=1,
        kind=TranslationKind.STRING,
    )


def test_exact_source_hash_cache_round_trip(tmp_path: Path) -> None:
    unit = _unit()
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        saved = memory.save(unit, "Oyuna Başla", provider="mock")

        assert memory.get(unit) == saved
        assert saved.translated_text == "Oyuna Başla"
        assert not saved.locked


def test_source_change_is_a_cache_miss(tmp_path: Path) -> None:
    original = _unit()
    changed = _unit("Start New Game")
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        memory.save(original, "Oyuna Başla", provider="mock")

        assert memory.get(changed) is None


def test_locked_human_translation_cannot_be_overwritten(tmp_path: Path) -> None:
    unit = _unit()
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        memory.save(unit, "Başlat", provider="human", locked=True)

        with pytest.raises(TranslationMemoryError, match="kilitli"):
            memory.save(unit, "Oyuna Başla", provider="provider")

        assert memory.get(unit).translated_text == "Başlat"  # type: ignore[union-attr]


def test_lock_and_unlock_existing_entry(tmp_path: Path) -> None:
    unit = _unit()
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        memory.save(unit, "Oyuna Başla", provider="mock")

        assert memory.set_locked(unit).locked
        assert not memory.set_locked(unit, locked=False).locked


def test_missing_entry_cannot_be_locked(tmp_path: Path) -> None:
    with (
        TranslationMemory(tmp_path / "memory.sqlite3") as memory,
        pytest.raises(TranslationMemoryError, match="bulunamadı"),
    ):
        memory.set_locked(_unit())


def test_similar_sources_are_review_only_and_ranked(tmp_path: Path) -> None:
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        memory.save(_unit("Start Game", unit_id="one"), "Oyuna Başla", provider="mock")
        memory.save(_unit("Start a Game", unit_id="two"), "Bir Oyun Başlat", provider="mock")
        memory.save(_unit("Preferences", unit_id="three"), "Tercihler", provider="mock")

        candidates = memory.find_similar("Start New Game", threshold=0.5)

        assert [candidate.entry.unit_id for candidate in candidates] == ["two", "one"]
        assert candidates[0].similarity >= candidates[1].similarity


@pytest.mark.parametrize(
    ("threshold", "limit"),
    [(-0.1, 5), (1.1, 5), (0.5, 0)],
)
def test_rejects_invalid_similarity_options(
    tmp_path: Path,
    threshold: float,
    limit: int,
) -> None:
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory, pytest.raises(ValueError):
        memory.find_similar("text", threshold=threshold, limit=limit)


def test_keeps_translation_history_and_restores_as_locked_human_choice(tmp_path: Path) -> None:
    unit = _unit()
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        first = memory.save(unit, "Başlat", provider="provider-one")
        memory.save(unit, "Oyuna Başla", provider="provider-two")
        history = memory.history(unit)

        assert [revision.translated_text for revision in history] == ["Oyuna Başla", "Başlat"]
        restored = memory.restore_revision(unit, history[-1].revision_id)

    assert first.translated_text == "Başlat"
    assert restored.translated_text == "Başlat"
    assert restored.provider == "history-restore"
    assert restored.locked


def test_rejects_unknown_history_revision(tmp_path: Path) -> None:
    unit = _unit()
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        memory.save(unit, "Başlat", provider="provider")
        with pytest.raises(TranslationMemoryError, match="sürümü"):
            memory.restore_revision(unit, 99999)


def test_shared_memory_connection_is_thread_safe(tmp_path: Path) -> None:
    units = [_unit(f"Text {index}", unit_id=f"unit-{index}") for index in range(8)]
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        with ThreadPoolExecutor(max_workers=4) as executor:
            saved = tuple(
                executor.map(
                    lambda item: memory.save(
                        item,
                        f"Çeviri {item.unit_id}",
                        provider="parallel-test",
                    ),
                    units,
                )
            )

        assert len(saved) == len(units)
        assert all(memory.get(unit) is not None for unit in units)
