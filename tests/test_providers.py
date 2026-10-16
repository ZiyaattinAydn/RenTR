from __future__ import annotations

import json

import httpx
import pytest

from rentr.providers import (
    OpenAICompatibleProvider,
    ProviderError,
    TemporaryProviderError,
    TranslationContext,
    TranslationRequest,
)


def _request() -> TranslationRequest:
    return TranslationRequest(
        unit_id="start_deadbeef",
        source_text="Hello, __RENTR_0000__!",
        source_language="English",
        target_language="Turkish",
        context=TranslationContext(
            speaker="eileen",
            label="start",
            previous_source_text="Previous line",
            next_source_text="Next line",
        ),
    )


def test_openai_compatible_adapter_sends_structured_request() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Merhaba, __RENTR_0000__!"}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1/",
        api_key="secret-test-key",
        model="translator-test",
        client=client,
    )

    response = provider.translate(_request())

    assert response.translated_text == "Merhaba, __RENTR_0000__!"
    assert captured["authorization"] == "Bearer secret-test-key"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "translator-test"
    assert "Speaker: eileen" in payload["messages"][1]["content"]
    assert "Previous source: Previous line" in payload["messages"][1]["content"]
    assert "Next source: Next line" in payload["messages"][1]["content"]
    assert "do not translate" not in payload["messages"][1]["content"]
    assert "word-for-word" in payload["messages"][0]["content"]


@pytest.mark.parametrize("status", [400, 401, 403])
def test_non_retryable_http_errors_fail(status: int) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(status, text="bad"))
    )
    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key="test-key",
        model="test",
        client=client,
    )

    with pytest.raises(ProviderError):
        provider.translate(_request())


@pytest.mark.parametrize("status", [408, 429, 500, 503])
def test_retryable_http_errors_are_classified(status: int) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(status, text="later"))
    )
    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key="test-key",
        model="test",
        client=client,
    )

    with pytest.raises(TemporaryProviderError):
        provider.translate(_request())


def test_invalid_response_schema_is_rejected() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"choices": []}))
    )
    provider = OpenAICompatibleProvider(
        base_url="https://provider.example/v1",
        api_key="test-key",
        model="test",
        client=client,
    )

    with pytest.raises(ProviderError, match="şeması"):
        provider.translate(_request())
