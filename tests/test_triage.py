from __future__ import annotations

import pytest

from rentr.triage import UnitDisposition, classify_source_text


@pytest.mark.parametrize(
    "source",
    [
        "{image=icon_pay.webp}",
        "{image=icon_pay.webp}{image=icon_pay.webp}",
        "[player_name]",
        "%(score)03d",
        "...",
        "123 / 456",
        "https://example.com/page",
    ],
)
def test_passthroughs_nonlinguistic_or_control_only_text(source: str) -> None:
    assert classify_source_text(source).disposition is UnitDisposition.PASSTHROUGH


@pytest.mark.parametrize(
    "source",
    [
        "What will you do?",
        "{b}What will you do?{/b}",
        "Hello, [player_name]!",
        "Pay {image=icon_pay.webp} now",
        "5 minutes",
    ],
)
def test_keeps_visible_language_for_provider(source: str) -> None:
    assert classify_source_text(source).disposition is UnitDisposition.PROVIDER


def test_malformed_control_syntax_is_not_silently_skipped() -> None:
    result = classify_source_text("Hello [name")

    assert result.disposition is UnitDisposition.PROVIDER
    assert result.reason == "protection_error"
