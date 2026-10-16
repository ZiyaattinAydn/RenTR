"""Desktop orchestration built only from tested core services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rentr.localization import LocalizationAssets
from rentr.memory import TranslationMemory
from rentr.packaged import plan_packaged_translation_command, prepare_packaged_game
from rentr.parser import parse_template
from rentr.pipeline import TranslationEngine, TranslationReport
from rentr.providers import TranslationProvider
from rentr.renderer import render_template
from rentr.renpy_cli import (
    TargetPlatform,
    discover_renpy_sdk,
    execute_translation_command,
    plan_translation_command,
)
from rentr.review import ReviewItem, build_review_queue
from rentr.scanner import GameInputMode, inspect_game
from rentr.workspace import plan_workspace, prepare_workspace
from rentr.writer import (
    WritePlan,
    WriteReceipt,
    apply_safe_write,
    plan_safe_write,
    rollback_safe_write,
)


class DesktopWorkflowError(ValueError):
    """Raised when the visual workflow cannot safely continue."""


@dataclass(frozen=True, slots=True)
class PreparedProject:
    workspace_root: Path
    templates: tuple[Path, ...]
    mode: GameInputMode


@dataclass(frozen=True, slots=True)
class DesktopPreview:
    report: TranslationReport
    review_queue: tuple[ReviewItem, ...]
    write_plan: WritePlan


@dataclass(frozen=True, slots=True)
class DesktopProjectPreview:
    previews: tuple[DesktopPreview, ...]

    @property
    def results_count(self) -> int:
        return sum(len(preview.report.results) for preview in self.previews)

    @property
    def review_queue(self) -> tuple[ReviewItem, ...]:
        items = (item for preview in self.previews for item in preview.review_queue)
        return tuple(sorted(items, key=lambda item: (-item.score, item.unit_id)))

    @property
    def preview_diff(self) -> str:
        return "\n".join(
            preview.write_plan.preview_diff
            for preview in self.previews
            if preview.write_plan.preview_diff
        )


def _workspace_templates(workspace_root: Path) -> tuple[Path, ...]:
    translation_dir = workspace_root / "game" / "tl" / "turkish"
    return tuple(sorted(translation_dir.rglob("*.rpy"))) if translation_dir.is_dir() else ()


def prepare_game_for_desktop(
    game_root: Path,
    workspace_root: Path,
    *,
    sdk_root: Path | None = None,
    target_platform: TargetPlatform,
) -> PreparedProject:
    """Prepare source/resume games without ever choosing the original as output."""
    workspace = workspace_root.expanduser().resolve()
    existing_templates = _workspace_templates(workspace) if workspace.is_dir() else ()
    if existing_templates:
        return PreparedProject(workspace, existing_templates, GameInputMode.RESUME)
    if workspace.exists():
        raise DesktopWorkflowError("Mevcut çalışma alanında kullanılabilir Türkçe şablon yok")

    inspection = inspect_game(game_root)
    if inspection.mode is GameInputMode.PACKAGED:
        if sdk_root is None:
            raise DesktopWorkflowError("Paketli oyun şablonu için Ren'Py SDK klasörü gerekli")
        prepared = prepare_packaged_game(game_root, workspace)
        sdk = discover_renpy_sdk(sdk_root, target_platform)
        command = plan_packaged_translation_command(prepared, sdk)
        result = execute_translation_command(command)
        return PreparedProject(workspace, result.generated_files, GameInputMode.PACKAGED)
    if inspection.mode is GameInputMode.UNSUPPORTED:
        raise DesktopWorkflowError("Desteklenen Ren'Py script veya arşivi bulunamadı")
    workspace_plan = plan_workspace(inspection, workspace)
    if inspection.mode is GameInputMode.SOURCE:
        if sdk_root is None:
            raise DesktopWorkflowError("Kaynak oyun için Ren'Py SDK klasörü gerekli")
        sdk = discover_renpy_sdk(sdk_root, target_platform)
        command_plan = plan_translation_command(inspection, workspace_plan, sdk)
        prepare_workspace(workspace_plan)
        result = execute_translation_command(command_plan)
        templates = result.generated_files
    else:
        prepare_workspace(workspace_plan)
        templates = _workspace_templates(workspace)
    if not templates:
        raise DesktopWorkflowError("İzole çalışma alanında Türkçe şablon bulunamadı")
    return PreparedProject(workspace, templates, inspection.mode)


def preview_template_translation(
    template_path: Path,
    workspace_root: Path,
    *,
    provider: TranslationProvider,
    output_relative_path: Path = Path("game/tl/turkish/rentr_output.rpy"),
    localization: LocalizationAssets | None = None,
) -> DesktopPreview:
    """Translate to an in-memory preview and local cache, never to the original game."""
    workspace = workspace_root.expanduser().resolve()
    units = parse_template(template_path.expanduser().resolve())
    with TranslationMemory(workspace / ".rentr" / "memory.sqlite3") as memory:
        report = TranslationEngine(
            provider=provider,
            memory=memory,
            localization=localization,
        ).translate(units)
    if report.failed_count:
        first = next(result for result in report.results if not result.succeeded)
        raise DesktopWorkflowError(f"Çeviri başarısız: {first.unit.unit_id}: {first.error}")
    rendered = render_template(report.translated_units)
    write_plan = plan_safe_write(
        workspace / output_relative_path,
        rendered,
        workspace_root=workspace,
    )
    return DesktopPreview(
        report=report,
        review_queue=build_review_queue(report, assets=localization),
        write_plan=write_plan,
    )


def apply_desktop_preview(preview: DesktopPreview) -> WriteReceipt:
    return apply_safe_write(preview.write_plan)


def preview_project_translation(
    template_paths: tuple[Path, ...],
    workspace_root: Path,
    *,
    provider: TranslationProvider,
    localization: LocalizationAssets | None = None,
) -> DesktopProjectPreview:
    """Preview every generated template and preserve each relative output path."""
    workspace = workspace_root.expanduser().resolve()
    if not template_paths:
        raise DesktopWorkflowError("Çevrilecek Türkçe şablon bulunamadı")
    previews: list[DesktopPreview] = []
    for template_path in template_paths:
        template = template_path.expanduser().resolve()
        if workspace not in template.parents:
            raise DesktopWorkflowError("Şablon izole çalışma alanının dışında olamaz")
        relative = template.relative_to(workspace)
        if relative.parts[:3] != ("game", "tl", "turkish") or template.suffix != ".rpy":
            raise DesktopWorkflowError("Şablon Türkçe çalışma klasöründe bir .rpy olmalı")
        previews.append(
            preview_template_translation(
                template,
                workspace,
                provider=provider,
                output_relative_path=relative,
                localization=localization,
            )
        )
    return DesktopProjectPreview(tuple(previews))


def apply_desktop_project_preview(
    preview: DesktopProjectPreview,
) -> tuple[WriteReceipt, ...]:
    """Apply every workspace preview, rolling earlier writes back on failure."""
    receipts: list[WriteReceipt] = []
    try:
        for item in preview.previews:
            receipts.append(apply_safe_write(item.write_plan))
    except BaseException:
        for receipt in reversed(receipts):
            rollback_safe_write(receipt)
        raise
    return tuple(receipts)
