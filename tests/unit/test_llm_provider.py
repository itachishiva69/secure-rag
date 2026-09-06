from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from app.services.context import ContextResult
from app.services.llm_provider import (
    LLMProviderError,
    OpenAICompatibleProvider,
)


def make_context() -> ContextResult:
    return ContextResult(
        text="The company has a finance policy.",
        sources=[],
    )


def make_provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        api_key="test-key",
        model="test-model",
        base_url="https://example.com/v1",
        timeout=5.0,
    )


def make_response(content: str | None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=content,
                )
            )
        ]
    )


def test_generate_returns_stripped_content():
    provider = make_provider()

    provider.client.chat.completions.create = Mock(
        return_value=make_response(
            "  The finance policy applies.  "
        )
    )

    result = provider.generate(
        query="What is the finance policy?",
        context=make_context(),
    )

    assert result == "The finance policy applies."


def test_generate_rejects_empty_content():
    provider = make_provider()

    provider.client.chat.completions.create = Mock(
        return_value=make_response("   ")
    )

    with pytest.raises(
        LLMProviderError,
        match="empty content",
    ):
        provider.generate(
            query="What is the finance policy?",
            context=make_context(),
        )


def test_generate_rejects_missing_content():
    provider = make_provider()

    provider.client.chat.completions.create = Mock(
        return_value=make_response(None)
    )

    with pytest.raises(
        LLMProviderError,
        match="no content",
    ):
        provider.generate(
            query="What is the finance policy?",
            context=make_context(),
        )


def test_generate_rejects_missing_choices():
    provider = make_provider()

    provider.client.chat.completions.create = Mock(
        return_value=SimpleNamespace(
            choices=[]
        )
    )

    with pytest.raises(
        LLMProviderError,
        match="no choices",
    ):
        provider.generate(
            query="What is the finance policy?",
            context=make_context(),
        )


@pytest.mark.parametrize(
    "exception_factory,expected_message",
    [
        (
            lambda: APITimeoutError(
                request=Mock()
            ),
            "timed out",
        ),
        (
            lambda: APIConnectionError(
                request=Mock()
            ),
            "connection failed",
        ),
        (
            lambda: RateLimitError(
                message="rate limited",
                response=Mock(),
                body=None,
            ),
            "rate limit exceeded",
        ),
        (
            lambda: InternalServerError(
                message="server error",
                response=Mock(),
                body=None,
            ),
            "server error",
        ),
    ],
)
def test_generate_maps_provider_failures(
    exception_factory,
    expected_message,
):
    provider = make_provider()

    provider.client.chat.completions.create = Mock(
        side_effect=exception_factory()
    )

    with pytest.raises(
        LLMProviderError,
        match=expected_message,
    ):
        provider.generate(
            query="What is the finance policy?",
            context=make_context(),
        )


def test_generate_preserves_unexpected_exceptions():
    provider = make_provider()

    provider.client.chat.completions.create = Mock(
        side_effect=RuntimeError(
            "unexpected provider failure"
        )
    )

    with pytest.raises(
        RuntimeError,
        match="unexpected provider failure",
    ):
        provider.generate(
            query="What is the finance policy?",
            context=make_context(),
        )