from __future__ import annotations

from pathlib import Path

from rentr.memory import TranslationMemory
from rentr.parser import parse_template
from rentr.pipeline import TranslationEngine
from rentr.providers import TranslationRequest, TranslationResponse
from rentr.renderer import render_template

FIXTURES = Path(__file__).parent / "fixtures"


class _FixtureProvider:
    name = "fixture-provider"

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        return TranslationResponse(f"TR: {request.source_text}", self.name, "offline")


def test_three_independent_fixtures_complete_semantic_pipeline(tmp_path: Path) -> None:
    fixture_names = (
        "first_choice_a.rpy",
        "existing_translation_a.rpy",
        "parser_edge_cases.rpy",
    )
    for fixture_name in fixture_names:
        source_units = parse_template(FIXTURES / fixture_name)
        with TranslationMemory(tmp_path / f"{fixture_name}.sqlite3") as memory:
            report = TranslationEngine(provider=_FixtureProvider(), memory=memory).translate(
                source_units
            )
        assert report.failed_count == 0
        rendered = render_template(report.translated_units)
        output = tmp_path / f"rendered-{fixture_name}"
        output.write_text(rendered, encoding="utf-8")
        reparsed = parse_template(output)
        assert [unit.unit_id for unit in reparsed] == [unit.unit_id for unit in source_units]
        assert all(unit.translated_text is not None for unit in reparsed)
