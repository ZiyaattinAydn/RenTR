from pathlib import Path

import pytest

from rentr.scanner import GameInputMode, GameInspectionError, inspect_game

GAMES = Path(__file__).parent / "fixtures" / "games"


def test_source_game_does_not_require_existing_tl_directory() -> None:
    inspection = inspect_game(GAMES / "source_game")

    assert inspection.mode is GameInputMode.SOURCE
    assert len(inspection.source_scripts) == 1
    assert inspection.translation_files == ()
    assert inspection.translation_dir == GAMES / "source_game" / "game" / "tl" / "turkish"
    assert inspection.next_action == "generate_translation_templates"


def test_packaged_game_routes_to_isolated_extraction() -> None:
    inspection = inspect_game(GAMES / "packaged_game")

    assert inspection.mode is GameInputMode.PACKAGED
    assert inspection.source_scripts == ()
    assert len(inspection.compiled_scripts) == 1
    assert len(inspection.archives) == 1
    assert inspection.next_action == "prepare_isolated_extraction"


def test_existing_translation_is_resume_mode_not_required_input() -> None:
    inspection = inspect_game(GAMES / "resume_game")

    assert inspection.mode is GameInputMode.RESUME
    assert len(inspection.translation_files) == 1
    assert inspection.next_action == "inventory_existing_translation"


def test_game_directory_can_be_selected_directly() -> None:
    game_dir = GAMES / "source_game" / "game"

    inspection = inspect_game(game_dir)

    assert inspection.game_dir == game_dir.resolve()
    assert inspection.mode is GameInputMode.SOURCE


def test_non_game_folder_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(GameInspectionError, match="game dizini bulunamadı"):
        inspect_game(tmp_path)
