"""Selective and atomic working-copy preparation for inspected games."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from rentr.scanner import GameInspection

_MINIMUM_WORKSPACE_BYTES = 16 * 1024 * 1024


class WorkspaceError(ValueError):
    """Raised when an isolated workspace cannot be prepared safely."""


@dataclass(frozen=True, slots=True)
class PlannedFile:
    """One immutable source-to-workspace copy operation."""

    source: Path
    relative_destination: Path
    size_bytes: int


@dataclass(frozen=True, slots=True)
class WorkspacePlan:
    """Dry-run result for a selective working copy."""

    game_root: Path
    workspace_root: Path
    files: tuple[PlannedFile, ...]
    source_bytes: int
    required_free_bytes: int
    available_free_bytes: int


def _is_within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path
    while not candidate.exists():
        if candidate == candidate.parent:
            raise WorkspaceError(f"Çalışma alanı için erişilebilir üst klasör yok: {path}")
        candidate = candidate.parent
    if not candidate.is_dir():
        raise WorkspaceError(f"Çalışma alanı üst yolu klasör değil: {candidate}")
    return candidate


def _selected_artifacts(inspection: GameInspection) -> tuple[Path, ...]:
    candidates = (
        *inspection.source_scripts,
        *inspection.compiled_scripts,
        *inspection.archives,
        *inspection.translation_files,
    )
    return tuple(sorted(set(candidates)))


def plan_workspace(inspection: GameInspection, workspace_root: Path) -> WorkspacePlan:
    """Plan a script-only copy and reject overlapping or undersized destinations."""
    resolved_workspace = workspace_root.expanduser().resolve()
    game_root = inspection.selected_root.resolve()

    if _is_within(resolved_workspace, game_root) or _is_within(game_root, resolved_workspace):
        raise WorkspaceError("Çalışma alanı orijinal oyun klasörüyle kesişemez")

    artifacts = _selected_artifacts(inspection)
    if not artifacts:
        raise WorkspaceError("Çalışma alanına alınacak desteklenen oyun dosyası bulunamadı")

    planned_files = tuple(
        PlannedFile(
            source=source,
            relative_destination=Path("game") / source.relative_to(inspection.game_dir),
            size_bytes=source.stat().st_size,
        )
        for source in artifacts
    )
    source_bytes = sum(item.size_bytes for item in planned_files)
    required_free_bytes = max(source_bytes * 2, _MINIMUM_WORKSPACE_BYTES)
    disk_root = _nearest_existing_parent(resolved_workspace.parent)
    available_free_bytes = shutil.disk_usage(disk_root).free

    if available_free_bytes < required_free_bytes:
        raise WorkspaceError(
            "Çalışma alanı için yeterli boş disk yok: "
            f"gerekli={required_free_bytes}, kullanılabilir={available_free_bytes}"
        )

    return WorkspacePlan(
        game_root=game_root,
        workspace_root=resolved_workspace,
        files=planned_files,
        source_bytes=source_bytes,
        required_free_bytes=required_free_bytes,
        available_free_bytes=available_free_bytes,
    )


def prepare_workspace(plan: WorkspacePlan) -> Path:
    """Copy planned artifacts through a temporary directory and publish atomically."""
    destination = plan.workspace_root
    partial = destination.with_name(f"{destination.name}.partial")

    if destination.exists():
        raise WorkspaceError(f"Çalışma alanı zaten mevcut: {destination}")
    if partial.exists():
        raise WorkspaceError(f"Yarım çalışma alanı temizlenmeli: {partial}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial.mkdir()
    try:
        for item in plan.files:
            target = partial / item.relative_destination
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.source, target)
        partial.replace(destination)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise

    return destination
