"""Fail-closed project configuration without secrets on disk."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ConfigError(ValueError):
    """Raised when a project configuration is malformed or stores a secret."""


class ProviderType(StrEnum):
    OPENAI_COMPATIBLE = "openai-compatible"
    OLLAMA = "ollama"


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    path: Path
    project_name: str
    provider_type: ProviderType
    model: str
    base_url: str
    api_key_env: str | None
    glossary_path: Path | None
    characters_path: Path | None
    memory_path: Path

    def read_api_key(self) -> str | None:
        if self.api_key_env is None:
            return None
        value = os.environ.get(self.api_key_env)
        if not value:
            raise ConfigError(f"Gerekli ortam değişkeni ayarlı değil: {self.api_key_env}")
        return value

    def sanitized_record(self) -> dict[str, object]:
        return {
            "project_name": self.project_name,
            "provider_type": self.provider_type.value,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "api_key_available": bool(
                self.api_key_env is None or os.environ.get(self.api_key_env)
            ),
            "glossary_path": str(self.glossary_path) if self.glossary_path else None,
            "characters_path": str(self.characters_path) if self.characters_path else None,
            "memory_path": str(self.memory_path),
        }


def _relative_path(root: Path, value: object, *, field: str) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{field} geçerli bir yol olmalı")
    path = Path(value)
    return (path if path.is_absolute() else root / path).resolve()


def _reject_inline_secrets(payload: object, *, path: str = "root") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key)
            if key_text.casefold() in {"api_key", "secret", "token", "password"}:
                raise ConfigError(
                    f"Gizli değer yapılandırma dosyasına yazılamaz: {path}.{key_text}"
                )
            _reject_inline_secrets(value, path=f"{path}.{key_text}")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            _reject_inline_secrets(value, path=f"{path}[{index}]")


def load_project_config(path: Path) -> ProjectConfig:
    resolved = path.expanduser().resolve()
    try:
        payload = tomllib.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Proje yapılandırması okunamadı: {resolved}: {error}") from error
    _reject_inline_secrets(payload)
    if payload.get("schema_version") != 1:
        raise ConfigError("Desteklenmeyen proje yapılandırma şeması")

    project = payload.get("project")
    provider = payload.get("provider")
    paths = payload.get("paths", {})
    if (
        not isinstance(project, dict)
        or not isinstance(provider, dict)
        or not isinstance(paths, dict)
    ):
        raise ConfigError("project, provider ve paths TOML tabloları geçerli olmalı")
    name = project.get("name")
    provider_type = provider.get("type")
    model = provider.get("model")
    base_url = provider.get("base_url")
    api_key_env = provider.get("api_key_env")
    if (
        not isinstance(name, str)
        or not name.strip()
        or not isinstance(provider_type, str)
        or not isinstance(model, str)
        or not model.strip()
        or not isinstance(base_url, str)
        or not base_url.strip()
        or (api_key_env is not None and not isinstance(api_key_env, str))
    ):
        raise ConfigError("Proje veya sağlayıcı alanları eksik/geçersiz")
    try:
        parsed_provider = ProviderType(provider_type)
    except ValueError as error:
        raise ConfigError(f"Desteklenmeyen sağlayıcı türü: {provider_type}") from error
    if parsed_provider is ProviderType.OPENAI_COMPATIBLE and not api_key_env:
        raise ConfigError("OpenAI uyumlu sağlayıcı api_key_env gerektirir")

    root = resolved.parent
    glossary = _relative_path(root, paths.get("glossary"), field="paths.glossary")
    characters = _relative_path(root, paths.get("characters"), field="paths.characters")
    memory = _relative_path(
        root,
        paths.get("memory", ".rentr/memory.sqlite3"),
        field="paths.memory",
    )
    if memory is None:  # pragma: no cover - default invariant
        raise ConfigError("memory yolu gerekli")
    return ProjectConfig(
        path=resolved,
        project_name=name,
        provider_type=parsed_provider,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        glossary_path=glossary,
        characters_path=characters,
        memory_path=memory,
    )
