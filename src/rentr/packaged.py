"""Prepare packaged Ren'Py script artifacts in an isolated workspace."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from rentr.renpy_cli import RenPySdk, TranslationCommandPlan
from rentr.rpa import extract_scripts, inspect_rpa, plan_script_extraction
from rentr.rpyc import RpycInspection, inspect_rpyc
from rentr.scanner import GameInputMode, inspect_game
from rentr.versioning import RuntimeDetection, detect_runtime
from rentr.workspace import plan_workspace, prepare_workspace


class PackagedGameError(ValueError):
    """Raised when packaged scripts cannot be prepared without unsafe behavior."""


@dataclass(frozen=True, slots=True)
class PackagedPreparation:
    original_game_root: Path
    workspace_root: Path
    runtime: RuntimeDetection
    archives: tuple[Path, ...]
    source_scripts: tuple[Path, ...]
    compiled_scripts: tuple[Path, ...]
    compiled_inspections: tuple[RpycInspection, ...]

    @property
    def needs_compiled_backend(self) -> bool:
        return not self.source_scripts and bool(self.compiled_scripts)


_LANGUAGE = re.compile(r"^[a-z]+(?:_[a-z]+)*$")
_SCRIPT_SUFFIXES = {".rpy", ".rpyc", ".rpym", ".rpymc"}


def prepare_packaged_game(
    game_root: Path,
    workspace_root: Path,
) -> PackagedPreparation:
    """Copy and statically extract standard RPA scripts; never load an RPYC pickle."""
    inspection = inspect_game(game_root)
    if inspection.mode is not GameInputMode.PACKAGED:
        raise PackagedGameError("Paketli hazırlık yalnız packaged oyun modunda kullanılabilir")
    runtime = detect_runtime(inspection.selected_root)
    script_archives: list[Path] = []
    for archive_path in inspection.archives:
        archive = inspect_rpa(archive_path)
        if any(
            member.relative_path.suffix.casefold() in _SCRIPT_SUFFIXES
            for member in archive.members
        ):
            script_archives.append(archive_path)
    workspace_inspection = replace(inspection, archives=tuple(script_archives))
    workspace_plan = plan_workspace(workspace_inspection, workspace_root)
    workspace = prepare_workspace(workspace_plan)
    workspace_game = workspace / "game"
    workspace_archives = tuple(
        workspace_game / archive.relative_to(inspection.game_dir)
        for archive in workspace_inspection.archives
    )
    for archive_path in sorted(workspace_archives, reverse=True):
        archive = inspect_rpa(archive_path)
        plan = plan_script_extraction(
            archive,
            workspace_game,
            workspace_root=workspace,
        )
        extract_scripts(plan)

    source_scripts = tuple(sorted(workspace_game.rglob("*.rpy")))
    compiled_scripts = tuple(sorted(workspace_game.rglob("*.rpyc")))
    if not source_scripts and not compiled_scripts:
        raise PackagedGameError("Paketli oyundan çevrilebilir script çıkarılamadı")
    compiled_inspections = tuple(inspect_rpyc(path) for path in compiled_scripts)
    return PackagedPreparation(
        original_game_root=inspection.selected_root,
        workspace_root=workspace,
        runtime=runtime,
        archives=workspace_archives,
        source_scripts=source_scripts,
        compiled_scripts=compiled_scripts,
        compiled_inspections=compiled_inspections,
    )


def plan_packaged_translation_command(
    prepared: PackagedPreparation,
    sdk: RenPySdk,
    *,
    language: str = "turkish",
) -> TranslationCommandPlan:
    """Plan official template generation only after static isolated preparation."""
    workspace = prepared.workspace_root.resolve()
    original = prepared.original_game_root.resolve()
    if workspace == original or workspace in original.parents or original in workspace.parents:
        raise PackagedGameError("Paketli çalışma alanı orijinal oyunla kesişemez")
    if not workspace.is_dir() or not (workspace / "game").is_dir():
        raise PackagedGameError("Hazırlanmış paketli çalışma alanı bulunamadı")
    if not prepared.source_scripts and not prepared.compiled_scripts:
        raise PackagedGameError("SDK için hazırlanmış script bulunamadı")
    if _LANGUAGE.fullmatch(language) is None:
        raise PackagedGameError("Geçersiz Ren'Py dil adı")
    return TranslationCommandPlan(
        sdk_root=sdk.root,
        project_root=workspace,
        language=language,
        cwd=sdk.root,
        args=(*sdk.command_prefix, str(workspace), "translate", language),
        target_platform=sdk.target_platform,
        dry_run=False,
        execution_enabled=True,
        writes_to_original_game=False,
    )
