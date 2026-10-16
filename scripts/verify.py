"""Run RenTR's local quality gate with one cross-platform command."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence

CHECKS: tuple[tuple[str, Sequence[str]], ...] = (
    ("Ruff", ("ruff", "check", ".")),
    ("Mypy", ("mypy",)),
    ("Pytest", ("pytest",)),
)


def main() -> int:
    for label, command in CHECKS:
        print(f"\n== {label} ==", flush=True)
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            print(f"\nDOĞRULAMA BAŞARISIZ: {label}", file=sys.stderr)
            return result.returncode

    print("\nDOĞRULAMA BAŞARILI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
