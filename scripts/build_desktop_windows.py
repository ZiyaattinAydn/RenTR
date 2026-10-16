"""Build the one-file RenTR PySide6 Windows desktop application."""

from __future__ import annotations

import shutil
from pathlib import Path

from rentr.packaging import execute_desktop_build, plan_desktop_windows_build


def main() -> int:
    deploy = shutil.which("pyside6-deploy")
    if deploy is None:
        raise SystemExit("pyside6-deploy bulunamadı; önce: uv sync --group desktop")
    project_root = Path(__file__).resolve().parents[1]
    plan = plan_desktop_windows_build(project_root, deploy_executable=Path(deploy))
    output = execute_desktop_build(plan)
    print(f"Windows masaüstü paketi hazır: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
