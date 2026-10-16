"""RenTR command-line interface."""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from rentr import __version__
from rentr.audit import LocalAuditLog
from rentr.config import load_project_config
from rentr.domain import TranslationUnit
from rentr.local_models import (
    HardwareProfile,
    ModelRequirement,
    OllamaProvider,
    QualityProfile,
    assess_model,
    build_ollama_judge_provider,
    build_ollama_provider,
    build_ollama_repair_provider,
    detect_hardware,
)
from rentr.localization import (
    LocalizationAssets,
    load_character_cards,
    load_glossary,
)
from rentr.memory import TranslationMemory
from rentr.mod_package import (
    TranslationPackageError,
    apply_package_install,
    build_translation_package,
    load_install_receipt,
    plan_package_install,
    rollback_package_install,
)
from rentr.packaged import (
    PackagedGameError,
    plan_packaged_translation_command,
    prepare_packaged_game,
)
from rentr.parser import TemplateParseError, parse_template
from rentr.pilot import select_pilot_units
from rentr.pipeline import (
    TranslationEngine,
    TranslationOrigin,
    TranslationReport,
    TranslationResult,
    WorkEstimate,
)
from rentr.providers import MockTranslationProvider, OpenAICompatibleProvider, ProviderError
from rentr.renderer import TemplateRenderError, render_template
from rentr.renpy_cli import (
    RenPyCliError,
    TargetPlatform,
    TranslationCommandPlan,
    discover_renpy_sdk,
    execute_translation_command,
    plan_translation_command,
)
from rentr.review import build_review_queue
from rentr.runtime_research import (
    RuntimeOverlaySimulator,
    RuntimeResearchError,
    assess_runtime_strategies,
    load_text_events,
)
from rentr.scanner import GameInspection, GameInspectionError, inspect_game
from rentr.triage import UnitDisposition, classify_source_text
from rentr.updates import compare_inventories
from rentr.workspace import WorkspaceError, WorkspacePlan, plan_workspace, prepare_workspace
from rentr.writer import SafeWriteError, apply_safe_write, plan_safe_write

app = typer.Typer(
    add_completion=False,
    help="Ren'Py projeleri için Türkçe yerelleştirme yardımcısı.",
    no_args_is_help=True,
)
console = Console()
DEFAULT_TARGET_PLATFORM = TargetPlatform.WINDOWS if os.name == "nt" else TargetPlatform.POSIX


def _version_callback(value: bool) -> None:
    if value:
        console.print(__version__)
        raise typer.Exit()


def _inventory_record(unit: TranslationUnit) -> dict[str, object]:
    return {
        "unit_id": unit.unit_id,
        "kind": unit.kind.value,
        "source_text": unit.source_text,
        "translated_text": unit.translated_text,
        "translated_segments": list(unit.translated_segments),
        "speaker": unit.speaker,
        "label": unit.label,
        "file_path": str(unit.file_path),
        "line_number": unit.line_number,
        "source_hash": unit.source_hash,
        "status": unit.status.value,
    }


def _game_record(inspection: GameInspection) -> dict[str, object]:
    return {
        "mode": inspection.mode.value,
        "selected_root": str(inspection.selected_root),
        "game_dir": str(inspection.game_dir),
        "translation_dir": str(inspection.translation_dir),
        "source_script_count": len(inspection.source_scripts),
        "compiled_script_count": len(inspection.compiled_scripts),
        "archive_count": len(inspection.archives),
        "translation_file_count": len(inspection.translation_files),
        "next_action": inspection.next_action,
    }


def _workspace_record(plan: WorkspacePlan) -> dict[str, object]:
    return {
        "game_root": str(plan.game_root),
        "workspace_root": str(plan.workspace_root),
        "file_count": len(plan.files),
        "source_bytes": plan.source_bytes,
        "required_free_bytes": plan.required_free_bytes,
        "available_free_bytes": plan.available_free_bytes,
        "files": [item.relative_destination.as_posix() for item in plan.files],
        "writes_to_original_game": False,
    }


def _translation_plan_record(plan: TranslationCommandPlan) -> dict[str, object]:
    return {
        "target_platform": plan.target_platform.value,
        "sdk_root": str(plan.sdk_root),
        "project_root": str(plan.project_root),
        "language": plan.language,
        "cwd": str(plan.cwd),
        "args": list(plan.args),
        "dry_run": plan.dry_run,
        "execution_enabled": plan.execution_enabled,
        "writes_to_original_game": plan.writes_to_original_game,
    }


def _estimate_record(estimate: WorkEstimate) -> dict[str, int]:
    return {
        "total_units": estimate.total_units,
        "existing_units": estimate.existing_units,
        "cached_units": estimate.cached_units,
        "passthrough_units": estimate.passthrough_units,
        "provider_units": estimate.provider_units,
        "provider_characters": estimate.provider_characters,
    }


def _resolve_output(workspace: Path, output: Path) -> Path:
    return output if output.is_absolute() else workspace / output


def _load_mock_provider(mapping_path: Path) -> MockTranslationProvider:
    try:
        payload = json.loads(mapping_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Mock çeviri haritası okunamadı: {error}") from error
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in payload.items()
    ):
        raise ValueError("Mock çeviri haritası string:string JSON nesnesi olmalı")
    return MockTranslationProvider(payload)


def _load_localization_assets(
    glossary_path: Path | None,
    characters_path: Path | None,
) -> LocalizationAssets:
    return LocalizationAssets(
        glossary=load_glossary(glossary_path) if glossary_path is not None else None,
        characters=(
            load_character_cards(characters_path) if characters_path is not None else ()
        ),
    )


@app.command()
def doctor(
    project: Annotated[
        Path | None,
        typer.Option("--project", help="İsteğe bağlı Ren'Py proje klasörü."),
    ] = None,
) -> None:
    """Çalışma ortamını kontrol eder; proje dosyalarını değiştirmez."""
    table = Table(title=f"RenTR {__version__} — Ortam Kontrolü")
    table.add_column("Kontrol")
    table.add_column("Sonuç")
    table.add_row("Python", platform.python_version())
    table.add_row("Platform", platform.platform())
    table.add_row("SQLite", sqlite3.sqlite_version)

    if project is None:
        table.add_row("Proje", "Seçilmedi")
    else:
        resolved = project.expanduser().resolve()
        if not resolved.is_dir():
            console.print(table)
            console.print(f"[red]Hata:[/red] Proje klasörü bulunamadı: {resolved}")
            raise typer.Exit(code=2)
        table.add_row("Proje", str(resolved))

    table.add_row("Durum", "Temel ortam hazır")
    console.print(table)


@app.command()
def inventory(
    template: Annotated[
        Path,
        typer.Argument(help="Ren'Py tarafından oluşturulmuş .rpy çeviri şablonu."),
    ],
) -> None:
    """Diyalog ve old/new kaynaklarını salt okunur JSON envanterine çıkarır."""
    resolved = template.expanduser().resolve()
    if not resolved.is_file():
        console.print(f"[red]Hata:[/red] Şablon dosyası bulunamadı: {resolved}")
        raise typer.Exit(code=2)

    try:
        units = parse_template(resolved)
    except (OSError, UnicodeError, TemplateParseError) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=3) from error

    typer.echo(
        json.dumps(
            [_inventory_record(unit) for unit in units],
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command(name="render-template")
def render_template_command(
    template: Annotated[
        Path,
        typer.Argument(help="Önizlenecek Ren'Py .rpy çeviri şablonu."),
    ],
    language: Annotated[
        str,
        typer.Option("--language", help="Küçük ASCII Ren'Py dil adı."),
    ] = "turkish",
) -> None:
    """Şablonu dosyaya yazmadan kanonik Ren'Py metni olarak gösterir."""
    resolved = template.expanduser().resolve()
    if not resolved.is_file():
        console.print(f"[red]Hata:[/red] Şablon dosyası bulunamadı: {resolved}")
        raise typer.Exit(code=2)

    try:
        rendered = render_template(parse_template(resolved), language=language)
    except (OSError, UnicodeError, TemplateParseError, TemplateRenderError) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=3) from error

    typer.echo(rendered, nl=False)


@app.command(name="inspect-game")
def inspect_game_command(
    game_root: Annotated[
        Path,
        typer.Argument(help="Oyunun game klasörünü içeren ana dizini."),
    ],
) -> None:
    """Oyunu çalıştırmadan source, packaged veya resume modunu belirler."""
    try:
        inspection = inspect_game(game_root)
    except GameInspectionError as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error

    typer.echo(json.dumps(_game_record(inspection), ensure_ascii=False, indent=2))


@app.command(name="workspace-plan")
def workspace_plan_command(
    game_root: Annotated[
        Path,
        typer.Argument(help="Oyunun game klasörünü içeren ana dizini."),
    ],
    destination: Annotated[
        Path,
        typer.Option("--destination", "-d", help="İzole çalışma alanının yeni yolu."),
    ],
) -> None:
    """Dosya kopyalamadan seçici ve izole çalışma alanı planını gösterir."""
    try:
        inspection = inspect_game(game_root)
        plan = plan_workspace(inspection, destination)
    except (GameInspectionError, OSError, WorkspaceError) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error

    typer.echo(json.dumps(_workspace_record(plan), ensure_ascii=False, indent=2))


@app.command(name="translation-plan")
def translation_plan_command(
    game_root: Annotated[
        Path,
        typer.Argument(help="Kaynak .rpy dosyalarını içeren oyun ana dizini."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="İzole çalışma alanının yeni yolu."),
    ],
    sdk_root: Annotated[
        Path,
        typer.Option("--sdk", help="Resmî Ren'Py SDK kök klasörü."),
    ],
    target_platform: Annotated[
        TargetPlatform,
        typer.Option("--target-platform", help="SDK başlatıcı düzeni."),
    ] = DEFAULT_TARGET_PLATFORM,
    language: Annotated[
        str,
        typer.Option("--language", help="Küçük ASCII Ren'Py dil adı."),
    ] = "turkish",
) -> None:
    """Resmî translate komutunu çalıştırmadan güvenli JSON planı üretir."""
    try:
        inspection = inspect_game(game_root)
        workspace_plan = plan_workspace(inspection, workspace)
        sdk = discover_renpy_sdk(sdk_root, target_platform)
        command_plan = plan_translation_command(
            inspection,
            workspace_plan,
            sdk,
            language,
        )
    except (GameInspectionError, OSError, RenPyCliError, WorkspaceError) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error

    typer.echo(json.dumps(_translation_plan_record(command_plan), ensure_ascii=False, indent=2))


@app.command(name="prepare-translation")
def prepare_translation_command(
    game_root: Annotated[
        Path,
        typer.Argument(help="Kaynak .rpy dosyalarını içeren oyun ana dizini."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Oluşturulacak izole çalışma alanı."),
    ],
    sdk_root: Annotated[
        Path,
        typer.Option("--sdk", help="Resmî Ren'Py SDK kök klasörü."),
    ],
    target_platform: Annotated[
        TargetPlatform,
        typer.Option("--target-platform", help="SDK başlatıcı düzeni."),
    ] = DEFAULT_TARGET_PLATFORM,
    language: Annotated[
        str,
        typer.Option("--language", help="Küçük ASCII Ren'Py dil adı."),
    ] = "turkish",
) -> None:
    """İzole kopyayı oluşturur ve resmî SDK ile çeviri şablonlarını üretir."""
    try:
        inspection = inspect_game(game_root)
        workspace_plan = plan_workspace(inspection, workspace)
        sdk = discover_renpy_sdk(sdk_root, target_platform)
        command_plan = plan_translation_command(
            inspection,
            workspace_plan,
            sdk,
            language,
        )
        prepare_workspace(workspace_plan)
        result = execute_translation_command(command_plan)
    except (GameInspectionError, OSError, RenPyCliError, WorkspaceError) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error

    typer.echo(
        json.dumps(
            {
                "workspace": str(workspace_plan.workspace_root),
                "generated_files": [str(path) for path in result.generated_files],
                "return_code": result.return_code,
                "writes_to_original_game": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command(name="prepare-packaged")
def prepare_packaged_command(
    game_root: Annotated[
        Path,
        typer.Argument(help=".rpa/.rpyc içeren paketli Ren'Py oyun klasörü."),
    ],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Oluşturulacak izole çalışma alanı."),
    ],
    sdk_root: Annotated[
        Path | None,
        typer.Option("--sdk", help="Şablon üretmek için resmî Ren'Py SDK kökü."),
    ] = None,
    target_platform: Annotated[
        TargetPlatform,
        typer.Option("--target-platform", help="SDK başlatıcı düzeni."),
    ] = DEFAULT_TARGET_PLATFORM,
    language: Annotated[
        str,
        typer.Option("--language", help="Küçük ASCII Ren'Py dil adı."),
    ] = "turkish",
) -> None:
    """Standart RPA-3.0 scriptlerini oyun kodu çalıştırmadan izole alana çıkarır."""
    try:
        prepared = prepare_packaged_game(game_root, workspace)
        generated_files: tuple[Path, ...] = ()
        if sdk_root is not None:
            sdk = discover_renpy_sdk(sdk_root, target_platform)
            command_plan = plan_packaged_translation_command(
                prepared,
                sdk,
                language=language,
            )
            generated_files = execute_translation_command(command_plan).generated_files
    except (
        GameInspectionError,
        OSError,
        PackagedGameError,
        RenPyCliError,
        ValueError,
    ) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error
    typer.echo(
        json.dumps(
            {
                "workspace": str(prepared.workspace_root),
                "runtime_generation": prepared.runtime.generation.value,
                "runtime_version": prepared.runtime.version,
                "source_scripts": [str(path) for path in prepared.source_scripts],
                "compiled_scripts": [str(path) for path in prepared.compiled_scripts],
                "needs_compiled_backend": prepared.needs_compiled_backend,
                "compiled_formats": [
                    inspection.format.value for inspection in prepared.compiled_inspections
                ],
                "generated_files": [str(path) for path in generated_files],
                "writes_to_original_game": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command(name="build-package")
def build_package_command(
    workspace: Annotated[
        Path,
        typer.Argument(help="Türkçe çevirileri içeren izole çalışma alanı."),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Çalışma alanı içindeki isteğe bağlı ZIP yolu."),
    ] = None,
    manual_language: Annotated[
        bool,
        typer.Option(
            "--manual-language",
            help="Türkçeyi varsayılan yapma; oyun içinden elle seçilecek.",
        ),
    ] = False,
) -> None:
    """Doğrulanmış ve yeniden üretilebilir Türkçe kurulum paketi oluşturur."""
    try:
        built = build_translation_package(
            workspace,
            output,
            activate_turkish=not manual_language,
        )
    except (OSError, TranslationPackageError) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error
    typer.echo(
        json.dumps(
            {
                "package": str(built.package_path),
                "package_id": built.manifest.package_id,
                "package_hash": built.package_hash,
                "activation": built.manifest.activation,
                "files": [item.path for item in built.manifest.files],
                "writes_to_original_game": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command(name="install-package")
def install_package_command(
    package: Annotated[Path, typer.Argument(help="RenTR Türkçe çeviri ZIP paketi.")],
    game_root: Annotated[Path, typer.Argument(help="Kurulum yapılacak Ren'Py oyun klasörü.")],
    replace_existing: Annotated[
        bool,
        typer.Option(
            "--replace-existing",
            help="Mevcut hedefleri yedekleyip değiştirmeye açık onay ver.",
        ),
    ] = False,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Doğrulanmış kurulum planını gerçek oyuna uygula."),
    ] = False,
) -> None:
    """Varsayılan olarak yalnız planlar; --apply gerçek oyuna kurar."""
    try:
        plan = plan_package_install(
            package,
            game_root,
            replace_existing=replace_existing,
        )
        receipt = apply_package_install(plan) if apply else None
    except (OSError, TranslationPackageError) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error
    typer.echo(
        json.dumps(
            {
                "package_id": plan.package_id,
                "game_root": str(plan.game_root),
                "files": [target.relative_path for target in plan.targets],
                "collisions": list(plan.collisions),
                "applied": receipt is not None,
                "receipt": str(receipt.receipt_path) if receipt is not None else None,
                "writes_to_original_game": receipt is not None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command(name="rollback-install")
def rollback_install_command(
    game_root: Annotated[Path, typer.Argument(help="Kurulumun yapıldığı Ren'Py oyun klasörü.")],
    receipt: Annotated[
        Path,
        typer.Option("--receipt", help="Oyunun .rentr/installations klasöründeki kayıt."),
    ],
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Doğrulanmış geri alma planını uygula."),
    ] = False,
) -> None:
    """Kurulum kaydını doğrular; --apply ile korumalı geri alma yapar."""
    try:
        loaded = load_install_receipt(receipt, game_root)
        if apply:
            rollback_package_install(loaded)
    except (OSError, TranslationPackageError) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error
    typer.echo(
        json.dumps(
            {
                "package_id": loaded.package_id,
                "game_root": str(loaded.game_root),
                "files": [item.relative_path for item in loaded.files],
                "applied": apply,
                "receipt_removed": apply,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command(name="inventory-report")
def inventory_report(
    path: Annotated[Path, typer.Argument(help="Türkçe şablon dosyası veya tl/turkish klasörü.")],
) -> None:
    """Report what really needs AI work before any provider request."""
    resolved = path.expanduser().resolve()
    files: tuple[Path, ...]
    if resolved.is_file():
        files = (resolved,)
    elif resolved.is_dir():
        files = tuple(sorted(resolved.rglob("*.rpy")))
    else:
        raise typer.BadParameter(f"Şablon yolu bulunamadı: {resolved}")
    if not files:
        raise typer.BadParameter(f"Şablon bulunamadı: {resolved}")

    units = tuple(unit for template in files for unit in parse_template(template))
    triage = tuple(classify_source_text(unit.source_text) for unit in units)
    provider_units = tuple(
        unit
        for unit, classification in zip(units, triage, strict=True)
        if classification.disposition is UnitDisposition.PROVIDER
    )
    reason_counts = Counter(
        classification.reason
        for classification in triage
        if classification.disposition is UnitDisposition.PASSTHROUGH
    )
    source_counts = Counter(unit.source_text for unit in provider_units)
    duplicates = [
        {"source_text": source, "count": count}
        for source, count in source_counts.most_common(20)
        if count > 1
    ]
    payload: dict[str, object] = {
        "template_files": len(files),
        "total_units": len(units),
        "dialogue_units": sum(unit.kind.value == "dialogue" for unit in units),
        "string_units": sum(unit.kind.value == "string" for unit in units),
        "provider_units": len(provider_units),
        "passthrough_units": len(units) - len(provider_units),
        "passthrough_reasons": dict(sorted(reason_counts.items())),
        "unique_provider_source_texts": len(source_counts),
        "duplicate_provider_occurrences": len(provider_units) - len(source_counts),
        "top_provider_duplicates": duplicates,
    }
    console.print_json(json.dumps(payload, ensure_ascii=False))


@app.command(name="pilot-report")
def pilot_report_command(
    path: Annotated[Path, typer.Argument(help="Türkçe şablon dosyası veya tl/turkish klasörü.")],
    limit: Annotated[int, typer.Option("--limit", min=1, max=500)] = 100,
) -> None:
    """Build a deterministic representative sample without calling any provider."""
    resolved = path.expanduser().resolve()
    files: tuple[Path, ...]
    if resolved.is_file():
        files = (resolved,)
    elif resolved.is_dir():
        files = tuple(sorted(resolved.rglob("*.rpy")))
    else:
        raise typer.BadParameter(f"Şablon yolu bulunamadı: {resolved}")
    if not files:
        raise typer.BadParameter(f"Şablon bulunamadı: {resolved}")

    units = tuple(unit for template in files for unit in parse_template(template))
    selections = select_pilot_units(units, limit=limit)
    category_counts = Counter(selection.category.value for selection in selections)
    payload = {
        "requested_limit": limit,
        "selected_units": len(selections),
        "category_counts": dict(sorted(category_counts.items())),
        "samples": [
            {
                "category": selection.category.value,
                "unit_id": selection.unit.unit_id,
                "source_text": selection.unit.source_text,
                "speaker": selection.unit.speaker,
                "label": selection.unit.label,
                "file_path": str(selection.unit.file_path),
                "line_number": selection.unit.line_number,
            }
            for selection in selections
        ],
    }
    console.print_json(json.dumps(payload, ensure_ascii=False))


@app.command(name="pilot-translate")
def pilot_translate_command(
    path: Annotated[Path, typer.Argument(help="Türkçe şablon dosyası veya tl/turkish klasörü.")],
    workspace: Annotated[Path, typer.Option("--workspace", "-w")],
    ollama_model: Annotated[str, typer.Option("--ollama-model")] = "qwen2.5:7b",
    repair_model: Annotated[
        str | None,
        typer.Option(
            "--repair-model",
            help=(
                "Yüksek riskli veya teknik olarak bozulan ilk çevirileri bağlamla "
                "post-edit edecek ikinci Ollama modeli."
            ),
        ),
    ] = None,
    judge_model: Annotated[
        str | None,
        typer.Option(
            "--judge-model",
            help=(
                "Temel ve repair adayları arasında BASE/REPAIR/REJECT kararı verecek "
                "Ollama modeli. Belirtilmezse repair modeli kullanılır."
            ),
        ),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=500)] = 100,
    quality: Annotated[QualityProfile, typer.Option("--quality")] = QualityProfile.BALANCED,
    output: Annotated[Path | None, typer.Option("--output")] = None,
    reuse_memory: Annotated[
        bool,
        typer.Option(
            "--reuse-memory/--fresh-memory",
            help=(
                "Pilot belleğini yeniden kullan; varsayılan her kalite koşusunda "
                "temiz bellektir."
            ),
        ),
    ] = False,
) -> None:
    """Translate only a representative pilot sample while retaining full-game context."""
    resolved = path.expanduser().resolve()
    resolved_workspace = workspace.expanduser().resolve()
    files: tuple[Path, ...]
    if resolved.is_file():
        files = (resolved,)
    elif resolved.is_dir():
        files = tuple(sorted(resolved.rglob("*.rpy")))
    else:
        raise typer.BadParameter(f"Şablon yolu bulunamadı: {resolved}")
    if not files:
        raise typer.BadParameter(f"Şablon bulunamadı: {resolved}")
    if not resolved_workspace.is_dir():
        raise typer.BadParameter(f"Çalışma alanı bulunamadı: {resolved_workspace}")

    units = tuple(unit for template in files for unit in parse_template(template))
    selections = select_pilot_units(units, limit=limit)
    if not selections:
        raise typer.BadParameter("Pilot için sağlayıcıya gidecek metin bulunamadı")

    pilot_memory = resolved_workspace / ".rentr" / "pilot-memory.sqlite3"
    if not reuse_memory:
        for suffix in ("", "-wal", "-shm"):
            Path(f"{pilot_memory}{suffix}").unlink(missing_ok=True)

    if judge_model is not None and repair_model is None:
        raise typer.BadParameter("--judge-model yalnız --repair-model ile kullanılabilir")

    provider = build_ollama_provider(model=ollama_model, quality=quality)
    repair_provider = (
        build_ollama_repair_provider(model=repair_model, quality=quality)
        if repair_model is not None
        else None
    )
    effective_judge_model = judge_model or repair_model
    judge_provider = (
        build_ollama_judge_provider(model=effective_judge_model, quality=quality)
        if effective_judge_model is not None
        else None
    )
    try:
        with TranslationMemory(pilot_memory) as memory:
            report = TranslationEngine(
                provider=provider,
                memory=memory,
                repair_provider=repair_provider,
                judge_provider=judge_provider,
            ).translate_selected(
                units,
                (selection.index for selection in selections),
            )
    finally:
        provider.close()
        if repair_provider is not None:
            repair_provider.close()
        if judge_provider is not None:
            judge_provider.close()

    categories = {selection.index: selection.category for selection in selections}
    result_rows = []
    for selection, result in zip(selections, report.results, strict=True):
        result_rows.append(
            {
                "category": categories[selection.index].value,
                "unit_id": result.unit.unit_id,
                "source_text": result.unit.source_text,
                "translated_text": result.translated_text,
                "speaker": result.unit.speaker,
                "label": result.unit.label,
                "file_path": str(result.unit.file_path),
                "line_number": result.unit.line_number,
                "origin": result.origin.value,
                "attempts": result.attempts,
                "error": result.error,
                "base_translated_text": result.base_translated_text,
                "risk_score": result.risk_score,
                "risk_reasons": list(result.risk_reasons),
                "repair_attempted": result.repair_attempted,
                "repair_used": result.repair_used,
                "repair_attempts": result.repair_attempts,
                "repair_model": result.repair_model,
                "repair_error": result.repair_error,
                "post_repair_risk_reasons": list(result.post_repair_risk_reasons),
                "selector_attempted": result.selector_attempted,
                "selector_decision": (
                    result.selector_decision.value
                    if result.selector_decision is not None
                    else None
                ),
                "selector_attempts": result.selector_attempts,
                "selector_model": result.selector_model,
                "selector_confidence": result.selector_confidence,
                "selector_reasons": list(result.selector_reasons),
                "selector_error": result.selector_error,
            }
        )

    destination = (
        output.expanduser().resolve()
        if output is not None
        else resolved_workspace / ".rentr" / "pilot-results.json"
    )
    workspace_resolved = resolved_workspace.resolve()
    if destination != workspace_resolved and workspace_resolved not in destination.parents:
        raise typer.BadParameter("Pilot çıktısı izole çalışma alanının dışında olamaz")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "model": ollama_model,
                "repair_model": repair_model,
                "judge_model": effective_judge_model,
                "quality": quality.value,
                "selected_units": len(selections),
                "failed_units": report.failed_count,
                "repair_attempted_units": report.repair_attempted_count,
                "repaired_units": report.repaired_count,
                "selector_attempted_units": report.selector_attempted_count,
                "selector_base_units": report.selector_base_count,
                "selector_repair_units": report.selector_repair_count,
                "selector_reject_units": report.selector_reject_count,
                "memory_mode": "reuse" if reuse_memory else "fresh",
                "results": result_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    typer.echo(
        json.dumps(
            {
                "selected_units": len(selections),
                "failed_units": report.failed_count,
                "repair_attempted_units": report.repair_attempted_count,
                "repaired_units": report.repaired_count,
                "selector_attempted_units": report.selector_attempted_count,
                "selector_base_units": report.selector_base_count,
                "selector_repair_units": report.selector_repair_count,
                "selector_reject_units": report.selector_reject_count,
                "memory_mode": "reuse" if reuse_memory else "fresh",
                "output": str(destination),
                "writes_to_original_game": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if report.failed_count:
        raise typer.Exit(code=3)


@app.command(name="translate-estimate")
def translate_estimate_command(
    template: Annotated[Path, typer.Argument(help="Ren'Py Türkçe çeviri şablonu.")],
    memory_path: Annotated[
        Path,
        typer.Option("--memory", help="Yerel SQLite çeviri belleği yolu."),
    ],
) -> None:
    """Sağlayıcı çağrısı yapmadan kalan birim ve karakter işini hesaplar."""
    resolved = template.expanduser().resolve()
    try:
        units = parse_template(resolved)
        with TranslationMemory(memory_path) as memory:
            estimate = TranslationEngine(
                provider=MockTranslationProvider({}),
                memory=memory,
            ).estimate(units)
    except (OSError, UnicodeError, TemplateParseError, ValueError) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error
    typer.echo(json.dumps(_estimate_record(estimate), ensure_ascii=False, indent=2))


@app.command(name="translate-template")
def translate_template_command(
    template: Annotated[Path, typer.Argument(help="Çevrilecek Ren'Py şablonu.")],
    workspace: Annotated[
        Path,
        typer.Option("--workspace", "-w", help="Mevcut izole çalışma alanı."),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Çalışma alanına göre göreli veya alan içindeki mutlak çıktı yolu.",
        ),
    ] = Path("game/tl/turkish/rentr_output.rpy"),
    memory_path: Annotated[
        Path | None,
        typer.Option("--memory", help="Varsayılan: WORKSPACE/.rentr/memory.sqlite3"),
    ] = None,
    mock_map: Annotated[
        Path | None,
        typer.Option("--mock-map", help="Yalnız test için korumalı JSON çeviri haritası."),
    ] = None,
    provider_url: Annotated[
        str | None,
        typer.Option("--provider-url", help="OpenAI uyumlu /v1 taban adresi."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="Sağlayıcı model adı."),
    ] = None,
    ollama_model: Annotated[
        str | None,
        typer.Option("--ollama-model", help="Yerel Ollama model adı; API anahtarı gerekmez."),
    ] = None,
    quality: Annotated[
        QualityProfile,
        typer.Option("--quality", help="Yerel model kalite profili."),
    ] = QualityProfile.BALANCED,
    glossary: Annotated[
        Path | None,
        typer.Option("--glossary", help="Sürümlü Türkçe sözlük JSON dosyası."),
    ] = None,
    characters: Annotated[
        Path | None,
        typer.Option("--characters", help="Karakter sesi ve sen/siz kartları JSON dosyası."),
    ] = None,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Doğrulanmış diff'i izole alana atomik uygula."),
    ] = False,
) -> None:
    """Çevirir, doğrular ve diff gösterir; varsayılan olarak dosya yazmaz."""
    resolved_template = template.expanduser().resolve()
    resolved_workspace = workspace.expanduser().resolve()
    database = memory_path or resolved_workspace / ".rentr" / "memory.sqlite3"
    provider: MockTranslationProvider | OpenAICompatibleProvider | OllamaProvider
    closable_provider: OpenAICompatibleProvider | OllamaProvider | None = None
    try:
        if mock_map is not None:
            provider = _load_mock_provider(mock_map.expanduser().resolve())
        elif ollama_model is not None:
            closable_provider = build_ollama_provider(
                model=ollama_model,
                base_url=provider_url or "http://127.0.0.1:11434",
                quality=quality,
            )
            provider = closable_provider
        else:
            api_key = os.environ.get("RENTR_API_KEY", "")
            if provider_url is None or model is None or not api_key:
                raise ValueError(
                    "Gerçek sağlayıcı için --provider-url, --model ve RENTR_API_KEY gerekli"
                )
            closable_provider = OpenAICompatibleProvider(
                base_url=provider_url,
                api_key=api_key,
                model=model,
            )
            provider = closable_provider

        units = parse_template(resolved_template)
        assets = _load_localization_assets(glossary, characters)
        with TranslationMemory(database) as memory:
            engine = TranslationEngine(
                provider=provider,
                memory=memory,
                localization=assets,
            )
            estimate = engine.estimate(units)
            report = engine.translate(units)
        if report.failed_count:
            failures = [
                {
                    "unit_id": result.unit.unit_id,
                    "error": result.error,
                    "attempts": result.attempts,
                }
                for result in report.results
                if not result.succeeded
            ]
            typer.echo(json.dumps({"failures": failures}, ensure_ascii=False, indent=2))
            raise typer.Exit(code=3)

        rendered = render_template(report.translated_units)
        output_path = _resolve_output(resolved_workspace, output)
        write_plan = plan_safe_write(
            output_path,
            rendered,
            workspace_root=resolved_workspace,
        )
        applied = False
        backup_path: str | None = None
        if apply:
            receipt = apply_safe_write(write_plan)
            applied = True
            backup_path = str(receipt.backup_path) if receipt.backup_path else None
        review_queue = build_review_queue(report, assets=assets)
        LocalAuditLog(resolved_workspace).append(
            "translation.completed",
            unit_count=len(report.results),
            failed_count=report.failed_count,
            applied=applied,
            output=str(write_plan.output_path),
        )
    except typer.Exit:
        raise
    except (
        OSError,
        UnicodeError,
        TemplateParseError,
        TemplateRenderError,
        SafeWriteError,
        ValueError,
    ) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error
    finally:
        if closable_provider is not None:
            closable_provider.close()

    typer.echo(
        json.dumps(
            {
                "estimate": _estimate_record(estimate),
                "output": str(write_plan.output_path),
                "preview_diff": write_plan.preview_diff,
                "applied": applied,
                "backup": backup_path,
                "review_queue": [
                    {
                        "unit_id": item.unit_id,
                        "score": item.score,
                        "reasons": [reason.value for reason in item.reasons],
                    }
                    for item in review_queue
                ],
                "writes_to_original_game": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command(name="project-check")
def project_check_command(
    config_path: Annotated[Path, typer.Argument(help="rentr.toml proje yapılandırması.")],
) -> None:
    """Yapılandırma ve yerelleştirme varlıklarını gizli değer göstermeden doğrular."""
    try:
        config = load_project_config(config_path)
        assets = _load_localization_assets(config.glossary_path, config.characters_path)
        record = config.sanitized_record()
        record["glossary_version"] = assets.glossary.version if assets.glossary else None
        record["glossary_term_count"] = len(assets.glossary.entries) if assets.glossary else 0
        record["character_count"] = len(assets.characters)
    except (OSError, UnicodeError, ValueError) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error
    typer.echo(json.dumps(record, ensure_ascii=False, indent=2))


@app.command(name="local-model-check")
def local_model_check_command(
    model: Annotated[str, typer.Option("--model", help="Değerlendirilecek yerel model adı.")],
    minimum_memory: Annotated[
        float,
        typer.Option("--minimum-memory", min=0.1, help="Minimum RAM (GiB)."),
    ] = 4.0,
    recommended_memory: Annotated[
        float,
        typer.Option("--recommended-memory", min=0.1, help="Önerilen RAM (GiB)."),
    ] = 8.0,
    connect: Annotated[
        bool,
        typer.Option("--connect", help="Yerel Ollama model listesini de kontrol et."),
    ] = False,
    base_url: Annotated[
        str,
        typer.Option("--base-url", help="Yerel Ollama adresi."),
    ] = "http://127.0.0.1:11434",
) -> None:
    """Yerel donanım uygunluğunu raporlar; varsayılan olarak ağ çağrısı yapmaz."""
    provider: OllamaProvider | None = None
    try:
        hardware: HardwareProfile = detect_hardware()
        assessment = assess_model(
            hardware,
            ModelRequirement(model, minimum_memory, recommended_memory),
        )
        installed_models: tuple[str, ...] | None = None
        if connect:
            provider = OllamaProvider(model=model, base_url=base_url)
            installed_models = provider.list_models()
    except (OSError, ProviderError, ValueError) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error
    finally:
        if provider is not None:
            provider.close()
    typer.echo(
        json.dumps(
            {
                "operating_system": hardware.operating_system,
                "cpu_count": hardware.cpu_count,
                "memory_gib": hardware.memory_gib,
                "model": model,
                "suitability": assessment.suitability.value,
                "reason": assessment.reason,
                "installed_models": (
                    list(installed_models) if installed_models is not None else None
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command(name="runtime-research-report")
def runtime_research_report_command(
    game_root: Annotated[
        Path,
        typer.Argument(help="Salt okunur runtime seçenek raporu üretilecek oyun."),
    ],
) -> None:
    """Statik, clipboard, OCR ve hook yaklaşımlarını oyunu başlatmadan değerlendirir."""
    try:
        report = assess_runtime_strategies(game_root)
    except (GameInspectionError, OSError, RuntimeResearchError, ValueError) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error
    typer.echo(
        json.dumps(
            {
                "game_root": str(report.game_root),
                "game_mode": report.game_mode.value,
                "runtime_generation": report.runtime.generation.value,
                "runtime_version": report.runtime.version,
                "strategies": [
                    {
                        "strategy": item.strategy.value,
                        "verdict": item.verdict.value,
                        "reason": item.reason,
                        "requires_game_write": item.requires_game_write,
                        "requires_screen_capture": item.requires_screen_capture,
                        "requires_process_injection": item.requires_process_injection,
                        "known_limitations": list(item.known_limitations),
                    }
                    for item in report.strategies
                ],
                "writes_to_game": report.writes_to_game,
                "starts_game_process": report.starts_game_process,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command(name="runtime-simulate")
def runtime_simulate_command(
    events: Annotated[
        Path,
        typer.Argument(help="Her satırı bir kullanıcı sağladığı metin olayı olan UTF-8 dosya."),
    ],
    mock_map: Annotated[
        Path,
        typer.Option("--mock-map", help="Araştırma için korumalı JSON çeviri haritası."),
    ],
) -> None:
    """Ekran yakalamadan veya hook yapmadan metin akışı çevirisini simüle eder."""
    try:
        source_events = load_text_events(events)
        provider = _load_mock_provider(mock_map.expanduser().resolve())
        frames = RuntimeOverlaySimulator(provider).simulate(source_events)
    except (OSError, ProviderError, RuntimeResearchError, ValueError) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error
    typer.echo(
        json.dumps(
            {
                "frames": [
                    {
                        "sequence": frame.sequence,
                        "source_text": frame.source_text,
                        "translated_text": frame.translated_text,
                        "origin": frame.origin.value,
                    }
                    for frame in frames
                ],
                "provider_calls": len(provider.calls),
                "writes_to_game": False,
                "captures_screen": False,
                "injects_process": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command(name="review-queue")
def review_queue_command(
    template: Annotated[Path, typer.Argument(help="Mevcut Türkçe hedefleri içeren şablon.")],
    glossary: Annotated[
        Path | None,
        typer.Option("--glossary", help="Sürümlü Türkçe sözlük JSON dosyası."),
    ] = None,
    characters: Annotated[
        Path | None,
        typer.Option("--characters", help="Karakter kartları JSON dosyası."),
    ] = None,
    minimum_score: Annotated[
        int,
        typer.Option("--minimum-score", min=0, max=100, help="En düşük risk puanı."),
    ] = 1,
) -> None:
    """Mevcut hedeflerden açıklanabilir risk sıralı inceleme kuyruğu üretir."""
    try:
        units = parse_template(template.expanduser().resolve())
        report = TranslationReport(
            tuple(
                TranslationResult(
                    unit=unit,
                    translated_text=unit.translated_text,
                    origin=(
                        TranslationOrigin.EXISTING
                        if unit.translated_text is not None
                        else TranslationOrigin.FAILED
                    ),
                    attempts=0,
                    error=None if unit.translated_text is not None else "çeviri yok",
                )
                for unit in units
            )
        )
        queue = build_review_queue(
            report,
            assets=_load_localization_assets(glossary, characters),
            minimum_score=minimum_score,
        )
    except (OSError, UnicodeError, TemplateParseError, ValueError) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error
    typer.echo(
        json.dumps(
            [
                {
                    "unit_id": item.unit_id,
                    "score": item.score,
                    "reasons": [reason.value for reason in item.reasons],
                    "source_text": item.source_text,
                    "translated_text": item.translated_text,
                    "file_path": item.file_path,
                    "line_number": item.line_number,
                }
                for item in queue
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command(name="update-report")
def update_report_command(
    previous: Annotated[Path, typer.Argument(help="Önceki Ren'Py şablonu.")],
    current: Annotated[Path, typer.Argument(help="Güncel Ren'Py şablonu.")],
) -> None:
    """İki oyun sürümündeki eklenen, silinen ve değişen metinleri karşılaştırır."""
    try:
        changes = compare_inventories(
            parse_template(previous.expanduser().resolve()),
            parse_template(current.expanduser().resolve()),
        )
    except (OSError, UnicodeError, TemplateParseError, ValueError) as error:
        console.print(f"[red]Hata:[/red] {error}")
        raise typer.Exit(code=2) from error
    typer.echo(
        json.dumps(
            [
                {
                    "unit_id": change.unit_id,
                    "kind": change.kind.value,
                    "previous_source": (
                        change.previous.source_text if change.previous is not None else None
                    ),
                    "current_source": (
                        change.current.source_text if change.current is not None else None
                    ),
                }
                for change in changes
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Sürümü gösterip çıkar.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """RenTR ana komutu."""
    del version


def run() -> int:
    """Testable process entry point."""
    app()
    return 0


if __name__ == "__main__":
    sys.exit(run())
