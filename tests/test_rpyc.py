from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from rentr.rpyc import RpycError, RpycFormat, inspect_rpyc


def _write_rpc2(path: Path, payload: bytes = b"payload") -> None:
    header = b"RENPY RPC2"
    table_size = struct.calcsize("<III") * 2
    offset = len(header) + table_size
    path.write_bytes(
        header
        + struct.pack("<III", 1, offset, len(payload))
        + struct.pack("<III", 0, 0, 0)
        + payload
    )


def test_preflights_rpc2_sections_without_unpickling(tmp_path: Path) -> None:
    path = tmp_path / "script.rpyc"
    _write_rpc2(path)

    inspection = inspect_rpyc(path)

    assert inspection.format is RpycFormat.RPC2
    assert inspection.sections[0].slot == 1
    assert inspection.safe_to_unpickle is False


def test_identifies_legacy_zlib_without_decompressing(tmp_path: Path) -> None:
    path = tmp_path / "legacy.rpyc"
    path.write_bytes(zlib.compress(b"untrusted pickle bytes"))

    assert inspect_rpyc(path).format is RpycFormat.LEGACY_ZLIB


def test_rejects_out_of_bounds_rpc2_section(tmp_path: Path) -> None:
    path = tmp_path / "bad.rpyc"
    path.write_bytes(
        b"RENPY RPC2"
        + struct.pack("<III", 1, 9999, 10)
        + struct.pack("<III", 0, 0, 0)
    )

    with pytest.raises(RpycError, match="aralığı"):
        inspect_rpyc(path)
