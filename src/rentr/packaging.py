"""Deterministic Windows CLI packaging plan for PyInstaller."""

from __future__ import annotations

import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class PackagingError(ValueError):
    """Raised when a reproducible package cannot be planned or verified."""


@dataclass(frozen=True, slots=True)
class WindowsBuildPlan:
    project_root: Path
    args: tuple[str, ...]
    cwd: Path
    output_executable: Path


@dataclass(frozen=True, slots=True)
class DesktopBuildPlan:
    project_root: Path
    args: tuple[str, ...]
    cwd: Path
    output_executable: Path


def plan_windows_build(
    project_root: Path,
    *,
    python_executable: Path | None = None,
    host_system: str | None = None,
) -> WindowsBuildPlan:
    """Build a shell-free one-file CLI packaging command."""
    root = project_root.expanduser().resolve()
    if not (root / "pyproject.toml").is_file() or not (root / "src" / "rentr").is_dir():
        raise PackagingError(f"RenTR proje kökü geçersiz: {root}")
    system = host_system or platform.system()
    if system != "Windows":
        raise PackagingError("Windows .exe paketi yalnız Windows üzerinde üretilebilir")
    python = (python_executable or Path(sys.executable)).expanduser().resolve()
    dist = root / "dist" / "windows"
    work = root / "build" / "pyinstaller"
    specs = root / "build" / "specs"
    args = (
        str(python),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "RenTR",
        "--paths",
        str(root / "src"),
        "--distpath",
        str(dist),
        "--workpath",
        str(work),
        "--specpath",
        str(specs),
        str(root / "src" / "rentr" / "__main__.py"),
    )
    return WindowsBuildPlan(
        project_root=root,
        args=args,
        cwd=root,
        output_executable=dist / "RenTR.exe",
    )


def execute_windows_build(
    plan: WindowsBuildPlan,
    *,
    timeout_seconds: float = 900.0,
) -> Path:
    """Execute a reviewed plan and require the expected executable."""
    if timeout_seconds <= 0:
        raise PackagingError("Paketleme zaman aşımı pozitif olmalı")
    try:
        result = subprocess.run(
            plan.args,
            cwd=plan.cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PackagingError(f"Windows paketleme başlatılamadı: {error}") from error
    if result.returncode != 0:
        raise PackagingError(
            f"Windows paketleme başarısız (kod={result.returncode}): {result.stderr.strip()}"
        )
    if not plan.output_executable.is_file():
        raise PackagingError("Paketleme başarılı göründü ancak RenTR.exe üretilmedi")
    return plan.output_executable


def plan_desktop_windows_build(
    project_root: Path,
    *,
    deploy_executable: Path,
    host_system: str | None = None,
) -> DesktopBuildPlan:
    """Plan the official pyside6-deploy one-file Windows GUI build."""
    root = project_root.expanduser().resolve()
    main_file = root / "src" / "rentr" / "desktop" / "app.py"
    if not main_file.is_file():
        raise PackagingError(f"RenTR masaüstü giriş dosyası bulunamadı: {main_file}")
    if (host_system or platform.system()) != "Windows":
        raise PackagingError("Windows masaüstü paketi yalnız Windows üzerinde üretilebilir")
    executable = deploy_executable.expanduser().resolve()
    args = (
        str(executable),
        "--name",
        "RenTR",
        "--mode",
        "onefile",
        "--force",
        "--keep-deployment-files",
        str(main_file),
    )
    return DesktopBuildPlan(
        project_root=root,
        args=args,
        cwd=root,
        output_executable=root / "RenTR.exe",
    )


def execute_desktop_build(
    plan: DesktopBuildPlan,
    *,
    timeout_seconds: float = 1800.0,
) -> Path:
    if timeout_seconds <= 0:
        raise PackagingError("Masaüstü paketleme zaman aşımı pozitif olmalı")
    try:
        result = subprocess.run(
            plan.args,
            cwd=plan.cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PackagingError(f"Masaüstü paketleme başlatılamadı: {error}") from error
    if result.returncode != 0:
        raise PackagingError(
            f"Masaüstü paketleme başarısız (kod={result.returncode}): {result.stderr.strip()}"
        )
    if not plan.output_executable.is_file():
        raise PackagingError("Paketleme başarılı göründü ancak RenTR.exe üretilmedi")
    return plan.output_executable
