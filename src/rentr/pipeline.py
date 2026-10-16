"""Resumable translation orchestration independent from CLI and GUI."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from enum import StrEnum

from rentr.domain import TranslationStatus, TranslationUnit
from rentr.localization import LocalizationAssets
from rentr.memory import TranslationMemory
from rentr.protection import (
    ProtectedText,
    ProtectionError,
    protect_text,
    restore_text_with_boundary_salvage,
)
from rentr.providers import (
    CandidateDecision,
    CandidateJudgeProvider,
    CandidateSelectionRequest,
    CandidateSelectionResponse,
    CharacterGuidance,
    GlossaryHint,
    ProviderError,
    SemanticRepairProvider,
    SemanticRepairRequest,
    SemanticRepairResponse,
    TemporaryProviderError,
    TranslationContext,
    TranslationProvider,
    TranslationRequest,
    TranslationResponse,
    TranslationSuggestion,
)
from rentr.quality import QualityError, validate_translation_output
from rentr.semantic_repair import TranslationRisk, TranslationRiskAnalyzer
from rentr.stutter import StutterPlan, normalize_stutters, restore_stutters
from rentr.triage import requires_provider_translation


class TranslationOrigin(StrEnum):
    """Where one final target came from."""

    EXISTING = "existing"
    MEMORY = "memory"
    PROVIDER = "provider"
    REPAIRED = "repaired"
    PASSTHROUGH = "passthrough"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded exponential backoff configuration."""

    max_attempts: int = 3
    initial_delay_seconds: float = 0.5
    multiplier: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts 1 veya daha büyük olmalı")
        if self.initial_delay_seconds < 0:
            raise ValueError("ilk bekleme negatif olamaz")
        if self.multiplier < 1:
            raise ValueError("bekleme çarpanı 1 veya daha büyük olmalı")


@dataclass(frozen=True, slots=True)
class TranslationResult:
    """One independently recoverable pipeline result."""

    unit: TranslationUnit
    translated_text: str | None
    origin: TranslationOrigin
    attempts: int
    error: str | None = None
    base_translated_text: str | None = None
    risk_score: int = 0
    risk_reasons: tuple[str, ...] = ()
    repair_attempted: bool = False
    repair_used: bool = False
    repair_attempts: int = 0
    repair_model: str | None = None
    repair_error: str | None = None
    post_repair_risk_reasons: tuple[str, ...] = ()
    selector_attempted: bool = False
    selector_decision: CandidateDecision | None = None
    selector_attempts: int = 0
    selector_model: str | None = None
    selector_confidence: float | None = None
    selector_reasons: tuple[str, ...] = ()
    selector_error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.origin is not TranslationOrigin.FAILED

    def materialize(self) -> TranslationUnit:
        """Build a validated output unit without mutating the parser inventory."""
        if self.translated_text is None:
            return self.unit
        if self.origin is TranslationOrigin.EXISTING:
            return self.unit
        return replace(
            self.unit,
            translated_text=self.translated_text,
            translated_segments=(self.translated_text,),
            status=TranslationStatus.VALIDATED,
        )


@dataclass(frozen=True, slots=True)
class TranslationReport:
    """Batch summary that preserves partial successes for resume."""

    results: tuple[TranslationResult, ...]

    @property
    def failed_count(self) -> int:
        return sum(not result.succeeded for result in self.results)

    @property
    def repaired_count(self) -> int:
        return sum(result.repair_used for result in self.results)

    @property
    def repair_attempted_count(self) -> int:
        return sum(result.repair_attempted for result in self.results)

    @property
    def selector_attempted_count(self) -> int:
        return sum(result.selector_attempted for result in self.results)

    @property
    def selector_base_count(self) -> int:
        return sum(result.selector_decision is CandidateDecision.BASE for result in self.results)

    @property
    def selector_repair_count(self) -> int:
        return sum(result.selector_decision is CandidateDecision.REPAIR for result in self.results)

    @property
    def selector_reject_count(self) -> int:
        return sum(result.selector_decision is CandidateDecision.REJECT for result in self.results)

    @property
    def translated_units(self) -> tuple[TranslationUnit, ...]:
        return tuple(result.materialize() for result in self.results)


@dataclass(frozen=True, slots=True)
class WorkEstimate:
    """Provider work estimate before any remote request."""

    total_units: int
    existing_units: int
    cached_units: int
    passthrough_units: int
    provider_units: int
    provider_characters: int


@dataclass(frozen=True, slots=True)
class _ProviderAttempt:
    response: TranslationResponse | None
    attempts: int
    error: str | None


@dataclass(frozen=True, slots=True)
class _RepairAttempt:
    response: SemanticRepairResponse | None
    attempts: int
    error: str | None


@dataclass(frozen=True, slots=True)
class _JudgeAttempt:
    response: CandidateSelectionResponse | None
    attempts: int
    error: str | None


class TranslationEngine:
    """Token-safe, cache-first and optionally self-repairing translation service."""

    def __init__(
        self,
        *,
        provider: TranslationProvider,
        memory: TranslationMemory,
        retry_policy: RetryPolicy | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        localization: LocalizationAssets | None = None,
        repair_provider: SemanticRepairProvider | None = None,
        judge_provider: CandidateJudgeProvider | None = None,
        risk_analyzer: TranslationRiskAnalyzer | None = None,
    ) -> None:
        self.provider = provider
        self.memory = memory
        self.retry_policy = retry_policy or RetryPolicy()
        self.sleeper = sleeper
        self.localization = localization or LocalizationAssets()
        self.repair_provider = repair_provider
        self.judge_provider = judge_provider
        self.risk_analyzer = risk_analyzer or TranslationRiskAnalyzer()

    def estimate(self, units: Iterable[TranslationUnit]) -> WorkEstimate:
        inventory = tuple(units)
        existing = 0
        cached = 0
        passthrough = 0
        provider = 0
        characters = 0
        for unit in inventory:
            if unit.translated_text is not None:
                existing += 1
            elif self.memory.get(unit) is not None:
                cached += 1
            elif not requires_provider_translation(unit.source_text):
                passthrough += 1
            else:
                provider += 1
                characters += len(unit.source_text)
        return WorkEstimate(
            total_units=len(inventory),
            existing_units=existing,
            cached_units=cached,
            passthrough_units=passthrough,
            provider_units=provider,
            provider_characters=characters,
        )

    @staticmethod
    def _context_maps(
        inventory: tuple[TranslationUnit, ...],
    ) -> tuple[dict[int, str], dict[int, str]]:
        previous_by_index: dict[int, str] = {}
        previous_by_label: dict[str, str] = {}
        for index, unit in enumerate(inventory):
            if unit.label and requires_provider_translation(unit.source_text):
                previous = previous_by_label.get(unit.label)
                if previous is not None:
                    previous_by_index[index] = previous
                previous_by_label[unit.label] = unit.source_text

        next_by_index: dict[int, str] = {}
        next_by_label: dict[str, str] = {}
        for index in range(len(inventory) - 1, -1, -1):
            unit = inventory[index]
            if unit.label and requires_provider_translation(unit.source_text):
                following = next_by_label.get(unit.label)
                if following is not None:
                    next_by_index[index] = following
                next_by_label[unit.label] = unit.source_text
        return previous_by_index, next_by_index

    def translate(self, units: Iterable[TranslationUnit]) -> TranslationReport:
        inventory = tuple(units)
        return self.translate_selected(inventory, range(len(inventory)))

    def translate_selected(
        self,
        units: Iterable[TranslationUnit],
        selected_indices: Iterable[int],
    ) -> TranslationReport:
        """Translate only selected inventory positions while keeping full context."""
        inventory = tuple(units)
        indices = tuple(sorted(set(selected_indices)))
        if any(index < 0 or index >= len(inventory) for index in indices):
            raise ValueError("seçilen çeviri indeksi envanter dışında")
        previous_by_index, next_by_index = self._context_maps(inventory)
        results = tuple(
            self._translate_unit(
                inventory[index],
                previous_source=previous_by_index.get(index),
                next_source=next_by_index.get(index),
            )
            for index in indices
        )
        return TranslationReport(results=results)

    def _translation_context(
        self,
        unit: TranslationUnit,
        *,
        previous_source: str | None,
        next_source: str | None,
    ) -> TranslationContext:
        suggestions = tuple(
            TranslationSuggestion(
                source_text=candidate.entry.source_text,
                translated_text=candidate.entry.translated_text,
                similarity=candidate.similarity,
            )
            for candidate in self.memory.find_similar(unit.source_text)
        )
        glossary = tuple(
            GlossaryHint(entry.source, entry.target, entry.notes)
            for entry in (
                self.localization.glossary.matching(unit.source_text)
                if self.localization.glossary is not None
                else ()
            )
        )
        card = self.localization.character_for(unit.speaker)
        character = (
            CharacterGuidance(
                display_name=card.display_name,
                address_style=card.address_style.value,
                traits=card.traits,
                notes=card.notes,
            )
            if card is not None
            else None
        )
        return TranslationContext(
            speaker=unit.speaker,
            label=unit.label,
            previous_source_text=previous_source,
            next_source_text=next_source,
            suggestions=suggestions,
            glossary=glossary,
            character=character,
        )

    def _call_provider(self, request: TranslationRequest) -> _ProviderAttempt:
        delay = self.retry_policy.initial_delay_seconds
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            try:
                return _ProviderAttempt(self.provider.translate(request), attempt, None)
            except TemporaryProviderError as error:
                if attempt == self.retry_policy.max_attempts:
                    return _ProviderAttempt(None, attempt, str(error))
                self.sleeper(delay)
                delay *= self.retry_policy.multiplier
            except ProviderError as error:
                return _ProviderAttempt(None, attempt, str(error))
        raise AssertionError("provider retry döngüsü sonuç üretmedi")  # pragma: no cover

    def _call_repair(self, request: SemanticRepairRequest) -> _RepairAttempt:
        if self.repair_provider is None:  # pragma: no cover - caller guarantees this
            raise AssertionError("repair provider yok")
        delay = self.retry_policy.initial_delay_seconds
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            try:
                return _RepairAttempt(self.repair_provider.repair(request), attempt, None)
            except TemporaryProviderError as error:
                if attempt == self.retry_policy.max_attempts:
                    return _RepairAttempt(None, attempt, str(error))
                self.sleeper(delay)
                delay *= self.retry_policy.multiplier
            except ProviderError as error:
                return _RepairAttempt(None, attempt, str(error))
        raise AssertionError("repair retry döngüsü sonuç üretmedi")  # pragma: no cover

    def _call_judge(self, request: CandidateSelectionRequest) -> _JudgeAttempt:
        if self.judge_provider is None:  # pragma: no cover - caller guarantees this
            raise AssertionError("judge provider yok")
        delay = self.retry_policy.initial_delay_seconds
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            try:
                return _JudgeAttempt(self.judge_provider.select(request), attempt, None)
            except TemporaryProviderError as error:
                if attempt == self.retry_policy.max_attempts:
                    return _JudgeAttempt(None, attempt, str(error))
                self.sleeper(delay)
                delay *= self.retry_policy.multiplier
            except ProviderError as error:
                return _JudgeAttempt(None, attempt, str(error))
        raise AssertionError("judge retry döngüsü sonuç üretmedi")  # pragma: no cover

    @staticmethod
    def _restore_and_validate(
        unit: TranslationUnit,
        protected: ProtectedText,
        translated_text: str,
        *,
        stutter_plan: StutterPlan,
    ) -> str:
        restored = restore_text_with_boundary_salvage(translated_text.strip(), protected)
        restored = restore_stutters(restored, stutter_plan)
        validate_translation_output(unit.source_text, restored)
        return restored

    def _risk(
        self,
        unit: TranslationUnit,
        candidate: str,
        *,
        context: TranslationContext,
    ) -> TranslationRisk:
        return self.risk_analyzer.analyze(unit.source_text, candidate, context=context)

    def _translate_unit(
        self,
        unit: TranslationUnit,
        *,
        previous_source: str | None,
        next_source: str | None,
    ) -> TranslationResult:
        if unit.translated_text is not None:
            return TranslationResult(
                unit=unit,
                translated_text=unit.translated_text,
                origin=TranslationOrigin.EXISTING,
                attempts=0,
            )

        cached = self.memory.get(unit)
        if cached is not None:
            return TranslationResult(
                unit=unit,
                translated_text=cached.translated_text,
                origin=TranslationOrigin.MEMORY,
                attempts=0,
            )

        if not requires_provider_translation(unit.source_text):
            return TranslationResult(
                unit=unit,
                translated_text=unit.source_text,
                origin=TranslationOrigin.PASSTHROUGH,
                attempts=0,
            )

        stutter_plan = normalize_stutters(unit.source_text)
        try:
            protected = protect_text(stutter_plan.normalized_text)
        except ProtectionError as error:
            return TranslationResult(
                unit=unit,
                translated_text=None,
                origin=TranslationOrigin.FAILED,
                attempts=0,
                error=str(error),
            )

        context = self._translation_context(
            unit,
            previous_source=previous_source,
            next_source=next_source,
        )
        request = TranslationRequest(
            unit_id=unit.unit_id,
            source_text=protected.protected_text,
            source_language="English",
            target_language="Turkish",
            context=context,
        )
        base_attempt = self._call_provider(request)
        base_response = base_attempt.response
        if base_response is None:
            return TranslationResult(
                unit=unit,
                translated_text=None,
                origin=TranslationOrigin.FAILED,
                attempts=base_attempt.attempts,
                error=base_attempt.error,
            )

        base_raw = base_response.translated_text.strip()
        base_restored: str | None = None
        base_validation_error: str | None = None
        try:
            base_restored = self._restore_and_validate(
                unit, protected, base_raw, stutter_plan=stutter_plan
            )
        except (ProtectionError, QualityError) as error:
            base_validation_error = str(error)

        risk_candidate = base_restored if base_restored is not None else base_raw
        risk = self._risk(unit, risk_candidate, context=context)
        risk_reasons = list(risk.reasons)
        if base_validation_error is not None:
            risk_reasons.insert(0, "base_technical_qc_failed")

        should_repair = self.repair_provider is not None and (
            base_validation_error is not None or risk.should_repair
        )
        if not should_repair:
            if base_restored is None:
                return TranslationResult(
                    unit=unit,
                    translated_text=None,
                    origin=TranslationOrigin.FAILED,
                    attempts=base_attempt.attempts,
                    error=base_validation_error,
                    base_translated_text=base_raw,
                    risk_score=risk.score,
                    risk_reasons=tuple(risk_reasons),
                )
            self.memory.save(unit, base_restored, provider=base_response.provider)
            return TranslationResult(
                unit=unit,
                translated_text=base_restored,
                origin=TranslationOrigin.PROVIDER,
                attempts=base_attempt.attempts,
                base_translated_text=base_restored,
                risk_score=risk.score,
                risk_reasons=tuple(risk_reasons),
            )

        repair_request = SemanticRepairRequest(
            unit_id=unit.unit_id,
            source_text=protected.protected_text,
            base_translation=base_raw,
            source_language="English",
            target_language="Turkish",
            context=context,
            risk_reasons=tuple(risk_reasons),
        )
        repair_attempt = self._call_repair(repair_request)
        repair_response = repair_attempt.response
        repair_model = repair_response.model if repair_response is not None else None
        if repair_response is None:
            if base_restored is not None and not risk.hard_reasons:
                self.memory.save(unit, base_restored, provider=base_response.provider)
                return TranslationResult(
                    unit=unit,
                    translated_text=base_restored,
                    origin=TranslationOrigin.PROVIDER,
                    attempts=base_attempt.attempts,
                    base_translated_text=base_restored,
                    risk_score=risk.score,
                    risk_reasons=tuple(risk_reasons),
                    repair_attempted=True,
                    repair_attempts=repair_attempt.attempts,
                    repair_model=repair_model,
                    repair_error=repair_attempt.error,
                    selector_attempted=True,
                    selector_decision=CandidateDecision.BASE,
                    selector_reasons=("repair_unavailable_conservative_base",),
                    selector_error=repair_attempt.error,
                )
            return TranslationResult(
                unit=unit,
                translated_text=None,
                origin=TranslationOrigin.FAILED,
                attempts=base_attempt.attempts,
                error="Semantic repair başarısız; güvenli aday bulunamadı",
                base_translated_text=base_restored or base_raw,
                risk_score=risk.score,
                risk_reasons=tuple(risk_reasons),
                repair_attempted=True,
                repair_attempts=repair_attempt.attempts,
                repair_model=repair_model,
                repair_error=repair_attempt.error,
                selector_attempted=True,
                selector_decision=CandidateDecision.REJECT,
                selector_reasons=("repair_unavailable_and_base_unsafe",),
                selector_error=repair_attempt.error,
            )

        repaired: str | None = None
        post_risk: TranslationRisk | None = None
        repair_validation_error: str | None = None
        try:
            repaired = self._restore_and_validate(
                unit,
                protected,
                repair_response.translated_text,
                stutter_plan=stutter_plan,
            )
            post_risk = self._risk(unit, repaired, context=context)
        except (ProtectionError, QualityError) as error:
            repair_validation_error = str(error)

        if repaired is None or post_risk is None:
            if base_restored is not None and not risk.hard_reasons:
                self.memory.save(unit, base_restored, provider=base_response.provider)
                return TranslationResult(
                    unit=unit,
                    translated_text=base_restored,
                    origin=TranslationOrigin.PROVIDER,
                    attempts=base_attempt.attempts,
                    base_translated_text=base_restored,
                    risk_score=risk.score,
                    risk_reasons=tuple(risk_reasons),
                    repair_attempted=True,
                    repair_attempts=repair_attempt.attempts,
                    repair_model=repair_response.model,
                    repair_error=repair_validation_error,
                    selector_attempted=True,
                    selector_decision=CandidateDecision.BASE,
                    selector_reasons=("repair_failed_technical_qc",),
                    selector_error=repair_validation_error,
                )
            return TranslationResult(
                unit=unit,
                translated_text=None,
                origin=TranslationOrigin.FAILED,
                attempts=base_attempt.attempts,
                error=repair_validation_error,
                base_translated_text=base_restored or base_raw,
                risk_score=risk.score,
                risk_reasons=tuple(risk_reasons),
                repair_attempted=True,
                repair_attempts=repair_attempt.attempts,
                repair_model=repair_response.model,
                repair_error=repair_validation_error,
                selector_attempted=True,
                selector_decision=CandidateDecision.REJECT,
                selector_reasons=("both_candidates_failed_technical_qc",),
                selector_error=repair_validation_error,
            )

        base_hard = (
            self.risk_analyzer.unresolved_hard_reasons(risk)
            if base_restored is not None
            else ("base_technical_qc_failed",)
        )
        repair_hard = self.risk_analyzer.unresolved_hard_reasons(post_risk)

        selector_decision: CandidateDecision
        selector_confidence: float | None = None
        selector_reasons: tuple[str, ...]
        selector_attempts = 0
        selector_model: str | None = None
        selector_error: str | None = None

        if base_restored is None:
            if repair_hard:
                return TranslationResult(
                    unit=unit,
                    translated_text=None,
                    origin=TranslationOrigin.FAILED,
                    attempts=base_attempt.attempts,
                    error=(
                        "Semantic repair sonrası yüksek güvenli anlam riski kaldı: "
                        + ", ".join(repair_hard)
                    ),
                    base_translated_text=base_raw,
                    risk_score=risk.score,
                    risk_reasons=tuple(risk_reasons),
                    repair_attempted=True,
                    repair_attempts=repair_attempt.attempts,
                    repair_model=repair_response.model,
                    post_repair_risk_reasons=post_risk.reasons,
                    selector_attempted=True,
                    selector_decision=CandidateDecision.REJECT,
                    selector_reasons=("base_technical_invalid_repair_semantically_unsafe",),
                )
            if self.judge_provider is None:
                return TranslationResult(
                    unit=unit,
                    translated_text=None,
                    origin=TranslationOrigin.FAILED,
                    attempts=base_attempt.attempts,
                    error=(
                        "Base teknik olarak geçersiz; repair semantik hakem olmadan "
                        "kabul edilmedi"
                    ),
                    base_translated_text=base_raw,
                    risk_score=risk.score,
                    risk_reasons=tuple(risk_reasons),
                    repair_attempted=True,
                    repair_attempts=repair_attempt.attempts,
                    repair_model=repair_response.model,
                    post_repair_risk_reasons=post_risk.reasons,
                    selector_attempted=True,
                    selector_decision=CandidateDecision.REJECT,
                    selector_reasons=("base_invalid_requires_semantic_judge",),
                )

            judge_request = CandidateSelectionRequest(
                unit_id=unit.unit_id,
                source_text=unit.source_text,
                base_translation=base_raw,
                repair_translation=repaired,
                source_language="English",
                target_language="Turkish",
                context=context,
                base_risk_reasons=tuple(dict.fromkeys((*risk_reasons, "base_technical_qc_failed"))),
                repair_risk_reasons=post_risk.reasons,
            )
            judge_attempt = self._call_judge(judge_request)
            selector_attempts = judge_attempt.attempts
            judge_response = judge_attempt.response
            if judge_response is None:
                return TranslationResult(
                    unit=unit,
                    translated_text=None,
                    origin=TranslationOrigin.FAILED,
                    attempts=base_attempt.attempts,
                    error="Base teknik olarak geçersiz ve semantic judge kullanılamadı",
                    base_translated_text=base_raw,
                    risk_score=risk.score,
                    risk_reasons=tuple(risk_reasons),
                    repair_attempted=True,
                    repair_attempts=repair_attempt.attempts,
                    repair_model=repair_response.model,
                    post_repair_risk_reasons=post_risk.reasons,
                    selector_attempted=True,
                    selector_decision=CandidateDecision.REJECT,
                    selector_attempts=selector_attempts,
                    selector_reasons=("judge_unavailable_base_invalid",),
                    selector_error=judge_attempt.error,
                )

            selector_model = judge_response.model
            selector_confidence = judge_response.confidence
            selector_reasons = judge_response.reasons
            if (
                judge_response.decision is CandidateDecision.REPAIR
                and judge_response.confidence >= 0.82
            ):
                selector_decision = CandidateDecision.REPAIR
            else:
                reject_reason = (
                    "repair_not_semantically_approved_for_invalid_base"
                    if judge_response.decision is not CandidateDecision.REPAIR
                    else "repair_below_invalid_base_confidence_threshold"
                )
                return TranslationResult(
                    unit=unit,
                    translated_text=None,
                    origin=TranslationOrigin.FAILED,
                    attempts=base_attempt.attempts,
                    error=(
                        "Teknik olarak geçersiz base yerine repair semantik hakemden "
                        "onay alamadı"
                    ),
                    base_translated_text=base_raw,
                    risk_score=risk.score,
                    risk_reasons=tuple(risk_reasons),
                    repair_attempted=True,
                    repair_attempts=repair_attempt.attempts,
                    repair_model=repair_response.model,
                    post_repair_risk_reasons=post_risk.reasons,
                    selector_attempted=True,
                    selector_decision=CandidateDecision.REJECT,
                    selector_attempts=selector_attempts,
                    selector_model=selector_model,
                    selector_confidence=selector_confidence,
                    selector_reasons=tuple(
                        dict.fromkeys((*judge_response.reasons, reject_reason))
                    ),
                )
        elif base_hard and repair_hard:
            return TranslationResult(
                unit=unit,
                translated_text=None,
                origin=TranslationOrigin.FAILED,
                attempts=base_attempt.attempts,
                error=(
                    "Semantic repair sonrası her iki adayda da yüksek güvenli anlam riski kaldı: "
                    + ", ".join(tuple(dict.fromkeys((*base_hard, *repair_hard))))
                ),
                base_translated_text=base_restored,
                risk_score=risk.score,
                risk_reasons=tuple(risk_reasons),
                repair_attempted=True,
                repair_attempts=repair_attempt.attempts,
                repair_model=repair_response.model,
                post_repair_risk_reasons=post_risk.reasons,
                selector_attempted=True,
                selector_decision=CandidateDecision.REJECT,
                selector_reasons=("both_candidates_have_hard_risk",),
            )
        elif repair_hard and not base_hard:
            selector_decision = CandidateDecision.BASE
            selector_reasons = ("repair_introduced_hard_risk",)
        elif repaired == base_restored:
            selector_decision = CandidateDecision.BASE
            selector_reasons = ("candidates_identical",)
        elif self.judge_provider is None:
            if base_hard and not repair_hard:
                selector_decision = CandidateDecision.REPAIR
                selector_reasons = ("repair_resolved_base_hard_risk_without_judge",)
            else:
                selector_decision = CandidateDecision.BASE
                selector_reasons = ("no_judge_provider_conservative_base",)
        else:
            judge_request = CandidateSelectionRequest(
                unit_id=unit.unit_id,
                source_text=stutter_plan.normalized_text,
                base_translation=base_restored,
                repair_translation=repaired,
                source_language="English",
                target_language="Turkish",
                context=context,
                base_risk_reasons=risk.reasons,
                repair_risk_reasons=post_risk.reasons,
            )
            judge_attempt = self._call_judge(judge_request)
            selector_attempts = judge_attempt.attempts
            judge_response = judge_attempt.response
            if judge_response is None:
                if base_hard:
                    return TranslationResult(
                        unit=unit,
                        translated_text=None,
                        origin=TranslationOrigin.FAILED,
                        attempts=base_attempt.attempts,
                        error="Base yüksek riskli ve semantic judge kullanılamadı",
                        base_translated_text=base_restored,
                        risk_score=risk.score,
                        risk_reasons=tuple(risk_reasons),
                        repair_attempted=True,
                        repair_attempts=repair_attempt.attempts,
                        repair_model=repair_response.model,
                        post_repair_risk_reasons=post_risk.reasons,
                        selector_attempted=True,
                        selector_decision=CandidateDecision.REJECT,
                        selector_attempts=selector_attempts,
                        selector_reasons=("judge_unavailable_base_hard_risk",),
                        selector_error=judge_attempt.error,
                    )
                selector_decision = CandidateDecision.BASE
                selector_reasons = ("judge_unavailable_conservative_base",)
                selector_error = judge_attempt.error
            else:
                selector_model = judge_response.model
                selector_confidence = judge_response.confidence
                selector_reasons = judge_response.reasons
                if judge_response.decision is CandidateDecision.REPAIR:
                    if judge_response.confidence >= 0.72:
                        selector_decision = CandidateDecision.REPAIR
                    elif base_hard:
                        return TranslationResult(
                            unit=unit,
                            translated_text=None,
                            origin=TranslationOrigin.FAILED,
                            attempts=base_attempt.attempts,
                            error="Yüksek riskli base için repair yeterli hakem güveni alamadı",
                            base_translated_text=base_restored,
                            risk_score=risk.score,
                            risk_reasons=tuple(risk_reasons),
                            repair_attempted=True,
                            repair_attempts=repair_attempt.attempts,
                            repair_model=repair_response.model,
                            post_repair_risk_reasons=post_risk.reasons,
                            selector_attempted=True,
                            selector_decision=CandidateDecision.REJECT,
                            selector_attempts=selector_attempts,
                            selector_model=selector_model,
                            selector_confidence=selector_confidence,
                            selector_reasons=tuple(
                                dict.fromkeys(
                                    (*judge_response.reasons, "repair_below_confidence_threshold")
                                )
                            ),
                        )
                    else:
                        selector_decision = CandidateDecision.BASE
                        selector_reasons = tuple(
                            dict.fromkeys(
                                (*judge_response.reasons, "repair_below_confidence_threshold")
                            )
                        )
                elif judge_response.decision is CandidateDecision.REJECT:
                    if judge_response.confidence >= 0.75 or base_hard:
                        return TranslationResult(
                            unit=unit,
                            translated_text=None,
                            origin=TranslationOrigin.FAILED,
                            attempts=base_attempt.attempts,
                            error="Candidate selector iki çeviriyi de reddetti",
                            base_translated_text=base_restored,
                            risk_score=risk.score,
                            risk_reasons=tuple(risk_reasons),
                            repair_attempted=True,
                            repair_attempts=repair_attempt.attempts,
                            repair_model=repair_response.model,
                            post_repair_risk_reasons=post_risk.reasons,
                            selector_attempted=True,
                            selector_decision=CandidateDecision.REJECT,
                            selector_attempts=selector_attempts,
                            selector_model=selector_model,
                            selector_confidence=selector_confidence,
                            selector_reasons=selector_reasons,
                        )
                    selector_decision = CandidateDecision.BASE
                    selector_reasons = tuple(
                        dict.fromkeys(
                            (*judge_response.reasons, "reject_below_confidence_threshold")
                        )
                    )
                elif base_hard:
                    return TranslationResult(
                        unit=unit,
                        translated_text=None,
                        origin=TranslationOrigin.FAILED,
                        attempts=base_attempt.attempts,
                        error="Hakem yüksek riskli base'i korumaya çalıştı; fail-closed",
                        base_translated_text=base_restored,
                        risk_score=risk.score,
                        risk_reasons=tuple(risk_reasons),
                        repair_attempted=True,
                        repair_attempts=repair_attempt.attempts,
                        repair_model=repair_response.model,
                        post_repair_risk_reasons=post_risk.reasons,
                        selector_attempted=True,
                        selector_decision=CandidateDecision.REJECT,
                        selector_attempts=selector_attempts,
                        selector_model=selector_model,
                        selector_confidence=selector_confidence,
                        selector_reasons=tuple(
                            dict.fromkeys((*judge_response.reasons, "base_has_hard_risk"))
                        ),
                    )
                else:
                    selector_decision = CandidateDecision.BASE

        selected_text = repaired if selector_decision is CandidateDecision.REPAIR else base_restored
        if selected_text is None:  # pragma: no cover - guarded above
            raise AssertionError("selector geçerli aday seçmedi")

        repair_used = selector_decision is CandidateDecision.REPAIR
        origin = TranslationOrigin.REPAIRED if repair_used else TranslationOrigin.PROVIDER
        memory_provider = (
            f"{base_response.provider}+{repair_response.provider}"
            if repair_used
            else base_response.provider
        )
        self.memory.save(unit, selected_text, provider=memory_provider)
        return TranslationResult(
            unit=unit,
            translated_text=selected_text,
            origin=origin,
            attempts=base_attempt.attempts,
            base_translated_text=base_restored or base_raw,
            risk_score=risk.score,
            risk_reasons=tuple(risk_reasons),
            repair_attempted=True,
            repair_used=repair_used,
            repair_attempts=repair_attempt.attempts,
            repair_model=repair_response.model,
            post_repair_risk_reasons=post_risk.reasons,
            selector_attempted=True,
            selector_decision=selector_decision,
            selector_attempts=selector_attempts,
            selector_model=selector_model,
            selector_confidence=selector_confidence,
            selector_reasons=selector_reasons,
            selector_error=selector_error,
        )

