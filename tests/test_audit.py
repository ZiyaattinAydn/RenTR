from __future__ import annotations

import json
from pathlib import Path

import pytest

from rentr.audit import AuditLogError, LocalAuditLog


def test_appends_local_structured_events(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log = LocalAuditLog(workspace)

    log.append("translation.completed", unit_count=3, failed_count=0)

    record = json.loads(log.path.read_text(encoding="utf-8"))
    assert record["event"] == "translation.completed"
    assert record["unit_count"] == 3
    assert record["failed_count"] == 0


@pytest.mark.parametrize("field", ["api_key", "authorization", "password", "token"])
def test_rejects_secret_shaped_fields(tmp_path: Path, field: str) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log = LocalAuditLog(workspace)

    with pytest.raises(AuditLogError, match="Gizli"):
        log.append("bad", **{field: "sensitive"})
