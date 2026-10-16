from hashlib import sha256
from pathlib import Path

import pytest

from rentr.providers import MockTranslationProvider
from rentr.runtime_research import (
    OverlayOrigin,
    ResearchVerdict,
    RuntimeOverlaySimulator,
    RuntimeResearchError,
    RuntimeStrategy,
    assess_runtime_strategies,
    load_text_events,
)

GAMES = Path(__file__).parent / "fixtures" / "games"


def _tree_hash(root: Path) -> str:
    digest = sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_runtime_report_is_read_only_and_rejects_process_hook() -> None:
    game = GAMES / "source_game"
    before = _tree_hash(game)

    report = assess_runtime_strategies(game)

    assert report.writes_to_game is False
    assert report.starts_game_process is False
    assert _tree_hash(game) == before
    assessments = {item.strategy: item for item in report.strategies}
    assert assessments[RuntimeStrategy.STATIC_PATCH].verdict is ResearchVerdict.RECOMMENDED
    assert (
        assessments[RuntimeStrategy.RENPY_CLIPBOARD].verdict
        is ResearchVerdict.RESEARCH_ONLY
    )
    hook = assessments[RuntimeStrategy.PROCESS_HOOK]
    assert hook.verdict is ResearchVerdict.REJECTED
    assert hook.requires_process_injection is True


def test_overlay_simulator_protects_tokens_and_deduplicates_events() -> None:
    provider = MockTranslationProvider(
        {"Hello, __RENTR_0000__!": "Merhaba, __RENTR_0000__!"}
    )
    simulator = RuntimeOverlaySimulator(provider)

    frames = simulator.simulate(("Hello, [player_name]!", "Hello, [player_name]!"))

    assert [frame.translated_text for frame in frames] == [
        "Merhaba, [player_name]!",
        "Merhaba, [player_name]!",
    ]
    assert [frame.origin for frame in frames] == [
        OverlayOrigin.PROVIDER,
        OverlayOrigin.MEMORY,
    ]
    assert len(provider.calls) == 1


def test_overlay_simulator_rejects_empty_or_oversized_text() -> None:
    simulator = RuntimeOverlaySimulator(MockTranslationProvider({}), maximum_text_length=5)

    with pytest.raises(RuntimeResearchError, match="boş"):
        simulator.translate("  ")
    with pytest.raises(RuntimeResearchError, match="sınırını"):
        simulator.translate("123456")


def test_load_text_events_is_bounded_and_rejects_blank_lines(tmp_path: Path) -> None:
    fixture = tmp_path / "events.txt"
    fixture.write_text("First line\n\nSecond line\n", encoding="utf-8")

    with pytest.raises(RuntimeResearchError, match="boş satır"):
        load_text_events(fixture)

    fixture.write_text("First line\nSecond line\n", encoding="utf-8")
    assert load_text_events(fixture) == ("First line", "Second line")
