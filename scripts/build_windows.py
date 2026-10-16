"""Build the verified RenTR Windows CLI executable."""

from __future__ import annotations

from pathlib import Path

from rentr.packaging import execute_windows_build, plan_windows_build


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    output = execute_windows_build(plan_windows_build(project_root))
    print(f"Windows paketi hazır: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
