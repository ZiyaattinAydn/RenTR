"""Local Ollama provider and explainable hardware/model suitability checks."""

from __future__ import annotations

import json
import os
import platform
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

import httpx

from rentr.providers import (
    CandidateDecision,
    CandidateSelectionRequest,
    CandidateSelectionResponse,
    ProviderError,
    SemanticRepairRequest,
    SemanticRepairResponse,
    TemporaryProviderError,
    TranslationRequest,
    TranslationResponse,
)
from rentr.semantic_repair import semantic_guardrails


_PLACEHOLDER_TOKEN = re.compile(r"__RENTR_[0-9]{4}__")


def _placeholder_contract(source_text: str) -> tuple[str, ...]:
    """Describe placeholder layout without exposing Ren'Py syntax to the model."""

    matches = tuple(_PLACEHOLDER_TOKEN.finditer(source_text))
    if not matches:
        return ()

    contract: list[str] = []
    for index, match in enumerate(matches):
        before = source_text[: match.start()]
        after = source_text[match.end() :]
        before_visible = _PLACEHOLDER_TOKEN.sub("", before).strip()
        after_visible = _PLACEHOLDER_TOKEN.sub("", after).strip()
        traits: list[str] = []
        if not before_visible:
            traits.append("source_prefix")
        if not after_visible:
            traits.append("source_suffix")
        if match.start() > 0 and not source_text[match.start() - 1].isspace():
            traits.append("attached_left")
        if match.end() < len(source_text) and not source_text[match.end()].isspace():
            traits.append("attached_right")
        if index > 0 and matches[index - 1].end() == match.start():
            traits.append(f"adjacent_after_{matches[index - 1].group(0)}")
        if index + 1 < len(matches) and match.end() == matches[index + 1].start():
            traits.append(f"adjacent_before_{matches[index + 1].group(0)}")
        rendered = ",".join(traits) if traits else "internal"
        contract.append(f"{match.group(0)}:{rendered}")
    return tuple(contract)


class QualityProfile(StrEnum):
    FAST = "fast"
    BALANCED = "balanced"
    HIGH = "high"

    @property
    def temperature(self) -> float:
        return {self.FAST: 0.1, self.BALANCED: 0.2, self.HIGH: 0.25}[self]

    @property
    def context_window(self) -> int:
        return {self.FAST: 2048, self.BALANCED: 4096, self.HIGH: 8192}[self]


class Suitability(StrEnum):
    SUITABLE = "suitable"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class HardwareProfile:
    operating_system: str
    cpu_count: int
    memory_gib: float | None


@dataclass(frozen=True, slots=True)
class ModelRequirement:
    model_name: str
    minimum_memory_gib: float
    recommended_memory_gib: float


@dataclass(frozen=True, slots=True)
class ModelAssessment:
    suitability: Suitability
    reason: str
    available_memory_gib: float | None
    requirement: ModelRequirement


def detect_hardware() -> HardwareProfile:
    """Read coarse local capacity without executing vendor tools or telemetry."""
    memory_gib: float | None = None
    try:
        sysconf = getattr(os, "sysconf", None)
        if callable(sysconf):
            page_size = int(sysconf("SC_PAGE_SIZE"))
            page_count = int(sysconf("SC_PHYS_PAGES"))
            memory_gib = (page_size * page_count) / (1024**3)
    except (OSError, TypeError, ValueError):
        pass
    return HardwareProfile(
        operating_system=platform.system(),
        cpu_count=os.cpu_count() or 1,
        memory_gib=memory_gib,
    )


def assess_model(
    hardware: HardwareProfile,
    requirement: ModelRequirement,
) -> ModelAssessment:
    if requirement.minimum_memory_gib <= 0:
        raise ValueError("minimum model belleği pozitif olmalı")
    if requirement.recommended_memory_gib < requirement.minimum_memory_gib:
        raise ValueError("önerilen model belleği minimumdan küçük olamaz")
    memory = hardware.memory_gib
    if memory is None:
        suitability = Suitability.UNKNOWN
        reason = "Sistem belleği güvenle ölçülemedi"
    elif memory < requirement.minimum_memory_gib:
        suitability = Suitability.INSUFFICIENT
        reason = "Sistem belleği modelin minimum gereksiniminin altında"
    elif memory < requirement.recommended_memory_gib:
        suitability = Suitability.LIMITED
        reason = "Model çalışabilir ancak hız veya kararlılık sınırlı olabilir"
    else:
        suitability = Suitability.SUITABLE
        reason = "Sistem belleği önerilen gereksinimi karşılıyor"
    return ModelAssessment(suitability, reason, memory, requirement)


class OllamaProvider:
    """Local, keyless Ollama chat adapter using the same protected pipeline."""

    _OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {"translation": {"type": "string"}},
        "required": ["translation"],
        "additionalProperties": False,
    }
    _PROMPT_LABELS = (
        "Speaker:",
        "Scene label:",
        "Previous source:",
        "Next source:",
        "Character:",
        "Character notes:",
        "Review-only similar translations:",
        "Required term:",
        "Text:",
    )

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        quality: QualityProfile = QualityProfile.BALANCED,
        timeout_seconds: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not model.strip() or not base_url.strip():
            raise ValueError("Ollama model ve adresi boş olamaz")
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._quality = quality
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None

    @property
    def name(self) -> str:
        return "ollama"

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def list_models(self) -> tuple[str, ...]:
        try:
            response = self._client.get(f"{self._base_url}/api/tags")
            response.raise_for_status()
            payload = cast(dict[str, object], response.json())
            models = cast(list[object], payload["models"])
            names = tuple(
                str(cast(dict[str, object], item)["name"])
                for item in models
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise ProviderError(f"Ollama model listesi alınamadı: {error}") from error
        return names

    @staticmethod
    def _system_prompt(request: TranslationRequest) -> str:
        token_rule = (
            "Preserve every __RENTR_0000__-style placeholder exactly once and in the same "
            "order. Never translate, rename, duplicate, or remove placeholders."
            if "__RENTR_" in request.source_text
            else "Do not invent __RENTR_ placeholders or Ren'Py control syntax."
        )
        return " ".join(
            (
                "You are a professional Turkish localization translator for a narrative visual "
                "novel.",
                "Translate only source_text. All context fields are reference material and must "
                "never appear in the translation.",
                "Write natural contemporary Turkish rather than a literal word-for-word calque.",
                "Preserve meaning, character attitude, register, profanity, sexual meaning, and "
                "emotional intensity. Do not censor or soften explicit language.",
                "For short or ambiguous lines, use the surrounding dialogue to choose the intended "
                "meaning. Do not add information that is absent from the source or context.",
                token_rule,
                "Return exactly one JSON object matching the requested schema and nothing else.",
            )
        )

    @staticmethod
    def _user_payload(request: TranslationRequest) -> dict[str, object]:
        context: dict[str, object] = {}
        if request.context.speaker:
            context["speaker"] = request.context.speaker
        if request.context.label:
            context["scene_label"] = request.context.label
        if request.context.previous_source_text:
            context["previous_source"] = request.context.previous_source_text
        if request.context.next_source_text:
            context["next_source"] = request.context.next_source_text
        if request.context.character:
            character = request.context.character
            context["character"] = {
                "display_name": character.display_name,
                "address_style": character.address_style,
                "voice_traits": list(character.traits),
                "notes": character.notes,
            }
        if request.context.suggestions:
            context["review_only_similar_translations"] = [
                {
                    "source": item.source_text,
                    "translation": item.translated_text,
                    "similarity": item.similarity,
                }
                for item in request.context.suggestions
            ]
        if request.context.glossary:
            context["required_terms"] = [
                {
                    "source": item.source_text,
                    "target": item.required_target,
                    "notes": item.notes,
                }
                for item in request.context.glossary
            ]
        return {
            "source_language": request.source_language,
            "target_language": request.target_language,
            "context": context,
            "source_text": request.source_text,
        }

    @classmethod
    def _reject_prompt_leakage(cls, translated: str, source_text: str) -> None:
        lines = tuple(line.strip() for line in translated.splitlines())
        leaked = next(
            (
                label
                for label in cls._PROMPT_LABELS
                if label not in source_text
                and any(line.startswith(label) for line in lines)
            ),
            None,
        )
        if leaked is not None:
            raise ProviderError(f"Ollama bağlam metadatasını çıktıya sızdırdı: {leaked}")

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        payload = {
            "model": self._model,
            "stream": False,
            "format": self._OUTPUT_SCHEMA,
            "messages": [
                {"role": "system", "content": self._system_prompt(request)},
                {
                    "role": "user",
                    "content": json.dumps(
                        self._user_payload(request),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            "options": {
                "temperature": self._quality.temperature,
                "num_ctx": self._quality.context_window,
            },
        }
        try:
            response = self._client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = cast(dict[str, object], response.json())
            message = cast(dict[str, object], data["message"])
            content = cast(str, message["content"])
            structured = cast(dict[str, object], json.loads(content))
            translated = structured["translation"]
            if not isinstance(translated, str):
                raise TypeError("translation string değil")
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise TemporaryProviderError(f"Ollama bağlantı hatası: {error}") from error
        except httpx.HTTPStatusError as error:
            if error.response.status_code >= 500:
                raise TemporaryProviderError(
                    f"Geçici Ollama HTTP hatası: {error.response.status_code}"
                ) from error
            raise ProviderError(f"Ollama HTTP hatası: {error.response.status_code}") from error
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ProviderError("Ollama yapılandırılmış yanıtı geçersiz") from error
        translated = translated.strip()
        if not translated:
            raise ProviderError("Ollama boş çeviri döndürdü")
        self._reject_prompt_leakage(translated, request.source_text)
        return TranslationResponse(translated, self.name, self._model)


class TranslateGemmaOllamaProvider(OllamaProvider):
    """Ollama adapter for TranslateGemma's strict direct-translation prompt."""

    @property
    def name(self) -> str:
        return "ollama-translategemma"

    @staticmethod
    def _translation_prompt(request: TranslationRequest) -> str:
        placeholder_rule = ""
        if "__RENTR_" in request.source_text:
            placeholder_rule = (
                " Immutable __RENTR_0000__-style control placeholders are opaque literal tokens. "
                "Copy each placeholder exactly once and in the same order. Never translate, "
                "rename, omit, annotate, describe, or append layout metadata to them. Output only "
                "the translated sentence containing the bare placeholders already present in the "
                "source."
            )
        return (
            "You are a professional English (en) to Turkish (tr) translator. "
            "Accurately convey the original meaning, character register, profanity, slang, "
            "sexual explicitness and emotional intensity in natural contemporary Turkish. "
            "Do not censor, sanitize, euphemize, explain, or offer alternative translations."
            f"{placeholder_rule}\n"
            "Produce only the Turkish translation, without any additional explanations or "
            "commentary. Please translate the following English text into Turkish:\n\n\n"
            f"{request.source_text}"
        )

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        payload = {
            "model": self._model,
            "stream": False,
            "messages": [
                {"role": "user", "content": self._translation_prompt(request)},
            ],
            "options": {
                "temperature": 0.1,
                "num_ctx": min(self._quality.context_window, 2048),
            },
        }
        try:
            response = self._client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = cast(dict[str, object], response.json())
            message = cast(dict[str, object], data["message"])
            translated = message["content"]
            if not isinstance(translated, str):
                raise TypeError("content string değil")
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise TemporaryProviderError(f"Ollama bağlantı hatası: {error}") from error
        except httpx.HTTPStatusError as error:
            if error.response.status_code >= 500:
                raise TemporaryProviderError(
                    f"Geçici Ollama HTTP hatası: {error.response.status_code}"
                ) from error
            raise ProviderError(f"Ollama HTTP hatası: {error.response.status_code}") from error
        except (KeyError, TypeError, ValueError) as error:
            raise ProviderError("TranslateGemma Ollama yanıtı geçersiz") from error

        translated = translated.strip()
        if not translated:
            raise ProviderError("TranslateGemma boş çeviri döndürdü")
        self._reject_prompt_leakage(translated, request.source_text)
        return TranslationResponse(translated, self.name, self._model)


class OllamaSemanticRepairProvider:
    """Context-aware Turkish post-editor for risky first-pass translations."""

    _OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {"translation": {"type": "string"}},
        "required": ["translation"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        quality: QualityProfile = QualityProfile.BALANCED,
        timeout_seconds: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not model.strip() or not base_url.strip():
            raise ValueError("Ollama repair modeli ve adresi boş olamaz")
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._quality = quality
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None

    @property
    def name(self) -> str:
        return "ollama-semantic-repair"

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    @staticmethod
    def _system_prompt(request: SemanticRepairRequest) -> str:
        token_rule = (
            "The source contains __RENTR_0000__-style placeholders. Preserve every placeholder "
            "exactly once and in the same order. Treat them as opaque literal tokens: never "
            "annotate them with layout descriptions such as attached_left/source_suffix. The "
            "base translation may have damaged or omitted them; the source is authoritative."
            if "__RENTR_" in request.source_text
            else "Do not invent __RENTR_ placeholders or Ren'Py control syntax."
        )
        return " ".join(
            (
                "You are the semantic post-editor for a Turkish visual-novel localization.",
                "Compare source_text with base_translation and return one corrected Turkish line.",
                "If the base translation is already faithful, natural and appropriately toned, "
                "return it unchanged.",
                "The English source is authoritative; never preserve a mistake just because it "
                "appears in the base translation.",
                "Use the surrounding dialogue, speaker and character guidance only to resolve "
                "meaning, register and pronouns. Never copy context into the answer.",
                "Preserve profanity, sexual meaning, slang, emotional intensity and character "
                "attitude. Do not censor, euphemize or make casual dialogue formal.",
                "Explicit or vulgar wording is not a defect here. When the English source is "
                "directly sexual, the Turkish must be equally direct rather than safer/politer.",
                "Use real natural Turkish words; never transliterate English sexual slang into "
                "invented pseudo-Turkish forms.",
                "Use natural contemporary Turkish. For character dialogue, prefer singular "
                "informal sen unless character guidance explicitly requests siz.",
                "Do not offer alternatives, explanations, labels, parentheses about content, or "
                "translator commentary.",
                "Do not add events, actions or details absent from source_text.",
                token_rule,
                "Return exactly one JSON object matching the requested schema and nothing else.",
            )
        )

    @staticmethod
    def _user_payload(request: SemanticRepairRequest) -> dict[str, object]:
        context: dict[str, object] = {}
        if request.context.speaker:
            context["speaker"] = request.context.speaker
        if request.context.label:
            context["scene_label"] = request.context.label
        if request.context.previous_source_text:
            context["previous_source"] = request.context.previous_source_text
        if request.context.next_source_text:
            context["next_source"] = request.context.next_source_text
        if request.context.character:
            character = request.context.character
            context["character"] = {
                "display_name": character.display_name,
                "address_style": character.address_style,
                "voice_traits": list(character.traits),
                "notes": character.notes,
            }
        if request.context.glossary:
            context["required_terms"] = [
                {
                    "source": item.source_text,
                    "target": item.required_target,
                    "notes": item.notes,
                }
                for item in request.context.glossary
            ]
        return {
            "source_language": request.source_language,
            "target_language": request.target_language,
            "risk_reasons": list(request.risk_reasons),
            "semantic_guardrails": list(semantic_guardrails(request.source_text)),
            "context": context,
            "source_text": request.source_text,
            "base_translation": request.base_translation,
        }

    def repair(self, request: SemanticRepairRequest) -> SemanticRepairResponse:
        payload = {
            "model": self._model,
            "stream": False,
            "format": self._OUTPUT_SCHEMA,
            "messages": [
                {"role": "system", "content": self._system_prompt(request)},
                {
                    "role": "user",
                    "content": json.dumps(
                        self._user_payload(request),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            "options": {
                "temperature": min(self._quality.temperature, 0.2),
                "num_ctx": self._quality.context_window,
            },
        }
        try:
            response = self._client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = cast(dict[str, object], response.json())
            message = cast(dict[str, object], data["message"])
            content = cast(str, message["content"])
            structured = cast(dict[str, object], json.loads(content))
            translated = structured["translation"]
            if not isinstance(translated, str):
                raise TypeError("translation string değil")
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise TemporaryProviderError(f"Ollama repair bağlantı hatası: {error}") from error
        except httpx.HTTPStatusError as error:
            if error.response.status_code >= 500:
                raise TemporaryProviderError(
                    f"Geçici Ollama repair HTTP hatası: {error.response.status_code}"
                ) from error
            raise ProviderError(
                f"Ollama repair HTTP hatası: {error.response.status_code}"
            ) from error
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ProviderError("Ollama semantic repair yanıtı geçersiz") from error

        translated = translated.strip()
        if not translated:
            raise ProviderError("Ollama semantic repair boş çeviri döndürdü")
        OllamaProvider._reject_prompt_leakage(translated, request.source_text)
        return SemanticRepairResponse(translated, self.name, self._model)


class OllamaCandidateJudgeProvider:
    """Pairwise semantic judge that selects a candidate without rewriting it."""

    _OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["base", "repair", "reject"]},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "reasons": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 6,
            },
        },
        "required": ["decision", "confidence", "reasons"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        quality: QualityProfile = QualityProfile.BALANCED,
        timeout_seconds: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not model.strip() or not base_url.strip():
            raise ValueError("Ollama judge modeli ve adresi boş olamaz")
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._quality = quality
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None

    @property
    def name(self) -> str:
        return "ollama-candidate-judge"

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    @staticmethod
    def _system_prompt() -> str:
        return " ".join(
            (
                "You are a strict pairwise judge for English-to-Turkish visual-novel localization.",
                "You receive the English source and exactly two Turkish candidates named BASE "
                "and REPAIR.",
                "Do not translate, rewrite, merge, or propose a third wording. Select BASE, "
                "REPAIR, or REJECT.",
                "Neither candidate is presumed better because of its label.",
                "Judge source meaning first: reject meaning reversals, omissions, invented "
                "details, and wrong idioms.",
                "Then judge natural contemporary Turkish, character register, pronouns, "
                "emotional intensity, slang, profanity, and explicit sexual meaning.",
                "Explicitness itself is never a defect. Never reject or penalize a candidate "
                "merely because it is sexually direct or vulgar when the source is direct.",
                "Do not reward censorship or euphemism when the English source is explicit. "
                "For example, anal sex may be anal seks/anal ilişki and sexual fuck should not "
                "be softened into birlikte olmak or yatmak.",
                "Reject malformed/invented pseudo-Turkish words and untranslated English sexual "
                "slang when a natural Turkish expression is required.",
                "Prefer informal singular Turkish for casual character dialogue unless character "
                "guidance explicitly asks for formal siz.",
                "Choose reject only for material semantic/naturalness failures in both candidates; "
                "a mere style preference or direct explicit wording is not enough.",
                "If both candidates are materially wrong, choose reject.",
                "Common traps: holding my own means keeping up/competing successfully, never "
                "kendi başımayım; what about you? normally means ya sen?, not sen ne düşünüyorsun; "
                "here you go when handing something is typically buyur/al, not işte o; an "
                "unfinished what the...?! must not become a specific ne yapıyorsun?! claim; and a "
                "bare Turkish lanet is not a natural standalone equivalent of an English "
                "sexual/profane fuck exclamation.",
                "If they are effectively tied, choose base; repair must be clearly better to "
                "replace a valid base.",
                "Return only the requested JSON object.",
            )
        )

    @staticmethod
    def _user_payload(request: CandidateSelectionRequest) -> dict[str, object]:
        context: dict[str, object] = {}
        if request.context.speaker:
            context["speaker"] = request.context.speaker
        if request.context.label:
            context["scene_label"] = request.context.label
        if request.context.previous_source_text:
            context["previous_source"] = request.context.previous_source_text
        if request.context.next_source_text:
            context["next_source"] = request.context.next_source_text
        if request.context.character:
            character = request.context.character
            context["character"] = {
                "display_name": character.display_name,
                "address_style": character.address_style,
                "voice_traits": list(character.traits),
                "notes": character.notes,
            }
        return {
            "source_language": request.source_language,
            "target_language": request.target_language,
            "semantic_guardrails": list(semantic_guardrails(request.source_text)),
            "context": context,
            "source_text": request.source_text,
            "base": request.base_translation,
            "repair": request.repair_translation,
            "base_risk_reasons": list(request.base_risk_reasons),
            "repair_risk_reasons": list(request.repair_risk_reasons),
        }

    def select(self, request: CandidateSelectionRequest) -> CandidateSelectionResponse:
        payload = {
            "model": self._model,
            "stream": False,
            "format": self._OUTPUT_SCHEMA,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(
                        self._user_payload(request),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            "options": {
                "temperature": 0.0,
                "num_ctx": self._quality.context_window,
            },
        }
        try:
            response = self._client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = cast(dict[str, object], response.json())
            message = cast(dict[str, object], data["message"])
            content = cast(str, message["content"])
            structured = cast(dict[str, object], json.loads(content))
            decision_raw = structured["decision"]
            confidence_raw = structured["confidence"]
            reasons_raw = structured["reasons"]
            if not isinstance(decision_raw, str):
                raise TypeError("decision string değil")
            if not isinstance(confidence_raw, (int, float)) or isinstance(confidence_raw, bool):
                raise TypeError("confidence number değil")
            if not isinstance(reasons_raw, list) or not all(
                isinstance(item, str) for item in reasons_raw
            ):
                raise TypeError("reasons string listesi değil")
            decision = CandidateDecision(decision_raw)
            confidence = float(confidence_raw)
            if not 0.0 <= confidence <= 1.0:
                raise ValueError("confidence aralık dışında")
            reasons = tuple(item.strip() for item in reasons_raw if item.strip())
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise TemporaryProviderError(f"Ollama judge bağlantı hatası: {error}") from error
        except httpx.HTTPStatusError as error:
            if error.response.status_code >= 500:
                raise TemporaryProviderError(
                    f"Geçici Ollama judge HTTP hatası: {error.response.status_code}"
                ) from error
            raise ProviderError(
                f"Ollama judge HTTP hatası: {error.response.status_code}"
            ) from error
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise ProviderError("Ollama candidate judge yanıtı geçersiz") from error

        return CandidateSelectionResponse(
            decision=decision,
            confidence=confidence,
            reasons=reasons,
            provider=self.name,
            model=self._model,
        )


def build_ollama_repair_provider(
    *,
    model: str,
    base_url: str = "http://127.0.0.1:11434",
    quality: QualityProfile = QualityProfile.BALANCED,
    timeout_seconds: float = 120.0,
    client: httpx.Client | None = None,
) -> OllamaSemanticRepairProvider:
    """Build the context-aware second-pass post-editor."""
    return OllamaSemanticRepairProvider(
        model=model,
        base_url=base_url,
        quality=quality,
        timeout_seconds=timeout_seconds,
        client=client,
    )


def build_ollama_judge_provider(
    *,
    model: str,
    base_url: str = "http://127.0.0.1:11434",
    quality: QualityProfile = QualityProfile.BALANCED,
    timeout_seconds: float = 120.0,
    client: httpx.Client | None = None,
) -> OllamaCandidateJudgeProvider:
    """Build the pairwise candidate selector."""
    return OllamaCandidateJudgeProvider(
        model=model,
        base_url=base_url,
        quality=quality,
        timeout_seconds=timeout_seconds,
        client=client,
    )


def build_ollama_provider(
    *,
    model: str,
    base_url: str = "http://127.0.0.1:11434",
    quality: QualityProfile = QualityProfile.BALANCED,
    timeout_seconds: float = 120.0,
    client: httpx.Client | None = None,
) -> OllamaProvider:
    """Select the strict TranslateGemma adapter when the model name requires it."""
    provider_type = (
        TranslateGemmaOllamaProvider
        if "translategemma" in model.casefold()
        else OllamaProvider
    )
    return provider_type(
        model=model,
        base_url=base_url,
        quality=quality,
        timeout_seconds=timeout_seconds,
        client=client,
    )
