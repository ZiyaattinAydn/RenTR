from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest

from rentr.scanner import inspect_game
from rentr.workspace import WorkspaceError, plan_workspace, prepare_workspace

GAMES = Path(__file__).parent / "fixtures" / "games"


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_plan_selects_scripts_and_archives_but_not_media(tmp_path: Path) -> None:
    inspection = inspect_game(GAMES / "packaged_game")

    plan = plan_workspace(inspection, tmp_path / "workspace")

    relative_files = {item.relative_destination.as_posix() for item in plan.files}
    assert relative_files == {"game/archive.rpa", "game/script.rpyc"}
    assert all("background.png" not in item for item in relative_files)
    assert plan.required_free_bytes >= plan.source_bytes * 2


def test_workspace_cannot_overlap_original_game() -> None:
    game_root = GAMES / "packaged_game"
    inspection = inspect_game(game_root)

    with pytest.raises(WorkspaceError, match="kesişemez"):
        plan_workspace(inspection, game_root / "rentr-work")


def test_prepare_workspace_copies_selectively_and_keeps_original_unchanged(
    tmp_path: Path,
) -> None:
    inspection = inspect_game(GAMES / "packaged_game")
    original = inspection.game_dir / "script.rpyc"
    digest_before = _digest(original)
    plan = plan_workspace(inspection, tmp_path / "workspace")

    destination = prepare_workspace(plan)

    assert (destination / "game" / "script.rpyc").is_file()
    assert (destination / "game" / "archive.rpa").is_file()
    assert not (destination / "game" / "background.png").exists()
    assert _digest(original) == digest_before


def test_prepare_workspace_refuses_existing_destination(tmp_path: Path) -> None:
    inspection = inspect_game(GAMES / "source_game")
    destination = tmp_path / "workspace"
    plan = plan_workspace(inspection, destination)
    destination.mkdir()

    with pytest.raises(WorkspaceError, match="zaten mevcut"):
        prepare_workspace(plan)


def test_copy_failure_removes_partial_workspace(tmp_path: Path) -> None:
    inspection = inspect_game(GAMES / "packaged_game")
    destination = tmp_path / "workspace"
    plan = plan_workspace(inspection, destination)

    with (
        patch("rentr.workspace.shutil.copy2", side_effect=OSError("copy failed")),
        pytest.raises(OSError, match="copy failed"),
    ):
        prepare_workspace(plan)

    assert not destination.exists()
    assert not destination.with_name("workspace.partial").exists()
