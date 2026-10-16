from __future__ import annotations

import json

import httpx
import pytest

from rentr.local_models import (
    HardwareProfile,
    ModelRequirement,
    OllamaProvider,
    QualityProfile,
    Suitability,
    TranslateGemmaOllamaProvider,
    assess_model,
    build_ollama_judge_provider,
    build_ollama_provider,
    build_ollama_repair_provider,
)
from rentr.providers import (
    CandidateDecision,
    CandidateSelectionRequest,
    CharacterGuidance,
    GlossaryHint,
    ProviderError,
    SemanticRepairRequest,
    TranslationContext,
    TranslationRequest,
    TranslationSuggestion,
)


def _request(source_text: str = "Hello __RENTR_0000__") -> TranslationRequest:
    return TranslationRequest(
        unit_id="start_deadbeef",
        source_text=source_text,
        source_language="English",
        target_language="Turkish",
        context=TranslationContext(
            speaker="eileen",
            label="start",
            previous_source_text="Previous line",
            next_source_text="Next line",
            suggestions=(TranslationSuggestion("Hi", "Selam", 0.9),),
            glossary=(GlossaryHint("Save", "Kaydet", "UI term"),),
            character=CharacterGuidance(
                display_name="Eileen",
                address_style="sen",
                traits=("warm",),
                notes="Uses casual Turkish",
            ),
        ),
    )


@pytest.mark.parametrize(
    ("memory", "expected"),
    [(3.0, Suitability.INSUFFICIENT), (6.0, Suitability.LIMITED), (12.0, Suitability.SUITABLE)],
)
def test_assesses_model_against_memory(memory: float, expected: Suitability) -> None:
    assessment = assess_model(
        HardwareProfile("Test", 4, memory),
        ModelRequirement("model", 4.0, 8.0),
    )

    assert assessment.suitability is expected


def test_ollama_adapter_uses_structured_output_and_separates_context() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"message": {"content": '{"translation":"Merhaba __RENTR_0000__"}'}},
        )

    provider = OllamaProvider(
        model="translator:latest",
        quality=QualityProfile.HIGH,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = provider.translate(_request())

    assert response.translated_text == "Merhaba __RENTR_0000__"
    assert captured["options"] == {"temperature": 0.25, "num_ctx": 8192}
    assert captured["format"] == OllamaProvider._OUTPUT_SCHEMA
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    system_prompt = messages[0]["content"]
    assert "Translate only source_text" in system_prompt
    assert "Do not censor or soften" in system_prompt
    assert "Preserve every __RENTR_0000__-style placeholder" in system_prompt
    user_payload = json.loads(messages[1]["content"])
    assert user_payload["source_text"] == "Hello __RENTR_0000__"
    assert user_payload["context"]["previous_source"] == "Previous line"
    assert user_payload["context"]["next_source"] == "Next line"
    assert user_payload["context"]["scene_label"] == "start"
    assert user_payload["context"]["review_only_similar_translations"][0]["translation"] == "Selam"
    assert user_payload["context"]["character"]["notes"] == "Uses casual Turkish"


def test_ollama_prompt_without_tokens_forbids_inventing_placeholders() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": '{"translation":"Tabii."}'}})

    provider = OllamaProvider(
        model="translator:latest",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert provider.translate(_request("Obviously.")).translated_text == "Tabii."
    messages = captured["messages"]
    assert isinstance(messages, list)
    first_message = messages[0]
    assert isinstance(first_message, dict)
    content = first_message["content"]
    assert isinstance(content, str)
    assert "Do not invent __RENTR_ placeholders" in content


def test_ollama_rejects_context_metadata_leakage() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "message": {
                        "content": '{"translation":"Scene label: start\\nText: Merhaba"}'
                    }
                },
            )
        )
    )

    with pytest.raises(ProviderError, match="metadatasını"):
        OllamaProvider(model="one", client=client).translate(_request("Hello"))


def test_ollama_rejects_invalid_structured_response() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"message": {"content": "Merhaba"}},
            )
        )
    )

    with pytest.raises(ProviderError, match="yapılandırılmış"):
        OllamaProvider(model="one", client=client).translate(_request())


def test_lists_installed_ollama_models() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"models": [{"name": "one:latest"}, {"name": "two:7b"}]},
            )
        )
    )

    assert OllamaProvider(model="one", client=client).list_models() == (
        "one:latest",
        "two:7b",
    )


def test_translategemma_adapter_uses_strict_single_user_prompt() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "Merhaba __RENTR_0000__"}})

    provider = build_ollama_provider(
        model="translategemma:12b",
        quality=QualityProfile.HIGH,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = provider.translate(_request())

    assert isinstance(provider, TranslateGemmaOllamaProvider)
    assert response.provider == "ollama-translategemma"
    assert response.translated_text == "Merhaba __RENTR_0000__"
    assert "format" not in captured
    assert captured["options"] == {"temperature": 0.1, "num_ctx": 2048}
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 1
    message = messages[0]
    assert isinstance(message, dict)
    assert message["role"] == "user"
    content = message["content"]
    assert isinstance(content, str)
    assert "English (en) to Turkish (tr)" in content
    assert "Previous line" not in content
    assert "Next line" not in content
    assert content.endswith("\n\n\nHello __RENTR_0000__")


def test_ollama_factory_keeps_contextual_adapter_for_general_models() -> None:
    provider = build_ollama_provider(
        model="aya-expanse:8b",
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(500))),
    )

    assert type(provider) is OllamaProvider


def test_semantic_repair_adapter_compares_base_with_context_and_returns_json() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"message": {"content": '{"translation":"Etrafında çekici kız çok."}'}},
        )

    provider = build_ollama_repair_provider(
        model="aya-expanse:8b",
        quality=QualityProfile.BALANCED,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    response = provider.repair(
        SemanticRepairRequest(
            unit_id="u1",
            source_text="There are hot girls around him.",
            base_translation="Etrafında sıcak kızlar var.",
            source_language="English",
            target_language="Turkish",
            context=TranslationContext(
                speaker="b",
                previous_source_text="He is popular.",
                next_source_text="Yeah.",
            ),
            risk_reasons=("hot_literalized_as_temperature",),
        )
    )

    assert response.translated_text == "Etrafında çekici kız çok."
    assert response.provider == "ollama-semantic-repair"
    assert captured["format"] == provider._OUTPUT_SCHEMA
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 2
    system = messages[0]
    assert isinstance(system, dict)
    assert "Do not censor" in str(system["content"])
    user = messages[1]
    assert isinstance(user, dict)
    payload = json.loads(str(user["content"]))
    assert payload["base_translation"] == "Etrafında sıcak kızlar var."
    assert payload["context"]["previous_source"] == "He is popular."
    assert payload["risk_reasons"] == ["hot_literalized_as_temperature"]


def test_candidate_judge_adapter_selects_without_rewriting() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": (
                        '{"decision":"base","confidence":0.93,'
                        '"reasons":["base_more_natural","same_meaning"]}'
                    )
                }
            },
        )

    provider = build_ollama_judge_provider(
        model="aya-expanse:8b",
        quality=QualityProfile.BALANCED,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    response = provider.select(
        CandidateSelectionRequest(
            unit_id="u1",
            source_text="Damn...! When did you get so good at this?",
            base_translation="Lan...! Ne zaman bu kadar iyi oldun?",
            repair_translation="Lan, bu ne kadar usta oldun sen?!",
            source_language="English",
            target_language="Turkish",
            context=TranslationContext(speaker="i", label="scene"),
            base_risk_reasons=("explicit_or_slang_source",),
            repair_risk_reasons=("explicit_or_slang_source",),
        )
    )

    assert response.decision is CandidateDecision.BASE
    assert response.confidence == 0.93
    assert response.reasons == ("base_more_natural", "same_meaning")
    assert captured["format"] == provider._OUTPUT_SCHEMA
    messages = captured["messages"]
    assert isinstance(messages, list)
    system = messages[0]
    assert isinstance(system, dict)
    assert "Do not translate, rewrite, merge" in str(system["content"])
    user = messages[1]
    assert isinstance(user, dict)
    payload = json.loads(str(user["content"]))
    assert payload["base"] == "Lan...! Ne zaman bu kadar iyi oldun?"
    assert payload["repair"] == "Lan, bu ne kadar usta oldun sen?!"


def test_translategemma_prompt_explicitly_preserves_uncensored_meaning_and_placeholders() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"message": {"content": "Sik beni __RENTR_0000__"}},
        )

    provider = build_ollama_provider(
        model="translategemma:12b",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider.translate(_request("Fuck me __RENTR_0000__"))

    messages = captured["messages"]
    assert isinstance(messages, list)
    content = str(messages[0]["content"])
    assert "Do not censor, sanitize, euphemize" in content
    assert "Immutable __RENTR_0000__-style control placeholders" in content
    assert "opaque literal tokens" in content
    assert "source_suffix" not in content
    assert "attached_left" not in content


def test_semantic_repair_payload_includes_guardrails_without_layout_leakage() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"message": {"content": '{"translation":"Sik beni __RENTR_0000__"}'}},
        )

    provider = build_ollama_repair_provider(
        model="aya-expanse:8b",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider.repair(
        SemanticRepairRequest(
            unit_id="u-explicit",
            source_text="Fuck me __RENTR_0000__",
            base_translation="Benimle ol __RENTR_0000__",
            source_language="English",
            target_language="Turkish",
            context=TranslationContext(speaker="h"),
            risk_reasons=("sexual_fuck_semantics_softened",),
        )
    )

    messages = captured["messages"]
    assert isinstance(messages, list)
    payload = json.loads(str(messages[1]["content"]))
    assert any(
        str(rule).startswith("sexual_fuck:") for rule in payload["semantic_guardrails"]
    )
    assert "placeholder_contract" not in payload


def test_candidate_judge_prompt_forbids_euphemism_bias_and_bad_transliteration() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": (
                        '{"decision":"base","confidence":0.96,'
                        '"reasons":["direct_explicitness_matches_source"]}'
                    )
                }
            },
        )

    provider = build_ollama_judge_provider(
        model="qwen3:8b",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider.select(
        CandidateSelectionRequest(
            unit_id="u-anal",
            source_text="How about some anal sex?",
            base_translation="Biraz anal seks yapmaya ne dersin?",
            repair_translation="Biraz anal ilişkiye ne dersin?",
            source_language="English",
            target_language="Turkish",
            context=TranslationContext(speaker="l"),
            base_risk_reasons=("explicit_or_slang_source",),
            repair_risk_reasons=("explicit_or_slang_source",),
        )
    )

    messages = captured["messages"]
    assert isinstance(messages, list)
    system = str(messages[0]["content"])
    assert "Explicitness itself is never a defect" in system
    assert "pseudo-Turkish" in system
    payload = json.loads(str(messages[1]["content"]))
    assert any(str(rule).startswith("anal_sex:") for rule in payload["semantic_guardrails"])


def test_translategemma_inline_placeholder_prompt_never_exposes_layout_metadata() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"message": {"content": "Senin için söylemesi kolay __RENTR_0000__"}},
        )

    provider = build_ollama_provider(
        model="translategemma:12b",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider.translate(_request("Easy for y--__RENTR_0000__you to say."))

    messages = captured["messages"]
    assert isinstance(messages, list)
    combined = "\n".join(str(message["content"]) for message in messages)
    assert "Easy for y--__RENTR_0000__you to say." in combined
    assert "attached_left" not in combined
    assert "attached_right" not in combined
    assert "source_suffix" not in combined
    assert "placeholder_contract" not in combined


def test_candidate_judge_prompt_warns_about_known_idiom_and_register_traps() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": '{"decision":"base","confidence":0.9,"reasons":["faithful"]}'
                }
            },
        )

    provider = build_ollama_judge_provider(
        model="qwen3:8b",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider.select(
        CandidateSelectionRequest(
            unit_id="u-idiom",
            source_text="I was holding my own. Here you go.",
            base_translation="İdare ediyordum. Buyur.",
            repair_translation="Kendi başımayım. İşte o.",
            source_language="English",
            target_language="Turkish",
            context=TranslationContext(),
        )
    )

    messages = captured["messages"]
    assert isinstance(messages, list)
    system = str(messages[0]["content"])
    assert "holding my own" in system.lower()
    assert "here you go" in system.lower()
    assert "what about you" in system.lower()
    assert "bare Turkish lanet" in system
