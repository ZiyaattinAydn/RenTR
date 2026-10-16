"""Evidence-based Ren'Py runtime generation detection."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class RenPyGeneration(StrEnum):
    RENPY_6_7 = "renpy-6-7"
    RENPY_8 = "renpy-8"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RuntimeDetection:
    generation: RenPyGeneration
    version: str | None
    evidence: tuple[str, ...]


_VERSION = re.compile(r"^(?P<major>[0-9]+)(?:\.[0-9]+){1,3}")


def detect_runtime(selected_root: Path) -> RuntimeDetection:
    resolved = selected_root.expanduser().resolve()
    base = resolved.parent if resolved.name.casefold() == "game" else resolved
    evidence: list[str] = []
    version: str | None = None
    build_info = base / "game" / "cache" / "build_info.json"
    if build_info.is_file() and not build_info.is_symlink():
        try:
            payload = json.loads(build_info.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict):
            raw_version = payload.get("version") or payload.get("renpy_version")
            if isinstance(raw_version, str):
                version = raw_version
                evidence.append(f"build_info:{raw_version}")

    lib_dir = base / "lib"
    library_names = (
        tuple(path.name.casefold() for path in lib_dir.iterdir())
        if lib_dir.is_dir()
        else ()
    )
    has_py3 = any(name.startswith("py3-") for name in library_names)
    has_py2 = any(name.startswith("py2-") for name in library_names)
    if has_py3:
        evidence.append("lib:py3")
    if has_py2:
        evidence.append("lib:py2")

    generation = RenPyGeneration.UNKNOWN
    if version is not None and (match := _VERSION.match(version)) is not None:
        major = int(match.group("major"))
        if major >= 8:
            generation = RenPyGeneration.RENPY_8
        elif major in {6, 7}:
            generation = RenPyGeneration.RENPY_6_7
    elif has_py3 and not has_py2:
        generation = RenPyGeneration.RENPY_8
    elif has_py2 and not has_py3:
        generation = RenPyGeneration.RENPY_6_7
    return RuntimeDetection(generation, version, tuple(evidence))
