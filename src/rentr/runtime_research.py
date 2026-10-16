"""Non-invasive runtime translation research and text-stream simulation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from rentr.protection import protect_text, restore_text
from rentr.providers import (
    ProviderError,
    TranslationContext,
    TranslationProvider,
    TranslationRequest,
)
from rentr.scanner import GameInputMode, inspect_game
from rentr.versioning import RenPyGeneration, RuntimeDetection, detect_runtime


class RuntimeResearchError(ValueError):
    """Raised when a research input cannot be evaluated safely."""


class RuntimeStrategy(StrEnum):
    STATIC_PATCH = "static-patch"
    RENPY_CLIPBOARD = "renpy-clipboard-assist"
    OCR_OVERLAY = "ocr-overlay"
    PROCESS_HOOK = "process-hook"


class ResearchVerdict(StrEnum):
    RECOMMENDED = "recommended"
    RESEARCH_ONLY = "research-only"
    REJECTED = "rejected"


class OverlayOrigin(StrEnum):
    PROVIDER = "provider"
    MEMORY = "memory"


@dataclass(frozen=True, slots=True)
class StrategyAssessment:
    strategy: RuntimeStrategy
    verdict: ResearchVerdict
    reason: str
    requires_game_write: bool
    requires_screen_capture: bool
    requires_process_injection: bool
    known_limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuntimeResearchReport:
    game_root: Path
    game_mode: GameInputMode
    runtime: RuntimeDetection
    strategies: tuple[StrategyAssessment, ...]
    writes_to_game: bool = False
    starts_game_process: bool = False


@dataclass(frozen=True, slots=True)
class OverlayFrame:
    sequence: int
    source_text: str
    translated_text: str
    origin: OverlayOrigin


def assess_runtime_strategies(game_root: Path) -> RuntimeResearchReport:
    """Produce a read-only decision report; never starts or modifies the game."""
    inspection = inspect_game(game_root)
    runtime = detect_runtime(inspection.selected_root)
    version_note = (
        f"Algılanan çalışma zamanı: {runtime.generation.value}"
        if runtime.generation is not RenPyGeneration.UNKNOWN
        else "Ren'Py nesli statik kanıtla belirlenemedi"
    )
    strategies = (
        StrategyAssessment(
            RuntimeStrategy.STATIC_PATCH,
            ResearchVerdict.RECOMMENDED,
            "Tam bağlam, önizleme, cache, lint ve geri alma sunduğu için V1 yolu.",
            True,
            False,
            False,
            ("Kurulum için ayrı kullanıcı onayı gerekir", version_note),
        ),
        StrategyAssessment(
            RuntimeStrategy.RENPY_CLIPBOARD,
            ResearchVerdict.RESEARCH_ONLY,
            "Ren'Py'nin self-voicing clipboard modu ekrandaki erişilebilir metni "
            "kullanıcı eylemiyle dışarı verebilir.",
            False,
            False,
            False,
            (
                "Shift+C davranışı oyun/sürüm/erişilebilir metin yapısına bağlıdır",
                "Seçim ve özel ekran metinleri eksik kalabilir",
                "Çeviri oyunun içine yerleşmez; ayrı görünüm gerekir",
            ),
        ),
        StrategyAssessment(
            RuntimeStrategy.OCR_OVERLAY,
            ResearchVerdict.RESEARCH_ONLY,
            "Motor bağımsız olabilir ancak ekran görüntüsü, OCR hatası ve gecikme getirir.",
            False,
            True,
            False,
            (
                "Kullanıcıdan açık ekran yakalama izni gerekir",
                "Stilize font, hareket ve düşük kontrast doğruluğu düşürür",
                "Tekrarlı metin ve konuşmacı bağlamı ayrıca çözülmelidir",
            ),
        ),
        StrategyAssessment(
            RuntimeStrategy.PROCESS_HOOK,
            ResearchVerdict.REJECTED,
            "Sürüm kırılması ve süreç bütünlüğü riski ürünün güvenlik sınırını aşıyor.",
            False,
            False,
            True,
            (
                "Oyun sürecine enjeksiyon/hook gerekir",
                "Antivirüs, lisans ve çökme riski yüksektir",
                "RenTR bu yaklaşımı uygulamaz",
            ),
        ),
    )
    return RuntimeResearchReport(
        game_root=inspection.selected_root,
        game_mode=inspection.mode,
        runtime=runtime,
        strategies=strategies,
    )


class RuntimeOverlaySimulator:
    """Translate user-supplied text events; performs no capture, hook, or game I/O."""

    def __init__(self, provider: TranslationProvider, *, maximum_text_length: int = 2_000):
        if maximum_text_length < 1:
            raise RuntimeResearchError("Maksimum metin uzunluğu pozitif olmalı")
        self._provider = provider
        self._maximum_text_length = maximum_text_length
        self._memory: dict[str, str] = {}
        self._sequence = 0

    def translate(self, source_text: str) -> OverlayFrame:
        source = source_text.strip()
        if not source:
            raise RuntimeResearchError("Runtime simülasyon metni boş olamaz")
        if len(source) > self._maximum_text_length:
            raise RuntimeResearchError("Runtime simülasyon metni güvenlik sınırını aşıyor")
        self._sequence += 1
        cached = self._memory.get(source)
        if cached is not None:
            return OverlayFrame(self._sequence, source, cached, OverlayOrigin.MEMORY)

        protected = protect_text(source)
        response = self._provider.translate(
            TranslationRequest(
                unit_id=f"runtime_{self._sequence:06d}",
                source_text=protected.protected_text,
                source_language="English",
                target_language="Turkish",
                context=TranslationContext(),
            )
        )
        translated = restore_text(response.translated_text.strip(), protected)
        if not translated:
            raise ProviderError("sağlayıcı boş runtime çevirisi döndürdü")
        self._memory[source] = translated
        return OverlayFrame(self._sequence, source, translated, OverlayOrigin.PROVIDER)

    def simulate(self, source_events: tuple[str, ...]) -> tuple[OverlayFrame, ...]:
        if not source_events:
            raise RuntimeResearchError("Simülasyon için en az bir metin olmalı")
        if len(source_events) > 1_000:
            raise RuntimeResearchError("Runtime olay sayısı güvenlik sınırını aşıyor")
        return tuple(self.translate(source) for source in source_events)


def load_text_events(path: Path) -> tuple[str, ...]:
    """Load a bounded UTF-8 one-event-per-line research fixture."""
    resolved = path.expanduser().resolve()
    if not resolved.is_file() or resolved.is_symlink():
        raise RuntimeResearchError(f"Runtime metin fixture'ı bulunamadı: {resolved}")
    if resolved.stat().st_size > 1024 * 1024:
        raise RuntimeResearchError("Runtime metin fixture'ı 1 MiB sınırını aşıyor")
    try:
        events = tuple(line.strip() for line in resolved.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeError) as error:
        raise RuntimeResearchError(f"Runtime metin fixture'ı okunamadı: {error}") from error
    if any(not event for event in events):
        raise RuntimeResearchError("Runtime metin fixture'ı boş satır içeremez")
    if not events:
        raise RuntimeResearchError("Runtime metin fixture'ı boş")
    return events
