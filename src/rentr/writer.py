"""Preview-first, preconditioned and atomic writes inside an isolated workspace."""

from __future__ import annotations

import difflib
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path


class SafeWriteError(ValueError):
    """Raised when an output cannot be written or rolled back safely."""


def _digest(content: bytes) -> str:
    return sha256(content).hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


@dataclass(frozen=True, slots=True)
class WritePlan:
    """Immutable dry-run bound to the exact current output state."""

    workspace_root: Path
    output_path: Path
    content: bytes
    content_hash: str
    original_exists: bool
    original_hash: str | None
    preview_diff: str


@dataclass(frozen=True, slots=True)
class WriteReceipt:
    """Evidence needed for a guarded rollback."""

    output_path: Path
    written_hash: str
    backup_path: Path | None
    created_new_file: bool


def plan_safe_write(
    output_path: Path,
    text: str,
    *,
    workspace_root: Path,
) -> WritePlan:
    """Create a diff and state precondition without modifying the filesystem."""
    root = workspace_root.expanduser().resolve()
    output = output_path.expanduser().resolve()
    if not root.is_dir():
        raise SafeWriteError(f"İzole çalışma alanı bulunamadı: {root}")
    if not _is_within(output, root):
        raise SafeWriteError("Çıktı izole çalışma alanının dışında olamaz")
    parent_is_symlink = any(
        parent.is_symlink() for parent in output.parents if parent != root
    )
    if output.is_symlink() or parent_is_symlink:
        raise SafeWriteError("Sembolik bağlantı üzerinden çıktı yazılamaz")

    content = text.encode("utf-8")
    original_exists = output.is_file()
    original = output.read_bytes() if original_exists else b""
    try:
        original_text = original.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SafeWriteError("Mevcut çıktı UTF-8 değil; üzerine yazılmayacak") from error
    preview = "".join(
        difflib.unified_diff(
            original_text.splitlines(keepends=True),
            text.splitlines(keepends=True),
            fromfile=str(output) if original_exists else "/dev/null",
            tofile=str(output),
        )
    )
    return WritePlan(
        workspace_root=root,
        output_path=output,
        content=content,
        content_hash=_digest(content),
        original_exists=original_exists,
        original_hash=_digest(original) if original_exists else None,
        preview_diff=preview,
    )


def _verify_precondition(plan: WritePlan) -> None:
    if plan.output_path.exists() != plan.original_exists:
        raise SafeWriteError("Çıktı dry-run sonrasında değişti; plan yeniden oluşturulmalı")
    original_changed = (
        not plan.output_path.is_file()
        or _digest(plan.output_path.read_bytes()) != plan.original_hash
    )
    if plan.original_exists and original_changed:
        raise SafeWriteError("Çıktı dry-run sonrasında değişti; üzerine yazılmadı")


def apply_safe_write(plan: WritePlan) -> WriteReceipt:
    """Apply one plan atomically after rechecking its exact precondition."""
    _verify_precondition(plan)
    output = plan.output_path
    output.parent.mkdir(parents=True, exist_ok=True)
    relative = output.relative_to(plan.workspace_root)
    backup: Path | None = None
    if plan.original_exists:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = plan.workspace_root / ".rentr-backups" / timestamp / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output, backup)

    partial = output.with_name(f".{output.name}.rentr-partial")
    if partial.exists():
        raise SafeWriteError(f"Eski yarım çıktı temizlenmeli: {partial}")
    try:
        with partial.open("xb") as handle:
            handle.write(plan.content)
            handle.flush()
            os.fsync(handle.fileno())
        partial.replace(output)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise

    if _digest(output.read_bytes()) != plan.content_hash:
        raise SafeWriteError("Atomik yazma sonrası çıktı özeti doğrulanamadı")
    return WriteReceipt(
        output_path=output,
        written_hash=plan.content_hash,
        backup_path=backup,
        created_new_file=not plan.original_exists,
    )


def rollback_safe_write(receipt: WriteReceipt) -> None:
    """Restore a receipt only if nobody changed the produced file afterward."""
    output = receipt.output_path
    if not output.is_file() or _digest(output.read_bytes()) != receipt.written_hash:
        raise SafeWriteError("Çıktı yazma sonrasında değişti; otomatik geri alma reddedildi")

    if receipt.created_new_file:
        output.unlink()
        return
    if receipt.backup_path is None or not receipt.backup_path.is_file():
        raise SafeWriteError("Geri alma yedeği bulunamadı")

    partial = output.with_name(f".{output.name}.rentr-rollback")
    if partial.exists():
        raise SafeWriteError(f"Eski geri alma dosyası temizlenmeli: {partial}")
    try:
        shutil.copy2(receipt.backup_path, partial)
        partial.replace(output)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
