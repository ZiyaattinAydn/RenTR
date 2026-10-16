from __future__ import annotations

from pathlib import Path

import pytest

from rentr.packaging import PackagingError, plan_desktop_windows_build, plan_windows_build

PROJECT_ROOT = Path(__file__).parents[1]


def test_plans_shell_free_windows_onefile_build() -> None:
    python = Path("C:/Python312/python.exe")

    plan = plan_windows_build(
        PROJECT_ROOT,
        python_executable=python,
        host_system="Windows",
    )

    assert plan.args[0] == str(python.resolve())
    assert plan.args[1:3] == ("-m", "PyInstaller")
    assert "--onefile" in plan.args
    assert plan.output_executable == PROJECT_ROOT / "dist" / "windows" / "RenTR.exe"


def test_refuses_cross_platform_windows_executable_build() -> None:
    with pytest.raises(PackagingError, match="yalnız Windows"):
        plan_windows_build(PROJECT_ROOT, host_system="Linux")


def test_rejects_non_project_root(tmp_path: Path) -> None:
    with pytest.raises(PackagingError, match="geçersiz"):
        plan_windows_build(tmp_path, host_system="Windows")


def test_plans_official_pyside6_desktop_deployment() -> None:
    deploy = Path("C:/RenTR/.venv/Scripts/pyside6-deploy.exe")

    plan = plan_desktop_windows_build(
        PROJECT_ROOT,
        deploy_executable=deploy,
        host_system="Windows",
    )

    assert plan.args[0] == str(deploy.resolve())
    assert plan.args[1:7] == (
        "--name",
        "RenTR",
        "--mode",
        "onefile",
        "--force",
        "--keep-deployment-files",
    )
    assert plan.output_executable == PROJECT_ROOT / "RenTR.exe"
