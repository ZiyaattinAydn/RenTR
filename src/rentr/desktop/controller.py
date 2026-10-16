"""UI-independent desktop state controller."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from rentr.domain import TranslationUnit
from rentr.parser import parse_template
from rentr.scanner import GameInspection, inspect_game


class DesktopState(StrEnum):
    IDLE = "idle"
    INSPECTED = "inspected"
    READY = "ready"
    WORKING = "working"
    PREVIEW = "preview"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DesktopSnapshot:
    state: DesktopState
    game: GameInspection | None
    template_path: Path | None
    units: tuple[TranslationUnit, ...]
    message: str


class DesktopController:
    """Small state machine; Qt widgets only render this state."""

    def __init__(self) -> None:
        self._snapshot = DesktopSnapshot(DesktopState.IDLE, None, None, (), "Oyun seçilmedi")

    @property
    def snapshot(self) -> DesktopSnapshot:
        return self._snapshot

    def inspect(self, game_root: Path) -> DesktopSnapshot:
        inspection = inspect_game(game_root)
        template = inspection.translation_files[0] if inspection.translation_files else None
        units = tuple(
            unit
            for translation_file in inspection.translation_files
            for unit in parse_template(translation_file)
        )
        state = DesktopState.READY if template is not None else DesktopState.INSPECTED
        message = (
            f"{len(units)} çeviri birimi hazır"
            if template is not None
            else f"Oyun modu: {inspection.mode.value}"
        )
        self._snapshot = DesktopSnapshot(state, inspection, template, units, message)
        return self._snapshot

    def load_template(self, template_path: Path) -> DesktopSnapshot:
        return self.load_templates((template_path,))

    def load_templates(self, template_paths: tuple[Path, ...]) -> DesktopSnapshot:
        if not template_paths:
            raise ValueError("En az bir Türkçe şablon gerekli")
        resolved = tuple(path.expanduser().resolve() for path in template_paths)
        units = tuple(unit for path in resolved for unit in parse_template(path))
        self._snapshot = DesktopSnapshot(
            DesktopState.READY,
            self._snapshot.game,
            resolved[0],
            units,
            f"{len(units)} çeviri birimi hazır",
        )
        return self._snapshot

    def set_state(self, state: DesktopState, message: str) -> DesktopSnapshot:
        self._snapshot = DesktopSnapshot(
            state,
            self._snapshot.game,
            self._snapshot.template_path,
            self._snapshot.units,
            message,
        )
        return self._snapshot
