from __future__ import annotations

import pickle
import struct
import zlib
from hashlib import sha256
from pathlib import Path

import pytest

from rentr.packaged import plan_packaged_translation_command, prepare_packaged_game
from rentr.renpy_cli import TargetPlatform, discover_renpy_sdk
from rentr.rpyc import RpycFormat
from rentr.versioning import RenPyGeneration


def _rpc2() -> bytes:
    payload = b"opaque-pickle-section"
    header = b"RENPY RPC2"
    offset = len(header) + struct.calcsize("<III") * 2
    return (
        header
        + struct.pack("<III", 1, offset, len(payload))
        + struct.pack("<III", 0, 0, 0)
        + payload
    )


def _rpa(path: Path, files: dict[str, bytes]) -> None:
    key = 0x12345678
    header_size = len(b"RPA-3.0 0000000000000000 00000000\n")
    content = bytearray(b"\x00" * header_size)
    index: dict[str, list[tuple[int, int]]] = {}
    for name, data in files.items():
        offset = len(content)
        content.extend(data)
        index[name] = [(offset ^ key, len(data) ^ key)]
    index_offset = len(content)
    content[:header_size] = f"RPA-3.0 {index_offset:016x} {key:08x}\n".encode()
    content.extend(zlib.compress(pickle.dumps(index, protocol=2)))
    path.write_bytes(content)


def test_prepares_rpyc_only_game_without_loading_compiled_pickle(tmp_path: Path) -> None:
    game_root = tmp_path / "PackagedGame"
    game_dir = game_root / "game"
    game_dir.mkdir(parents=True)
    archive = game_dir / "scripts.rpa"
    _rpa(archive, {"story/script.rpyc": _rpc2(), "images/bg.png": b"PNG"})
    original_hash = sha256(archive.read_bytes()).hexdigest()
    workspace = tmp_path / "workspace"

    prepared = prepare_packaged_game(game_root, workspace)

    assert prepared.needs_compiled_backend
    compiled = [
        path.relative_to(workspace / "game").as_posix()
        for path in prepared.compiled_scripts
    ]
    assert compiled == ["story/script.rpyc"]
    assert prepared.compiled_inspections[0].format is RpycFormat.RPC2
    assert not (workspace / "game" / "images" / "bg.png").exists()
    assert sha256(archive.read_bytes()).hexdigest() == original_hash


def test_prepares_archived_source_without_compiled_backend(tmp_path: Path) -> None:
    game_root = tmp_path / "PackagedSourceGame"
    game_dir = game_root / "game"
    game_dir.mkdir(parents=True)
    _rpa(game_dir / "scripts.rpa", {"script.rpy": b'label start:\n    "Hello"\n'})

    prepared = prepare_packaged_game(game_root, tmp_path / "workspace")

    assert not prepared.needs_compiled_backend
    assert prepared.source_scripts[0].read_text(encoding="utf-8").startswith("label start")



def test_packaged_preparation_skips_media_only_rpa_copy(tmp_path: Path) -> None:
    game_root = tmp_path / "MixedArchives"
    game_dir = game_root / "game"
    game_dir.mkdir(parents=True)
    _rpa(game_dir / "scripts.rpa", {"story/script.rpy": b'label start:\n    "Hello"\n'})
    _rpa(game_dir / "images.rpa", {"images/bg.webp": b"WEBP" * 1024})

    prepared = prepare_packaged_game(game_root, tmp_path / "workspace")

    assert [path.name for path in prepared.archives] == ["scripts.rpa"]
    assert (prepared.workspace_root / "game" / "scripts.rpa").is_file()
    assert not (prepared.workspace_root / "game" / "images.rpa").exists()
    assert (prepared.workspace_root / "game" / "story" / "script.rpy").is_file()

def test_plans_official_sdk_only_after_packaged_workspace_exists(tmp_path: Path) -> None:
    game_root = tmp_path / "Packaged"
    game_dir = game_root / "game"
    game_dir.mkdir(parents=True)
    _rpa(game_dir / "scripts.rpa", {"script.rpyc": _rpc2()})
    prepared = prepare_packaged_game(game_root, tmp_path / "workspace")
    sdk_root = tmp_path / "sdk"
    sdk_root.mkdir()
    launcher = sdk_root / "renpy.sh"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    sdk = discover_renpy_sdk(sdk_root, TargetPlatform.POSIX)

    plan = plan_packaged_translation_command(prepared, sdk)

    assert plan.execution_enabled is True
    assert plan.writes_to_original_game is False
    assert plan.args[-3:] == (str(prepared.workspace_root), "translate", "turkish")


@pytest.mark.parametrize(
    ("library_dir", "generation"),
    [
        ("py2-windows-i686", RenPyGeneration.RENPY_6_7),
        ("py3-windows-x86_64", RenPyGeneration.RENPY_8),
    ],
)
def test_packaged_matrix_prepares_renpy_7_and_8_in_isolation(
    tmp_path: Path,
    library_dir: str,
    generation: RenPyGeneration,
) -> None:
    game_root = tmp_path / generation.value
    game_dir = game_root / "game"
    game_dir.mkdir(parents=True)
    (game_root / "lib" / library_dir).mkdir(parents=True)
    _rpa(game_dir / "scripts.rpa", {"story/script.rpyc": _rpc2()})

    prepared = prepare_packaged_game(game_root, tmp_path / f"workspace-{generation.value}")

    assert prepared.runtime.generation is generation
    assert prepared.original_game_root == game_root.resolve()
    assert prepared.compiled_scripts[0].is_relative_to(prepared.workspace_root)
    assert not (game_root / "game" / "story" / "script.rpyc").exists()
