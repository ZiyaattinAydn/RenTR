from __future__ import annotations

import os
import pickle
import zlib
from pathlib import Path

import pytest

from rentr.rpa import RpaError, extract_scripts, inspect_rpa, plan_script_extraction


def _write_rpa(path: Path, files: dict[str, bytes], *, key: int = 0xA1B2C3D4) -> None:
    header_length = len(b"RPA-3.0 0000000000000000 00000000\n")
    data = bytearray(b"\x00" * header_length)
    raw_index: dict[bytes, list[tuple[int, int, bytes]]] = {}
    for name, content in files.items():
        prefix = b"Made with Ren'Py."
        offset = len(data)
        data.extend(content)
        raw_index[name.encode()] = [(offset ^ key, len(content) ^ key, prefix)]
    index_offset = len(data)
    compressed = zlib.compress(pickle.dumps(raw_index, protocol=2))
    header = f"RPA-3.0 {index_offset:016x} {key:08x}\n".encode()
    data[:header_length] = header
    data.extend(compressed)
    path.write_bytes(data)


def test_lists_and_extracts_only_scripts_inside_workspace(tmp_path: Path) -> None:
    archive_path = tmp_path / "scripts.rpa"
    _write_rpa(
        archive_path,
        {
            "script.rpyc": b"compiled",
            "sub/story.rpy": b'label start:\n    "Hello"\n',
            "images/bg.png": b"PNG",
        },
    )
    workspace = tmp_path / "workspace"
    game_dir = workspace / "game"
    game_dir.mkdir(parents=True)

    archive = inspect_rpa(archive_path)
    plan = plan_script_extraction(archive, game_dir, workspace_root=workspace)
    receipt = extract_scripts(plan)

    assert archive.version == "RPA-3.0"
    assert [member.archive_name for member in plan.members] == ["script.rpyc", "sub/story.rpy"]
    assert [path.relative_to(game_dir).as_posix() for path in receipt.extracted_files] == [
        "script.rpyc",
        "sub/story.rpy",
    ]
    assert (game_dir / "script.rpyc").read_bytes() == b"Made with Ren'Py.compiled"
    assert not (game_dir / "images" / "bg.png").exists()


def test_rejects_path_traversal_before_extraction(tmp_path: Path) -> None:
    archive_path = tmp_path / "bad.rpa"
    _write_rpa(archive_path, {"../escape.rpy": b"bad"})

    with pytest.raises(RpaError, match="dışına"):
        inspect_rpa(archive_path)

    assert not (tmp_path / "escape.rpy").exists()


class _Exploit:
    def __reduce__(self) -> tuple[object, tuple[str]]:
        return os.system, ("touch SHOULD_NOT_EXIST",)


def test_restricted_unpickler_rejects_executable_global(tmp_path: Path) -> None:
    archive_path = tmp_path / "malicious.rpa"
    header_length = len(b"RPA-3.0 0000000000000000 00000000\n")
    index_offset = header_length
    header = f"RPA-3.0 {index_offset:016x} {0:08x}\n".encode()
    archive_path.write_bytes(header + zlib.compress(pickle.dumps(_Exploit(), protocol=2)))

    with pytest.raises(RpaError, match="globali reddedildi"):
        inspect_rpa(archive_path)

    assert not (Path.cwd() / "SHOULD_NOT_EXIST").exists()


def test_rejects_unsupported_or_truncated_archive(tmp_path: Path) -> None:
    archive = tmp_path / "archive.rpa"
    archive.write_bytes(b"RPA-4.0 0000000000000000 00000000\n")

    with pytest.raises(RpaError, match="Desteklenmeyen"):
        inspect_rpa(archive)


def test_rejects_destination_outside_workspace(tmp_path: Path) -> None:
    archive_path = tmp_path / "scripts.rpa"
    _write_rpa(archive_path, {"script.rpyc": b"compiled"})
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(RpaError, match="içinde"):
        plan_script_extraction(
            inspect_rpa(archive_path),
            tmp_path / "outside",
            workspace_root=workspace,
        )
