import subprocess
from pathlib import Path
from typing import cast

import pytest

from rentr.renpy_cli import (
    RenPyCliError,
    TargetPlatform,
    discover_renpy_sdk,
    execute_translation_command,
    plan_translation_command,
)
from rentr.scanner import inspect_game
from rentr.workspace import plan_workspace, prepare_workspace

FIXTURES = Path(__file__).parent / "fixtures" / "games"
SOURCE_GAME = FIXTURES / "source_game"
PACKAGED_GAME = FIXTURES / "packaged_game"


def _windows_sdk(tmp_path: Path) -> Path:
    sdk = tmp_path / "renpy-sdk"
    launcher = sdk / "lib" / "py3-windows-x86_64" / "python.exe"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("fixture", encoding="utf-8")
    (sdk / "renpy.py").write_text("# fixture\n", encoding="utf-8")
    return sdk


def _posix_sdk(tmp_path: Path) -> Path:
    sdk = tmp_path / "renpy-sdk"
    sdk.mkdir()
    (sdk / "renpy.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    return sdk


def _successful_run_with_template(
    *args: object, **kwargs: object
) -> subprocess.CompletedProcess[str]:
    command = cast(tuple[str, ...], args[0])
    project_root = Path(command[-3])
    language = command[-1]
    translation = project_root / "game" / "tl" / language / "script.rpy"
    translation.parent.mkdir(parents=True, exist_ok=True)
    translation.write_text(
        'translate turkish strings:\n\n    old "Start"\n    new ""\n',
        encoding="utf-8",
    )
    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


def _successful_run_without_template(
    *args: object, **kwargs: object
) -> subprocess.CompletedProcess[str]:
    command = cast(tuple[str, ...], args[0])
    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


def test_discovers_documented_windows_launcher_without_execution(tmp_path: Path) -> None:
    sdk_root = _windows_sdk(tmp_path)

    sdk = discover_renpy_sdk(sdk_root, TargetPlatform.WINDOWS)

    assert sdk.command_prefix == (
        str((sdk_root / "lib" / "py3-windows-x86_64" / "python.exe").resolve()),
        str((sdk_root / "renpy.py").resolve()),
    )


def test_discovers_documented_posix_launcher_without_execution(tmp_path: Path) -> None:
    sdk_root = _posix_sdk(tmp_path)

    sdk = discover_renpy_sdk(sdk_root, TargetPlatform.POSIX)

    assert sdk.command_prefix == (str((sdk_root / "renpy.sh").resolve()),)


def test_rejects_incomplete_sdk_layout(tmp_path: Path) -> None:
    sdk_root = tmp_path / "renpy-sdk"
    sdk_root.mkdir()

    with pytest.raises(RenPyCliError, match="başlatıcısı eksik"):
        discover_renpy_sdk(sdk_root, TargetPlatform.WINDOWS)


def test_plans_shell_free_windows_translation_command(tmp_path: Path) -> None:
    inspection = inspect_game(SOURCE_GAME)
    workspace = plan_workspace(inspection, tmp_path / "isolated")
    sdk = discover_renpy_sdk(_windows_sdk(tmp_path), TargetPlatform.WINDOWS)

    plan = plan_translation_command(inspection, workspace, sdk)

    assert plan.args == (
        *sdk.command_prefix,
        str(workspace.workspace_root),
        "translate",
        "turkish",
    )
    assert plan.cwd == sdk.root
    assert plan.dry_run is True
    assert plan.execution_enabled is False
    assert plan.writes_to_original_game is False
    assert not workspace.workspace_root.exists()


@pytest.mark.parametrize("language", ["Turkish", "türkçe", "turkish;rm", "turkish__test"])
def test_rejects_unsafe_or_non_renpy_language_names(
    tmp_path: Path,
    language: str,
) -> None:
    inspection = inspect_game(SOURCE_GAME)
    workspace = plan_workspace(inspection, tmp_path / "isolated")
    sdk = discover_renpy_sdk(_posix_sdk(tmp_path), TargetPlatform.POSIX)

    with pytest.raises(RenPyCliError, match="Dil adı"):
        plan_translation_command(inspection, workspace, sdk, language)


def test_rejects_packaged_game_before_translation_generation(tmp_path: Path) -> None:
    inspection = inspect_game(PACKAGED_GAME)
    workspace = plan_workspace(inspection, tmp_path / "isolated")
    sdk = discover_renpy_sdk(_posix_sdk(tmp_path), TargetPlatform.POSIX)

    with pytest.raises(RenPyCliError, match="yalnız kaynak oyun"):
        plan_translation_command(inspection, workspace, sdk)


def test_executes_official_command_only_in_prepared_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inspection = inspect_game(SOURCE_GAME)
    workspace = plan_workspace(inspection, tmp_path / "isolated")
    prepare_workspace(workspace)
    sdk_root = _posix_sdk(tmp_path)
    launcher = sdk_root / "renpy.sh"
    launcher.write_text(
        "#!/bin/sh\n"
        'mkdir -p "$1/game/tl/$3"\n'
        'printf \'translate turkish strings:\\n\\n    old "Start"\\n    new ""\\n\' '
        '> "$1/game/tl/$3/script.rpy"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    sdk = discover_renpy_sdk(sdk_root, TargetPlatform.POSIX)
    plan = plan_translation_command(inspection, workspace, sdk)

    monkeypatch.setattr("rentr.renpy_cli.subprocess.run", _successful_run_with_template)

    result = execute_translation_command(plan)

    assert result.return_code == 0
    assert result.generated_files == (
        workspace.workspace_root / "game" / "tl" / "turkish" / "script.rpy",
    )


def test_rejects_success_without_generated_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inspection = inspect_game(SOURCE_GAME)
    workspace = plan_workspace(inspection, tmp_path / "isolated")
    prepare_workspace(workspace)
    sdk_root = _posix_sdk(tmp_path)
    launcher = sdk_root / "renpy.sh"
    launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    launcher.chmod(0o755)
    sdk = discover_renpy_sdk(sdk_root, TargetPlatform.POSIX)
    plan = plan_translation_command(inspection, workspace, sdk)

    monkeypatch.setattr("rentr.renpy_cli.subprocess.run", _successful_run_without_template)

    with pytest.raises(RenPyCliError, match="üretmedi"):
        execute_translation_command(plan)


def test_execution_environment_does_not_inherit_provider_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspection = inspect_game(SOURCE_GAME)
    workspace = plan_workspace(inspection, tmp_path / "isolated")
    prepare_workspace(workspace)
    sdk_root = _posix_sdk(tmp_path)
    launcher = sdk_root / "renpy.sh"
    launcher.write_text(
        "#!/bin/sh\n"
        'printf \'%s\' "${RENTR_API_KEY-unset}" > "$1/inherited-secret.txt"\n'
        'mkdir -p "$1/game/tl/$3"\n'
        'printf \'translate turkish strings:\\n\\n    old "Start"\\n    new ""\\n\' '
        '> "$1/game/tl/$3/script.rpy"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    monkeypatch.setenv("RENTR_API_KEY", "must-not-leak")
    sdk = discover_renpy_sdk(sdk_root, TargetPlatform.POSIX)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        (workspace.workspace_root / "inherited-secret.txt").write_text(
            str(environment.get("RENTR_API_KEY", "unset")),
            encoding="utf-8",
        )
        return _successful_run_with_template(*args, **kwargs)

    monkeypatch.setattr("rentr.renpy_cli.subprocess.run", fake_run)

    execute_translation_command(plan_translation_command(inspection, workspace, sdk))

    assert (workspace.workspace_root / "inherited-secret.txt").read_text() == "unset"
