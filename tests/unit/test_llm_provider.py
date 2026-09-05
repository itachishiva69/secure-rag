from unittest.mock import MagicMock, patch

import pytest
from openai import APIError

from app.services.context import (
    ContextResult,
    ContextSource,
)
from app.services.llm_provider import (
    LLMProviderError,
    OpenAICompatibleProvider,
)


def create_context():
    return ContextResult(
        text=(
            "[Source: finance-policy.txt, chunk 0]\n"
            "Finance department policy information."
        ),
        sources=[
            ContextSource(
                document_id=1,
                filename="finance-policy.txt",
                chunk_index=0,
            )
        ],
    )


@patch("app.services.llm_provider.OpenAI")
def test_provider_generates_answer(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content="Generated answer."
            )
        )
    ]

    mock_client.chat.completions.create.return_value = (
        mock_response
    )

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="test-model",
        base_url="https://example.com/v1",
    )

    result = provider.generate(
        query="What is the finance policy?",
        context=create_context(),
    )

    assert result == "Generated answer."

    mock_openai.assert_called_once_with(
        api_key="test-key",
        base_url="https://example.com/v1",
        timeout=30.0,
    )

    mock_client.chat.completions.create.assert_called_once()


@patch("app.services.llm_provider.OpenAI")
def test_provider_passes_custom_timeout(mock_openai):
    OpenAICompatibleProvider(
        api_key="test-key",
        model="test-model",
        base_url="https://example.com/v1",
        timeout=12.5,
    )

    mock_openai.assert_called_once_with(
        api_key="test-key",
        base_url="https://example.com/v1",
        timeout=12.5,
    )


@patch("app.services.llm_provider.OpenAI")
def test_provider_converts_api_error_to_provider_error(
    mock_openai,
):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    mock_client.chat.completions.create.side_effect = (
        APIError(
            "provider failure",
            request=None,
            body=None,
        )
    )

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="test-model",
        base_url="https://example.com/v1",
    )

    with pytest.raises(
        LLMProviderError,
        match="LLM provider request failed",
    ):
        provider.generate(
            query="What is the finance policy?",
            context=create_context(),
        )


@patch("app.services.llm_provider.OpenAI")
def test_provider_rejects_response_without_choices(
    mock_openai,
):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    mock_response = MagicMock()
    mock_response.choices = []

    mock_client.chat.completions.create.return_value = (
        mock_response
    )

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="test-model",
        base_url="https://example.com/v1",
    )

    with pytest.raises(
        LLMProviderError,
        match="LLM provider returned no choices",
    ):
        provider.generate(
            query="What is the finance policy?",
            context=create_context(),
        )


@patch("app.services.llm_provider.OpenAI")
def test_provider_handles_none_content(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(content=None)
        )
    ]

    mock_client.chat.completions.create.return_value = (
        mock_response
    )

    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="test-model",
        base_url="https://example.com/v1",
    )

    result = provider.generate(
        query="What is the finance policy?",
        context=create_context(),
    )

    assert result == ""