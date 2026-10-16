from __future__ import annotations

from pathlib import Path

from rentr.memory import TranslationMemory
from rentr.parser import parse_template
from rentr.pipeline import TranslationEngine
from rentr.providers import MockTranslationProvider
from rentr.renderer import render_template
from rentr.writer import apply_safe_write, plan_safe_write


def test_template_to_validated_atomic_turkish_output(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "first_choice_a.rpy"
    units = parse_template(fixture)
    provider = MockTranslationProvider(
        {
            "Hello, __RENTR_0000__!": "Merhaba, __RENTR_0000__!",
            "Start Game": "Oyuna Başla",
        }
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = workspace / "game" / "tl" / "turkish" / "script.rpy"

    with TranslationMemory(workspace / ".rentr" / "memory.sqlite3") as memory:
        report = TranslationEngine(provider=provider, memory=memory).translate(units)
        rendered = render_template(report.translated_units)
        receipt = apply_safe_write(
            plan_safe_write(output, rendered, workspace_root=workspace)
        )

    reparsed = parse_template(output)
    assert report.failed_count == 0
    assert receipt.output_path == output
    assert [unit.translated_text for unit in reparsed] == [
        "Merhaba, [player_name]!",
        "Oyuna Başla",
    ]
