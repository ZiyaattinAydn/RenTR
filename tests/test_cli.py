import json
import pickle
import struct
import subprocess
import zlib
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from rentr import __version__
from rentr.cli import app

runner = CliRunner()
FIXTURE = Path(__file__).parent / "fixtures" / "first_choice_a.rpy"
TRANSLATED_FIXTURE = Path(__file__).parent / "fixtures" / "existing_translation_a.rpy"
EDGE_FIXTURE = Path(__file__).parent / "fixtures" / "parser_edge_cases.rpy"
RENDERED_FIXTURE = Path(__file__).parent / "fixtures" / "parser_edge_cases.rendered.rpy"
SOURCE_GAME = Path(__file__).parent / "fixtures" / "games" / "source_game"
PACKAGED_GAME = Path(__file__).parent / "fixtures" / "games" / "packaged_game"


def _windows_sdk(tmp_path: Path) -> Path:
    sdk = tmp_path / "renpy-sdk"
    launcher = sdk / "lib" / "py3-windows-x86_64" / "python.exe"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("fixture", encoding="utf-8")
    (sdk / "renpy.py").write_text("# fixture\n", encoding="utf-8")
    return sdk


def _executable_posix_sdk(tmp_path: Path) -> Path:
    sdk = tmp_path / "renpy-sdk"
    sdk.mkdir()
    launcher = sdk / "renpy.sh"
    launcher.write_text(
        "#!/bin/sh\n"
        'mkdir -p "$1/game/tl/$3"\n'
        'printf \'translate turkish strings:\\n\\n    old "Start"\\n    new ""\\n\' '
        '> "$1/game/tl/$3/script.rpy"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    return sdk


def _successful_sdk_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
    command = cast(tuple[str, ...], args[0])
    project_root = Path(command[-3])
    language = command[-1]
    translation = project_root / "game" / "tl" / language / "script.rpy"
    translation.parent.mkdir(parents=True, exist_ok=True)
    translation.write_text(
        'translate turkish strings:\n\n    old "Start"\n    new ""\n',
        encoding="utf-8",
    )
    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


def _packaged_game(tmp_path: Path) -> Path:
    game_root = tmp_path / "Packaged"
    game_dir = game_root / "game"
    game_dir.mkdir(parents=True)
    key = 0x12345678
    rpc2_header = b"RENPY RPC2"
    rpc2_offset = len(rpc2_header) + struct.calcsize("<III") * 2
    payload = b"opaque"
    rpyc = (
        rpc2_header
        + struct.pack("<III", 1, rpc2_offset, len(payload))
        + struct.pack("<III", 0, 0, 0)
        + payload
    )
    header_size = len(b"RPA-3.0 0000000000000000 00000000\n")
    content = bytearray(b"\x00" * header_size)
    offset = len(content)
    content.extend(rpyc)
    index_offset = len(content)
    index = {"script.rpyc": [(offset ^ key, len(rpyc) ^ key)]}
    content[:header_size] = f"RPA-3.0 {index_offset:016x} {key:08x}\n".encode()
    content.extend(zlib.compress(pickle.dumps(index, protocol=2)))
    (game_dir / "scripts.rpa").write_bytes(content)
    return game_root


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_doctor_reports_ready_environment() -> None:
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "Temel ortam hazır" in result.stdout


def test_doctor_rejects_missing_project(tmp_path: Path) -> None:
    missing = tmp_path / "missing-game"

    result = runner.invoke(app, ["doctor", "--project", str(missing)])

    assert result.exit_code == 2
    assert "Proje klasörü bulunamadı" in result.stdout


def test_inventory_emits_two_json_units_for_choice_a() -> None:
    result = runner.invoke(app, ["inventory", str(FIXTURE)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [item["source_text"] for item in payload] == [
        "Hello, [player_name]!",
        "Start Game",
    ]
    assert [item["kind"] for item in payload] == ["dialogue", "string"]


def test_inventory_keeps_existing_translations_without_marking_them_pending() -> None:
    result = runner.invoke(app, ["inventory", str(TRANSLATED_FIXTURE)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [item["translated_text"] for item in payload] == [
        "Tekrar hoş geldin.",
        "Tercihler",
    ]
    assert [item["translated_segments"] for item in payload] == [
        ["Tekrar hoş geldin."],
        ["Tercihler"],
    ]
    assert [item["status"] for item in payload] == ["translated", "translated"]


def test_inspect_game_accepts_game_without_tl_turkish() -> None:
    result = runner.invoke(app, ["inspect-game", str(SOURCE_GAME)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["mode"] == "source"
    assert payload["translation_file_count"] == 0
    assert payload["next_action"] == "generate_translation_templates"


def test_workspace_plan_is_dry_run_and_excludes_media(tmp_path: Path) -> None:
    destination = tmp_path / "isolated-workspace"

    result = runner.invoke(
        app,
        ["workspace-plan", str(PACKAGED_GAME), "--destination", str(destination)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["writes_to_original_game"] is False
    assert payload["file_count"] == 2
    assert payload["files"] == ["game/archive.rpa", "game/script.rpyc"]
    assert not destination.exists()


def test_translation_plan_is_non_executing_and_does_not_create_workspace(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "isolated-workspace"
    sdk_root = _windows_sdk(tmp_path)

    result = runner.invoke(
        app,
        [
            "translation-plan",
            str(SOURCE_GAME),
            "--workspace",
            str(destination),
            "--sdk",
            str(sdk_root),
            "--target-platform",
            "windows",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["target_platform"] == "windows"
    assert payload["args"] == [
        str((sdk_root / "lib" / "py3-windows-x86_64" / "python.exe").resolve()),
        str((sdk_root / "renpy.py").resolve()),
        str(destination.resolve()),
        "translate",
        "turkish",
    ]
    assert payload["dry_run"] is True
    assert payload["execution_enabled"] is False
    assert payload["writes_to_original_game"] is False
    assert not destination.exists()
    assert not (SOURCE_GAME / "game" / "tl" / "turkish").exists()


def test_render_template_prints_canonical_preview_without_writing_files() -> None:
    before = EDGE_FIXTURE.read_bytes()

    result = runner.invoke(app, ["render-template", str(EDGE_FIXTURE)])

    assert result.exit_code == 0
    assert result.stdout == RENDERED_FIXTURE.read_text(encoding="utf-8")
    assert EDGE_FIXTURE.read_bytes() == before


def test_prepare_translation_executes_sdk_only_in_isolated_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    sdk = _executable_posix_sdk(tmp_path)

    monkeypatch.setattr("rentr.renpy_cli.subprocess.run", _successful_sdk_run)

    result = runner.invoke(
        app,
        [
            "prepare-translation",
            str(SOURCE_GAME),
            "--workspace",
            str(workspace),
            "--sdk",
            str(sdk),
            "--target-platform",
            "posix",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["writes_to_original_game"] is False
    assert payload["generated_files"] == [
        str(workspace / "game" / "tl" / "turkish" / "script.rpy")
    ]
    assert not (SOURCE_GAME / "game" / "tl" / "turkish").exists()


def test_package_cli_builds_plans_installs_and_rolls_back(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    translation = workspace / "game" / "tl" / "turkish"
    translation.mkdir(parents=True)
    (translation / "script.rpy").write_text(
        'translate turkish strings:\n\n    old "Start"\n    new "Başla"\n',
        encoding="utf-8",
    )
    game = tmp_path / "game-install"
    (game / "game").mkdir(parents=True)

    build_result = runner.invoke(app, ["build-package", str(workspace)])

    assert build_result.exit_code == 0
    build_payload = json.loads(build_result.stdout)
    package = Path(build_payload["package"])
    assert build_payload["writes_to_original_game"] is False
    assert package.is_file()

    plan_result = runner.invoke(app, ["install-package", str(package), str(game)])

    assert plan_result.exit_code == 0
    plan_payload = json.loads(plan_result.stdout)
    assert plan_payload["applied"] is False
    assert plan_payload["writes_to_original_game"] is False
    assert not (game / "game" / "tl" / "turkish" / "script.rpy").exists()

    install_result = runner.invoke(
        app,
        ["install-package", str(package), str(game), "--apply"],
    )

    assert install_result.exit_code == 0
    install_payload = json.loads(install_result.stdout)
    assert install_payload["applied"] is True
    assert install_payload["writes_to_original_game"] is True
    installed = game / "game" / "tl" / "turkish" / "script.rpy"
    assert installed.is_file()

    receipt = install_payload["receipt"]
    rollback_plan = runner.invoke(
        app,
        ["rollback-install", str(game), "--receipt", receipt],
    )
    assert rollback_plan.exit_code == 0
    assert json.loads(rollback_plan.stdout)["applied"] is False
    assert installed.is_file()

    rollback = runner.invoke(
        app,
        ["rollback-install", str(game), "--receipt", receipt, "--apply"],
    )
    assert rollback.exit_code == 0
    assert json.loads(rollback.stdout)["receipt_removed"] is True
    assert not installed.exists()


def test_runtime_research_cli_reports_no_game_actions() -> None:
    result = runner.invoke(app, ["runtime-research-report", str(SOURCE_GAME)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["writes_to_game"] is False
    assert payload["starts_game_process"] is False
    strategies = {item["strategy"]: item for item in payload["strategies"]}
    assert strategies["static-patch"]["verdict"] == "recommended"
    assert strategies["process-hook"]["verdict"] == "rejected"
    assert strategies["process-hook"]["requires_process_injection"] is True


def test_runtime_simulation_cli_uses_memory_without_capture_or_hook(tmp_path: Path) -> None:
    events = tmp_path / "events.txt"
    events.write_text("Hello, [player_name]!\nHello, [player_name]!\n", encoding="utf-8")
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps({"Hello, __RENTR_0000__!": "Merhaba, __RENTR_0000__!"}),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["runtime-simulate", str(events), "--mock-map", str(mapping)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["provider_calls"] == 1
    assert [frame["origin"] for frame in payload["frames"]] == ["provider", "memory"]
    assert payload["writes_to_game"] is False
    assert payload["captures_screen"] is False
    assert payload["injects_process"] is False


def test_translate_estimate_never_calls_provider(tmp_path: Path) -> None:
    memory = tmp_path / "memory.sqlite3"

    result = runner.invoke(
        app,
        ["translate-estimate", str(FIXTURE), "--memory", str(memory)],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "total_units": 2,
        "existing_units": 0,
        "cached_units": 0,
        "passthrough_units": 0,
        "provider_units": 2,
        "provider_characters": len("Hello, [player_name]!") + len("Start Game"),
    }


def test_translate_template_previews_then_atomically_applies(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = workspace / "game" / "tl" / "turkish" / "script.rpy"
    mapping = tmp_path / "mock.json"
    mapping.write_text(
        json.dumps(
            {
                "Hello, __RENTR_0000__!": "Merhaba, __RENTR_0000__!",
                "Start Game": "Oyuna Başla",
            }
        ),
        encoding="utf-8",
    )
    source_before = FIXTURE.read_bytes()
    arguments = [
        "translate-template",
        str(FIXTURE),
        "--workspace",
        str(workspace),
        "--output",
        "game/tl/turkish/script.rpy",
        "--mock-map",
        str(mapping),
    ]

    preview = runner.invoke(app, arguments)

    assert preview.exit_code == 0
    preview_payload = json.loads(preview.stdout)
    assert preview_payload["applied"] is False
    assert "Oyuna Başla" in preview_payload["preview_diff"]
    assert not output.exists()

    applied = runner.invoke(app, [*arguments, "--apply"])

    assert applied.exit_code == 0
    assert json.loads(applied.stdout)["applied"] is True
    assert "Merhaba, [player_name]!" in output.read_text(encoding="utf-8")
    assert FIXTURE.read_bytes() == source_before


def test_project_check_validates_assets_without_printing_secret(
    tmp_path: Path,
) -> None:
    glossary = tmp_path / "glossary.json"
    glossary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": "1.0",
                "terms": [{"source": "Start", "target": "Başla"}],
            }
        ),
        encoding="utf-8",
    )
    characters = tmp_path / "characters.json"
    characters.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "characters": [
                    {"speaker": "eileen", "display_name": "Eileen", "address_style": "sen"}
                ],
            }
        ),
        encoding="utf-8",
    )
    config = tmp_path / "rentr.toml"
    config.write_text(
        'schema_version = 1\n[project]\nname = "Demo"\n'
        '[provider]\ntype = "openai-compatible"\nmodel = "model"\n'
        'base_url = "https://example.test/v1"\napi_key_env = "DEMO_KEY"\n'
        '[paths]\nglossary = "glossary.json"\ncharacters = "characters.json"\n',
        encoding="utf-8",
    )

    result = runner.invoke(app, ["project-check", str(config)], env={"DEMO_KEY": "secret"})

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["glossary_term_count"] == 1
    assert payload["character_count"] == 1
    assert payload["api_key_available"] is True
    assert "secret" not in result.stdout


def test_review_queue_reports_existing_translation_risks(tmp_path: Path) -> None:
    glossary = tmp_path / "glossary.json"
    glossary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": "1.0",
                "terms": [{"source": "Preferences", "target": "Ayarlar"}],
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["review-queue", str(TRANSLATED_FIXTURE), "--glossary", str(glossary)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["unit_id"].startswith("strings:")
    assert "glossary_mismatch" in payload[0]["reasons"]


def test_update_report_compares_two_template_versions() -> None:
    result = runner.invoke(
        app,
        ["update-report", str(FIXTURE), str(TRANSLATED_FIXTURE)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert {item["kind"] for item in payload} >= {"added", "removed"}


def test_local_model_check_is_offline_by_default() -> None:
    result = runner.invoke(
        app,
        [
            "local-model-check",
            "--model",
            "translator:7b",
            "--minimum-memory",
            "1",
            "--recommended-memory",
            "2",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["model"] == "translator:7b"
    assert payload["installed_models"] is None
    assert payload["suitability"] in {"suitable", "limited", "insufficient", "unknown"}


def test_prepare_packaged_extracts_scripts_only_to_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    game_root = _packaged_game(tmp_path)
    workspace = tmp_path / "workspace"
    sdk = _executable_posix_sdk(tmp_path)

    monkeypatch.setattr("rentr.renpy_cli.subprocess.run", _successful_sdk_run)

    result = runner.invoke(
        app,
        [
            "prepare-packaged",
            str(game_root),
            "--workspace",
            str(workspace),
            "--sdk",
            str(sdk),
            "--target-platform",
            "posix",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["needs_compiled_backend"] is True
    assert payload["compiled_formats"] == ["rpc2"]
    assert payload["writes_to_original_game"] is False
    assert payload["generated_files"] == [
        str(workspace / "game" / "tl" / "turkish" / "script.rpy")
    ]
    assert (workspace / "game" / "script.rpyc").is_file()
    assert not (game_root / "game" / "script.rpyc").exists()
