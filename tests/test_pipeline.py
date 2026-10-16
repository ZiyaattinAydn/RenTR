from __future__ import annotations

from pathlib import Path

from rentr.domain import TranslationKind, TranslationStatus, TranslationUnit
from rentr.localization import (
    AddressStyle,
    CharacterCard,
    Glossary,
    GlossaryEntry,
    LocalizationAssets,
)
from rentr.memory import TranslationMemory
from rentr.pipeline import RetryPolicy, TranslationEngine, TranslationOrigin
from rentr.providers import (
    CandidateDecision,
    CandidateSelectionRequest,
    CandidateSelectionResponse,
    MockTranslationProvider,
    SemanticRepairRequest,
    SemanticRepairResponse,
    TemporaryProviderError,
    TranslationRequest,
    TranslationResponse,
)


def _unit(
    unit_id: str,
    source: str,
    *,
    translated: str | None = None,
    label: str | None = "start",
) -> TranslationUnit:
    return TranslationUnit(
        unit_id=unit_id,
        source_text=source,
        file_path=Path("script.rpy"),
        line_number=1,
        kind=TranslationKind.DIALOGUE,
        speaker="eileen",
        label=label,
        translated_text=translated,
        status=(TranslationStatus.TRANSLATED if translated else TranslationStatus.PENDING),
    )


def test_translates_with_protection_context_and_cache(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "Hello, [player_name]!")
    provider = MockTranslationProvider(
        {"Hello, __RENTR_0000__!": "Merhaba, __RENTR_0000__!"}
    )
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        engine = TranslationEngine(provider=provider, memory=memory)

        first = engine.translate([unit]).results[0]
        second = engine.translate([unit]).results[0]

    assert first.translated_text == "Merhaba, [player_name]!"
    assert first.origin is TranslationOrigin.PROVIDER
    assert first.materialize().status is TranslationStatus.VALIDATED
    assert second.origin is TranslationOrigin.MEMORY
    assert len(provider.calls) == 1
    assert provider.calls[0].context.speaker == "eileen"


def test_passthrough_control_only_unit_without_provider_call(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "{image=icon_pay.webp}")
    provider = MockTranslationProvider({})
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(provider=provider, memory=memory).translate([unit]).results[0]

    assert result.translated_text == unit.source_text
    assert result.origin is TranslationOrigin.PASSTHROUGH
    assert result.materialize().translated_text == unit.source_text
    assert provider.calls == []


def test_passthrough_units_do_not_pollute_dialogue_context(tmp_path: Path) -> None:
    previous = _unit("start_11111111", "Hello")
    technical = _unit("start_22222222", "{image=icon_pay.webp}")
    current = _unit("start_33333333", "How are you?")
    provider = MockTranslationProvider({"Hello": "Merhaba", "How are you?": "Nasılsın?"})
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        report = TranslationEngine(provider=provider, memory=memory).translate(
            [previous, technical, current]
        )

    assert report.failed_count == 0
    assert len(provider.calls) == 2
    assert provider.calls[1].context.previous_source_text == "Hello"


def test_preserves_existing_human_translation_without_provider_call(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "Welcome", translated="Hoş geldin")
    provider = MockTranslationProvider({})
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(provider=provider, memory=memory).translate([unit]).results[0]

    assert result.origin is TranslationOrigin.EXISTING
    assert result.materialize() is unit
    assert provider.calls == []


class _FlakyProvider:
    name = "flaky"

    def __init__(self) -> None:
        self.attempts = 0

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        self.attempts += 1
        if self.attempts < 3:
            raise TemporaryProviderError("later")
        return TranslationResponse(request.source_text, self.name, "test")


def test_retries_temporary_errors_with_bounded_backoff(tmp_path: Path) -> None:
    provider = _FlakyProvider()
    sleeps: list[float] = []
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(
            provider=provider,
            memory=memory,
            retry_policy=RetryPolicy(max_attempts=3, initial_delay_seconds=0.25),
            sleeper=sleeps.append,
        ).translate([_unit("start_deadbeef", "Hello")]).results[0]

    assert result.succeeded
    assert result.attempts == 3
    assert sleeps == [0.25, 0.5]


def test_token_corruption_fails_closed_and_is_not_cached(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "Hello [name]")
    provider = MockTranslationProvider({"Hello __RENTR_0000__": "Merhaba"})
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(provider=provider, memory=memory).translate([unit]).results[0]

        assert not result.succeeded
        assert result.origin is TranslationOrigin.FAILED
        assert memory.get(unit) is None


def test_partial_failure_is_resumable_from_saved_success(tmp_path: Path) -> None:
    first = _unit("start_11111111", "Hello")
    second = _unit("start_22222222", "Goodbye")
    provider = MockTranslationProvider({"Hello": "Merhaba"})
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        engine = TranslationEngine(provider=provider, memory=memory)
        report = engine.translate([first, second])
        resumed_provider = MockTranslationProvider({"Goodbye": "Güle güle"})
        resumed = TranslationEngine(provider=resumed_provider, memory=memory).translate(
            [first, second]
        )

    assert report.failed_count == 1
    assert [result.origin for result in resumed.results] == [
        TranslationOrigin.MEMORY,
        TranslationOrigin.PROVIDER,
    ]
    assert len(resumed_provider.calls) == 1


def test_builds_surrounding_line_and_similarity_context(tmp_path: Path) -> None:
    previous = _unit("start_11111111", "Start Game")
    current = _unit("start_22222222", "Start New Game")
    following = _unit("start_33333333", "Continue")
    provider = MockTranslationProvider(
        {
            "Start Game": "Oyuna Başla",
            "Start New Game": "Yeni Oyuna Başla",
            "Continue": "Devam Et",
        }
    )
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        report = TranslationEngine(provider=provider, memory=memory).translate(
            [previous, current, following]
        )

    assert report.failed_count == 0
    assert provider.calls[0].context.next_source_text == "Start New Game"
    assert provider.calls[1].context.previous_source_text == "Start Game"
    assert provider.calls[1].context.next_source_text == "Continue"
    assert provider.calls[1].context.suggestions[0].translated_text == "Oyuna Başla"


def test_estimate_separates_existing_cached_and_provider_work(tmp_path: Path) -> None:
    existing = _unit("start_11111111", "One", translated="Bir")
    cached = _unit("start_22222222", "Two")
    pending = _unit("start_33333333", "Three")
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        memory.save(cached, "İki", provider="human")
        estimate = TranslationEngine(
            provider=MockTranslationProvider({}),
            memory=memory,
        ).estimate([existing, cached, pending])

    assert estimate.total_units == 3
    assert estimate.existing_units == 1
    assert estimate.cached_units == 1
    assert estimate.passthrough_units == 0
    assert estimate.provider_units == 1
    assert estimate.provider_characters == len("Three")


def test_injects_matching_glossary_and_character_voice(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "Save the game")
    provider = MockTranslationProvider({"Save the game": "Oyunu Kaydet"})
    assets = LocalizationAssets(
        glossary=Glossary("1", (GlossaryEntry("Save", "Kaydet"),)),
        characters=(
            CharacterCard(
                speaker="eileen",
                display_name="Eileen",
                address_style=AddressStyle.SEN,
                traits=("warm",),
            ),
        ),
    )
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        TranslationEngine(
            provider=provider,
            memory=memory,
            localization=assets,
        ).translate([unit])

    context = provider.calls[0].context
    assert context.glossary[0].required_target == "Kaydet"
    assert context.character is not None
    assert context.character.address_style == "sen"


def test_estimate_counts_passthrough_without_provider_cost(tmp_path: Path) -> None:
    technical = _unit("start_deadbeef", "{image=icon_pay.webp}")
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        estimate = TranslationEngine(
            provider=MockTranslationProvider({}),
            memory=memory,
        ).estimate([technical])

    assert estimate.total_units == 1
    assert estimate.passthrough_units == 1
    assert estimate.provider_units == 0
    assert estimate.provider_characters == 0


def test_translate_selected_keeps_context_from_unselected_units(tmp_path: Path) -> None:
    previous = _unit("start_11111111", "I want you.")
    current = _unit("start_22222222", "Fuck me.")
    following = _unit("start_33333333", "Don't stop.")
    provider = MockTranslationProvider({"Fuck me.": "Sik beni."})
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        report = TranslationEngine(provider=provider, memory=memory).translate_selected(
            [previous, current, following],
            [1],
        )

    assert report.failed_count == 0
    assert len(provider.calls) == 1
    assert provider.calls[0].context.previous_source_text == "I want you."
    assert provider.calls[0].context.next_source_text == "Don't stop."


def test_unexpected_script_corruption_fails_closed_and_is_not_cached(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "Damn! When did you get so good at this?")
    provider = MockTranslationProvider(
        {"Damn! When did you get so good at this?": "TanıANGER! 你的嘴巴什么时候变得这么棒？"}
    )
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(provider=provider, memory=memory).translate([unit]).results[0]

        assert not result.succeeded
        assert result.origin is TranslationOrigin.FAILED
        assert "beklenmeyen yazı sistemi" in (result.error or "")
        assert memory.get(unit) is None


def test_moved_control_cluster_fails_closed_and_is_not_cached(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "I had to-{w=0.5}{nw}")
    provider = MockTranslationProvider(
        {
            "I had to-__RENTR_0000____RENTR_0001__": (
                "Yapmalıydım-__RENTR_0000__gerekti__RENTR_0001__"
            )
        }
    )
    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(provider=provider, memory=memory).translate([unit]).results[0]

        assert not result.succeeded
        assert result.origin is TranslationOrigin.FAILED
        assert "arasına metin" in (result.error or "")
        assert memory.get(unit) is None


class _JudgeProvider:
    name = "judge"

    def __init__(
        self,
        decision: CandidateDecision,
        *,
        confidence: float = 0.95,
        reasons: tuple[str, ...] = ("test_verdict",),
    ) -> None:
        self.decision = decision
        self.confidence = confidence
        self.reasons = reasons
        self.calls: list[CandidateSelectionRequest] = []

    def select(self, request: CandidateSelectionRequest) -> CandidateSelectionResponse:
        self.calls.append(request)
        return CandidateSelectionResponse(
            decision=self.decision,
            confidence=self.confidence,
            reasons=self.reasons,
            provider=self.name,
            model="judge-model",
        )


class _RepairProvider:
    name = "repair"

    def __init__(self, outputs: dict[str, str]) -> None:
        self.outputs = outputs
        self.calls: list[SemanticRepairRequest] = []

    def repair(self, request: SemanticRepairRequest) -> SemanticRepairResponse:
        self.calls.append(request)
        try:
            translated = self.outputs[request.source_text]
        except KeyError as error:
            raise AssertionError(f"unexpected repair request: {request.source_text}") from error
        return SemanticRepairResponse(translated, self.name, "repair-model")


def test_hybrid_repairs_high_risk_semantics_before_cache(tmp_path: Path) -> None:
    unit = _unit(
        "start_deadbeef",
        "There's no shortage of hot girls around him!",
    )
    base = MockTranslationProvider(
        {"There's no shortage of hot girls around him!": "Onun etrafında sıcak kızlar yok!"}
    )
    repair = _RepairProvider(
        {"There's no shortage of hot girls around him!": "Etrafında çekici kız sıkıntısı yok!"}
    )

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(
            provider=base,
            memory=memory,
            repair_provider=repair,
        ).translate([unit]).results[0]
        cached = memory.get(unit)

    assert result.origin is TranslationOrigin.REPAIRED
    assert result.translated_text == "Etrafında çekici kız sıkıntısı yok!"
    assert result.base_translated_text == "Onun etrafında sıcak kızlar yok!"
    assert result.repair_used
    assert result.repair_attempts == 1
    assert "hot_literalized_as_temperature" in result.risk_reasons
    assert cached is not None
    assert cached.translated_text == "Etrafında çekici kız sıkıntısı yok!"
    assert len(repair.calls) == 1


def test_hybrid_salvages_missing_boundary_image_without_repair_call(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "Good night {image=emoji_smile.webp}")
    base = MockTranslationProvider(
        {"Good night __RENTR_0000__": "İyi geceler"}
    )
    repair = _RepairProvider(
        {"Good night __RENTR_0000__": "İyi geceler __RENTR_0000__"}
    )

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(
            provider=base,
            memory=memory,
            repair_provider=repair,
        ).translate([unit]).results[0]

    assert result.origin is TranslationOrigin.PROVIDER
    assert result.translated_text == "İyi geceler {image=emoji_smile.webp}"
    assert not result.repair_attempted
    assert repair.calls == []


def test_hybrid_skips_repair_for_low_risk_clean_translation(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "Developer Menu", label=None)
    base = MockTranslationProvider({"Developer Menu": "Geliştirici Menüsü"})
    repair = _RepairProvider({})

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(
            provider=base,
            memory=memory,
            repair_provider=repair,
        ).translate([unit]).results[0]

    assert result.origin is TranslationOrigin.PROVIDER
    assert not result.repair_attempted
    assert result.risk_score < 45
    assert repair.calls == []


def test_hybrid_rejects_unresolved_hard_semantic_risk(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "Cum in my pussy!")
    base = MockTranslationProvider({"Cum in my pussy!": "Benim içine gir!"})
    repair = _RepairProvider({"Cum in my pussy!": "İçime gel!"})

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(
            provider=base,
            memory=memory,
            repair_provider=repair,
        ).translate([unit]).results[0]
        cached = memory.get(unit)

    assert result.origin is TranslationOrigin.FAILED
    assert "Semantic repair sonrası" in (result.error or "")
    assert "cum_semantics_missing" in (result.error or "")
    assert cached is None


def test_hybrid_repair_receives_full_scene_context(tmp_path: Path) -> None:
    previous = _unit("start_11111111", "I want you.")
    current = _unit("start_22222222", "Fuck me.")
    following = _unit("start_33333333", "Don't stop.")
    base = MockTranslationProvider({"Fuck me.": "Benimle birlikte ol."})
    repair = _RepairProvider({"Fuck me.": "Sik beni."})

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        report = TranslationEngine(
            provider=base,
            memory=memory,
            repair_provider=repair,
        ).translate_selected([previous, current, following], [1])

    assert report.failed_count == 0
    assert report.repaired_count == 1
    assert repair.calls[0].context.previous_source_text == "I want you."
    assert repair.calls[0].context.next_source_text == "Don't stop."
    assert repair.calls[0].risk_reasons


def test_selector_keeps_better_base_when_repair_degrades_soft_risk(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "Damn...! When did you get so good at this?")
    base = MockTranslationProvider(
        {"Damn...! When did you get so good at this?": "Lan...! Ne zaman bu kadar iyi oldun?"}
    )
    repair = _RepairProvider(
        {"Damn...! When did you get so good at this?": "Lan, bu ne kadar usta oldun sen?!"}
    )
    judge = _JudgeProvider(
        CandidateDecision.BASE,
        reasons=("base_more_natural", "meaning_preserved"),
    )

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(
            provider=base,
            memory=memory,
            repair_provider=repair,
            judge_provider=judge,
        ).translate([unit]).results[0]
        cached = memory.get(unit)

    assert result.origin is TranslationOrigin.PROVIDER
    assert result.translated_text == "Lan...! Ne zaman bu kadar iyi oldun?"
    assert result.repair_attempted
    assert not result.repair_used
    assert result.selector_decision is CandidateDecision.BASE
    assert result.selector_model == "judge-model"
    assert result.selector_confidence == 0.95
    assert cached is not None
    assert cached.translated_text == result.translated_text
    assert judge.calls[0].repair_translation == "Lan, bu ne kadar usta oldun sen?!"


def test_selector_uses_repair_only_with_sufficient_confidence(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "Damn, this is hot.")
    base = MockTranslationProvider({"Damn, this is hot.": "Lanet olsun, bu çok çekici."})
    repair = _RepairProvider({"Damn, this is hot.": "Vay be, bu çok seksi."})
    judge = _JudgeProvider(CandidateDecision.REPAIR, confidence=0.91)

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(
            provider=base,
            memory=memory,
            repair_provider=repair,
            judge_provider=judge,
        ).translate([unit]).results[0]

    assert result.origin is TranslationOrigin.REPAIRED
    assert result.translated_text == "Vay be, bu çok seksi."
    assert result.repair_used
    assert result.selector_decision is CandidateDecision.REPAIR


def test_selector_low_confidence_repair_falls_back_to_base(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "Damn, this is hot.")
    base = MockTranslationProvider({"Damn, this is hot.": "Lanet olsun, bu çok çekici."})
    repair = _RepairProvider({"Damn, this is hot.": "Vay be, bu çok seksi."})
    judge = _JudgeProvider(CandidateDecision.REPAIR, confidence=0.60)

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(
            provider=base,
            memory=memory,
            repair_provider=repair,
            judge_provider=judge,
        ).translate([unit]).results[0]

    assert result.origin is TranslationOrigin.PROVIDER
    assert result.translated_text == "Lanet olsun, bu çok çekici."
    assert result.selector_decision is CandidateDecision.BASE
    assert "repair_below_confidence_threshold" in result.selector_reasons


def test_selector_can_reject_two_bad_soft_candidates(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "Damn... what happened?")
    base = MockTranslationProvider({"Damn... what happened?": "Lanet... ne oldu?"})
    repair = _RepairProvider({"Damn... what happened?": "Lan... ne var?"})
    judge = _JudgeProvider(CandidateDecision.REJECT, confidence=0.92)

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(
            provider=base,
            memory=memory,
            repair_provider=repair,
            judge_provider=judge,
        ).translate([unit]).results[0]

    assert result.origin is TranslationOrigin.FAILED
    assert result.selector_decision is CandidateDecision.REJECT
    assert "iki çeviriyi de reddetti" in (result.error or "")


def test_invalid_base_never_auto_accepts_hallucinated_repair(tmp_path: Path) -> None:
    previous = _unit("start_11111111", "I was losing control.")
    unit = _unit(
        "start_22222222",
        "I was letting myself get dragged into this. I had to keep my cool, "
        "I had to-{w=0.5}{nw}",
    )
    following = _unit(
        "start_33333333",
        "Axel pushed me forward and told me to stay on all fours.",
    )
    protected_source = (
        "I was letting myself get dragged into this. I had to keep my cool, "
        "I had to-__RENTR_0000____RENTR_0001__"
    )
    base = MockTranslationProvider(
        {
            protected_source: (
                "Kendimi bu işin içine çekiliyordum. Sakin kalmam gerekiyordu, "
                "kontrolümü sağlamam gerekiyordu-__RENTR_0000____RENTR_0001__."
            )
        }
    )
    repair = _RepairProvider(
        {
            protected_source: (
                "Kendimi bu işin içine çekiliyordum. Sakin kalmam gerekiyordu, "
                "kontrolümü sağlamam gerekiyordu - Axel beni öne itti ve dört "
                "ayak üzerinde kalmamı söyledi.__RENTR_0000____RENTR_0001__"
            )
        }
    )
    judge = _JudgeProvider(CandidateDecision.REPAIR, confidence=0.99)

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(
            provider=base,
            memory=memory,
            repair_provider=repair,
            judge_provider=judge,
        ).translate_selected([previous, unit, following], [1]).results[0]

        assert result.origin is TranslationOrigin.FAILED
        assert result.selector_decision is CandidateDecision.REJECT
        assert "adjacent_context_name_leak" in result.post_repair_risk_reasons
        assert memory.get(unit) is None
        assert judge.calls == []


def test_invalid_base_requires_judge_approval_for_clean_repair(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "Hello [name], how are you?")
    protected_source = "Hello __RENTR_0000__, how are you?"
    base = MockTranslationProvider({protected_source: "Merhaba, nasılsın?"})
    repair = _RepairProvider(
        {protected_source: "Merhaba __RENTR_0000__, nasılsın?"}
    )
    judge = _JudgeProvider(CandidateDecision.REPAIR, confidence=0.95)

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(
            provider=base,
            memory=memory,
            repair_provider=repair,
            judge_provider=judge,
        ).translate([unit]).results[0]

    assert result.origin is TranslationOrigin.REPAIRED
    assert result.translated_text == "Merhaba [name], nasılsın?"
    assert result.selector_decision is CandidateDecision.REPAIR
    assert len(judge.calls) == 1
    assert "base_technical_qc_failed" in judge.calls[0].base_risk_reasons


def test_invalid_base_rejects_repair_if_judge_does_not_approve(tmp_path: Path) -> None:
    unit = _unit("start_deadbeef", "Hello [name], how are you?")
    protected_source = "Hello __RENTR_0000__, how are you?"
    base = MockTranslationProvider({protected_source: "Merhaba, nasılsın?"})
    repair = _RepairProvider(
        {protected_source: "Merhaba __RENTR_0000__, nasılsın?"}
    )
    judge = _JudgeProvider(CandidateDecision.BASE, confidence=0.95)

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(
            provider=base,
            memory=memory,
            repair_provider=repair,
            judge_provider=judge,
        ).translate([unit]).results[0]

        assert result.origin is TranslationOrigin.FAILED
        assert result.selector_decision is CandidateDecision.REJECT
        assert "repair semantik hakemden onay alamadı" in (result.error or "")
        assert memory.get(unit) is None


def test_stutter_waits_are_hidden_from_provider_and_restored_after_translation(
    tmp_path: Path,
) -> None:
    unit = _unit(
        "stutter_1",
        "Easy for y--{w=0.5}you to say. You n--{w=0.5}never had my problem.",
    )
    provider = MockTranslationProvider(
        {
            "Easy for you to say. You never had my problem.": (
                "Senin için söylemesi kolay. Sen asla benim sorunumu yaşamadın."
            )
        }
    )

    with TranslationMemory(tmp_path / "memory.sqlite3") as memory:
        result = TranslationEngine(provider=provider, memory=memory).translate([unit]).results[0]

    assert result.succeeded
    assert result.translated_text == (
        "S--{w=0.5}senin için söylemesi kolay. Sen a--{w=0.5}asla "
        "benim sorunumu yaşamadın."
    )
    assert provider.calls[0].source_text == "Easy for you to say. You never had my problem."
