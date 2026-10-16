"""Read-only Ren'Py game layout inspection."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class GameInspectionError(ValueError):
    """Raised when the selected path is not a usable Ren'Py game root."""


class GameInputMode(StrEnum):
    """The next safe processing route for a selected game."""

    SOURCE = "source"
    PACKAGED = "packaged"
    RESUME = "resume"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class GameInspection:
    """Inventory of script containers without executing or extracting them."""

    selected_root: Path
    game_dir: Path
    translation_dir: Path
    mode: GameInputMode
    source_scripts: tuple[Path, ...]
    compiled_scripts: tuple[Path, ...]
    archives: tuple[Path, ...]
    translation_files: tuple[Path, ...]

    @property
    def next_action(self) -> str:
        actions = {
            GameInputMode.SOURCE: "generate_translation_templates",
            GameInputMode.PACKAGED: "prepare_isolated_extraction",
            GameInputMode.RESUME: "inventory_existing_translation",
            GameInputMode.UNSUPPORTED: "report_unsupported_layout",
        }
        return actions[self.mode]


def _find_game_dir(selected_root: Path) -> Path:
    if selected_root.name.casefold() == "game" and selected_root.is_dir():
        return selected_root

    candidate = selected_root / "game"
    if candidate.is_dir():
        return candidate

    raise GameInspectionError(f"Seçilen klasörde Ren'Py game dizini bulunamadı: {selected_root}")


def _walk_files(game_dir: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    for current_root, directory_names, file_names in os.walk(game_dir, followlinks=False):
        directory_names.sort()
        file_names.sort()
        current_path = Path(current_root)
        files.extend(
            path for file_name in file_names if not (path := current_path / file_name).is_symlink()
        )
    return tuple(files)


def inspect_game(selected_root: Path) -> GameInspection:
    """Classify a Ren'Py folder without importing, running, or extracting content."""
    resolved_root = selected_root.expanduser().resolve()
    if not resolved_root.is_dir():
        raise GameInspectionError(f"Seçilen oyun klasörü bulunamadı: {resolved_root}")

    game_dir = _find_game_dir(resolved_root)
    translation_dir = game_dir / "tl" / "turkish"
    all_files = _walk_files(game_dir)

    translation_files = tuple(
        path
        for path in all_files
        if path.suffix.casefold() == ".rpy" and translation_dir in path.parents
    )
    source_scripts = tuple(
        path
        for path in all_files
        if path.suffix.casefold() == ".rpy" and translation_dir not in path.parents
    )
    compiled_scripts = tuple(path for path in all_files if path.suffix.casefold() == ".rpyc")
    archives = tuple(path for path in all_files if path.suffix.casefold() == ".rpa")

    if translation_files:
        mode = GameInputMode.RESUME
    elif source_scripts:
        mode = GameInputMode.SOURCE
    elif compiled_scripts or archives:
        mode = GameInputMode.PACKAGED
    else:
        mode = GameInputMode.UNSUPPORTED

    return GameInspection(
        selected_root=resolved_root,
        game_dir=game_dir,
        translation_dir=translation_dir,
        mode=mode,
        source_scripts=source_scripts,
        compiled_scripts=compiled_scripts,
        archives=archives,
        translation_files=translation_files,
    )
