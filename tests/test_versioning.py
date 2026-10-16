from __future__ import annotations

import json
from pathlib import Path

from rentr.versioning import RenPyGeneration, detect_runtime


def test_detects_renpy_8_from_build_info(tmp_path: Path) -> None:
    cache = tmp_path / "game" / "cache"
    cache.mkdir(parents=True)
    (cache / "build_info.json").write_text(json.dumps({"version": "8.4.1"}), encoding="utf-8")

    detection = detect_runtime(tmp_path)

    assert detection.generation is RenPyGeneration.RENPY_8
    assert detection.version == "8.4.1"


def test_detects_renpy_7_from_python2_runtime_layout(tmp_path: Path) -> None:
    (tmp_path / "lib" / "py2-windows-i686").mkdir(parents=True)

    assert detect_runtime(tmp_path).generation is RenPyGeneration.RENPY_6_7


def test_unknown_runtime_fails_to_claim_a_version(tmp_path: Path) -> None:
    detection = detect_runtime(tmp_path)

    assert detection.generation is RenPyGeneration.UNKNOWN
    assert detection.version is None
