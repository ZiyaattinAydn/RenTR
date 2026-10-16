"""Local JSONL audit log that refuses secret-shaped fields."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path


class AuditLogError(ValueError):
    """Raised when an audit event could expose a secret or escape its workspace."""


_FORBIDDEN_KEYS = {"api_key", "authorization", "password", "secret", "token"}


class LocalAuditLog:
    def __init__(self, workspace_root: Path) -> None:
        root = workspace_root.expanduser().resolve()
        if not root.is_dir():
            raise AuditLogError(f"İzole çalışma alanı bulunamadı: {root}")
        self.path = root / ".rentr" / "logs" / "events.jsonl"

    def append(self, event: str, **fields: object) -> None:
        if not event.strip():
            raise AuditLogError("audit event adı boş olamaz")
        forbidden = _FORBIDDEN_KEYS.intersection(key.casefold() for key in fields)
        if forbidden:
            raise AuditLogError(f"Gizli audit alanı reddedildi: {sorted(forbidden)[0]}")
        record = {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "event": event,
            **fields,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise AuditLogError("Audit log sembolik bağlantı olamaz")
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
