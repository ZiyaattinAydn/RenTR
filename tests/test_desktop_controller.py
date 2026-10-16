from __future__ import annotations

from pathlib import Path

from rentr.desktop.controller import DesktopController, DesktopState

GAMES = Path(__file__).parent / "fixtures" / "games"


def test_controller_inspects_source_without_requiring_turkish_folder() -> None:
    snapshot = DesktopController().inspect(GAMES / "source_game")

    assert snapshot.state is DesktopState.INSPECTED
    assert snapshot.game is not None
    assert snapshot.game.mode.value == "source"
    assert snapshot.units == ()


def test_controller_loads_resume_translation_on_same_screen() -> None:
    snapshot = DesktopController().inspect(GAMES / "resume_game")

    assert snapshot.state is DesktopState.READY
    assert snapshot.template_path is not None
    assert len(snapshot.units) == 1
