from __future__ import annotations

from pathlib import Path

import pytest

from rentr.config import ConfigError, ProviderType, load_project_config


def _config_text(*, extra_provider: str = "") -> str:
    return (
        'schema_version = 1\n\n[project]\nname = "Demo"\n\n'
        '[provider]\ntype = "openai-compatible"\nmodel = "translator"\n'
        'base_url = "https://provider.example/v1"\napi_key_env = "RENTR_API_KEY"\n'
        f"{extra_provider}\n[paths]\nglossary = \"glossary.json\"\n"
        'characters = "characters.json"\nmemory = ".rentr/memory.sqlite3"\n'
    )


def test_loads_relative_paths_and_reads_secret_only_from_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "rentr.toml"
    path.write_text(_config_text(), encoding="utf-8")
    monkeypatch.setenv("RENTR_API_KEY", "runtime-secret")

    config = load_project_config(path)

    assert config.provider_type is ProviderType.OPENAI_COMPATIBLE
    assert config.glossary_path == (tmp_path / "glossary.json").resolve()
    assert config.read_api_key() == "runtime-secret"
    assert "runtime-secret" not in str(config.sanitized_record())


def test_rejects_inline_api_key(tmp_path: Path) -> None:
    path = tmp_path / "rentr.toml"
    path.write_text(_config_text(extra_provider='api_key = "must-not-be-here"'), encoding="utf-8")

    with pytest.raises(ConfigError, match="Gizli"):
        load_project_config(path)


def test_reports_missing_secret_without_exposing_any_value(tmp_path: Path) -> None:
    path = tmp_path / "rentr.toml"
    path.write_text(_config_text(), encoding="utf-8")
    config = load_project_config(path)

    with pytest.raises(ConfigError, match="RENTR_API_KEY"):
        config.read_api_key()
