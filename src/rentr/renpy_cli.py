"""Safe, non-executing plans for the official Ren'Py translation CLI."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from rentr.scanner import GameInputMode, GameInspection
from rentr.workspace import WorkspacePlan

_LANGUAGE_PATTERN = re.compile(r"^[a-z]+(?:_[a-z]+)*$")


class RenPyCliError(ValueError):
    """Raised when an official Ren'Py CLI plan cannot be built safely."""


class TargetPlatform(StrEnum):
    """Supported official Ren'Py SDK launcher layouts."""

    WINDOWS = "windows"
    POSIX = "posix"


@dataclass(frozen=True, slots=True)
class RenPySdk:
    """A validated Ren'Py SDK launcher without executing it."""

    root: Path
    target_platform: TargetPlatform
    command_prefix: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TranslationCommandPlan:
    """Immutable dry-run plan for official translation template generation."""

    sdk_root: Path
    project_root: Path
    language: str
    cwd: Path
    args: tuple[str, ...]
    target_platform: TargetPlatform
    dry_run: bool = True
    execution_enabled: bool = False
    writes_to_original_game: bool = False


@dataclass(frozen=True, slots=True)
class TranslationCommandResult:
    """Captured result of an explicitly executed isolated SDK command."""

    args: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str
    generated_files: tuple[Path, ...]


def discover_renpy_sdk(sdk_root: Path, target_platform: TargetPlatform) -> RenPySdk:
    """Validate the documented SDK launcher layout without importing or running it."""
    resolved_root = sdk_root.expanduser().resolve()
    if not resolved_root.is_dir():
        raise RenPyCliError(f"Ren'Py SDK klasörü bulunamadı: {resolved_root}")

    required_files: tuple[Path, ...]
    command_prefix: tuple[str, ...]
    if target_platform is TargetPlatform.WINDOWS:
        launcher = resolved_root / "lib" / "py3-windows-x86_64" / "python.exe"
        renpy_entry = resolved_root / "renpy.py"
        required_files = (launcher, renpy_entry)
        command_prefix = (str(launcher), str(renpy_entry))
    else:
        launcher = resolved_root / "renpy.sh"
        required_files = (launcher,)
        command_prefix = (str(launcher),)

    missing = tuple(path for path in required_files if not path.is_file())
    if missing:
        missing_paths = ", ".join(str(path) for path in missing)
        raise RenPyCliError(f"Ren'Py SDK başlatıcısı eksik: {missing_paths}")

    return RenPySdk(
        root=resolved_root,
        target_platform=target_platform,
        command_prefix=command_prefix,
    )


def plan_translation_command(
    inspection: GameInspection,
    workspace: WorkspacePlan,
    sdk: RenPySdk,
    language: str = "turkish",
) -> TranslationCommandPlan:
    """Build a shell-free dry-run for ``translate <language>`` in an isolated copy."""
    if inspection.mode is not GameInputMode.SOURCE:
        raise RenPyCliError("Ren'Py çeviri şablonu yalnız kaynak oyun modunda planlanabilir")
    if workspace.game_root != inspection.selected_root.resolve():
        raise RenPyCliError("Çalışma alanı planı seçilen oyunla eşleşmiyor")
    if not _LANGUAGE_PATTERN.fullmatch(language):
        raise RenPyCliError(
            "Dil adı yalnız küçük ASCII harfler ve kelimeler arası alt çizgi içerebilir"
        )

    args = (*sdk.command_prefix, str(workspace.workspace_root), "translate", language)
    return TranslationCommandPlan(
        sdk_root=sdk.root,
        project_root=workspace.workspace_root,
        language=language,
        cwd=sdk.root,
        args=args,
        target_platform=sdk.target_platform,
    )


def execute_translation_command(
    plan: TranslationCommandPlan,
    *,
    timeout_seconds: float = 300.0,
) -> TranslationCommandResult:
    """Run the planned official command only against an existing isolated copy."""
    project_root = plan.project_root.resolve()
    if not project_root.is_dir() or not (project_root / "game").is_dir():
        raise RenPyCliError(f"Hazırlanmış izole proje bulunamadı: {project_root}")
    if plan.writes_to_original_game:
        raise RenPyCliError("Orijinal oyuna yazan komut çalıştırılamaz")
    if timeout_seconds <= 0:
        raise RenPyCliError("Komut zaman aşımı pozitif olmalı")
    if tuple(plan.args[-3:]) != (str(project_root), "translate", plan.language):
        raise RenPyCliError("Komut argümanları doğrulanmış çeviri planıyla uyuşmuyor")

    runtime_home = project_root / ".rentr-runtime-home"
    runtime_temp = project_root / ".rentr-runtime-temp"
    runtime_home.mkdir(exist_ok=True)
    runtime_temp.mkdir(exist_ok=True)
    environment = {
        key: value
        for key in ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR")
        if (value := os.environ.get(key)) is not None
    }
    environment.update(
        {
            "HOME": str(runtime_home),
            "USERPROFILE": str(runtime_home),
            "APPDATA": str(runtime_home / "AppData" / "Roaming"),
            "LOCALAPPDATA": str(runtime_home / "AppData" / "Local"),
            "TMP": str(runtime_temp),
            "TEMP": str(runtime_temp),
            "PYTHONNOUSERSITE": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    try:
        completed = subprocess.run(
            plan.args,
            cwd=plan.cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            env=environment,
        )
    except subprocess.TimeoutExpired as error:
        raise RenPyCliError(
            f"Ren'Py çeviri komutu zaman aşımına uğradı: {timeout_seconds}s"
        ) from error
    except OSError as error:
        raise RenPyCliError(f"Ren'Py çeviri komutu başlatılamadı: {error}") from error

    translation_dir = project_root / "game" / "tl" / plan.language
    generated = (
        tuple(sorted(translation_dir.rglob("*.rpy"))) if translation_dir.is_dir() else ()
    )
    if completed.returncode != 0:
        raise RenPyCliError(
            "Ren'Py çeviri komutu başarısız oldu "
            f"(kod={completed.returncode}): {completed.stderr.strip()}"
        )
    if not generated:
        raise RenPyCliError("Ren'Py komutu başarılı göründü ancak çeviri şablonu üretmedi")

    return TranslationCommandResult(
        args=plan.args,
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        generated_files=generated,
    )
