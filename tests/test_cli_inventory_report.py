from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rentr.cli import app

runner = CliRunner()


def test_inventory_report_separates_provider_and_passthrough(tmp_path: Path) -> None:
    template = tmp_path / "script.rpy"
    template.write_text(
        """translate turkish strings:

    old "{image=icon_pay.webp}"
    new ""

    old "Start Game"
    new ""

    old "Start Game"
    new ""
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["inventory-report", str(tmp_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["total_units"] == 3
    assert payload["provider_units"] == 2
    assert payload["passthrough_units"] == 1
    assert payload["unique_provider_source_texts"] == 1
    assert payload["duplicate_provider_occurrences"] == 1
    assert payload["passthrough_reasons"] == {"control_only": 1}


def test_pilot_report_is_bounded_and_never_calls_provider(tmp_path: Path) -> None:
    template = tmp_path / "script.rpy"
    lines = ["translate turkish strings:", ""]
    for index in range(20):
        lines.extend((f'    old "Menu item {index}"', '    new ""', ""))
    template.write_text("\n".join(lines), encoding="utf-8")

    result = runner.invoke(app, ["pilot-report", str(tmp_path), "--limit", "7"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["requested_limit"] == 7
    assert payload["selected_units"] == 7
    assert len(payload["samples"]) == 7
