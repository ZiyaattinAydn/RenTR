from __future__ import annotations

from pathlib import Path

from rentr.desktop.workflow import (
    apply_desktop_preview,
    apply_desktop_project_preview,
    prepare_game_for_desktop,
    preview_project_translation,
    preview_template_translation,
)
from rentr.providers import MockTranslationProvider
from rentr.renpy_cli import TargetPlatform

GAMES = Path(__file__).parent / "fixtures" / "games"
FIXTURES = Path(__file__).parent / "fixtures"


def test_resume_game_can_be_prepared_previewed_and_applied_without_terminal(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    prepared = prepare_game_for_desktop(
        GAMES / "resume_game",
        workspace,
        target_platform=TargetPlatform.POSIX,
    )
    source = prepared.templates[0].read_text(encoding="utf-8")
    provider = MockTranslationProvider({})

    preview = preview_template_translation(
        prepared.templates[0],
        workspace,
        provider=provider,
    )
    receipt = apply_desktop_preview(preview)

    assert receipt.output_path.is_file()
    assert provider.calls == []
    assert "translate turkish" in source
    assert not (GAMES / "resume_game" / "game" / "tl" / "turkish" / "rentr_output.rpy").exists()


def test_project_preview_translates_and_applies_every_template(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    translation = workspace / "game" / "tl" / "turkish"
    nested = translation / "chapter"
    nested.mkdir(parents=True)
    first = translation / "script.rpy"
    second = nested / "existing.rpy"
    first.write_bytes((FIXTURES / "first_choice_a.rpy").read_bytes())
    second.write_bytes((FIXTURES / "existing_translation_a.rpy").read_bytes())
    provider = MockTranslationProvider(
        {
            "Hello, __RENTR_0000__!": "Merhaba, __RENTR_0000__!",
            "Start Game": "Oyuna Başla",
        }
    )

    preview = preview_project_translation(
        (first, second),
        workspace,
        provider=provider,
    )

    assert preview.results_count == 4
    assert len(provider.calls) == 2
    assert "Oyuna Başla" not in first.read_text(encoding="utf-8")
    receipts = apply_desktop_project_preview(preview)
    assert len(receipts) == 2
    assert "Oyuna Başla" in first.read_text(encoding="utf-8")
    assert "Tercihler" in second.read_text(encoding="utf-8")
