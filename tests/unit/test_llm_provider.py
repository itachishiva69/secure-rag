from types import SimpleNamespace

from app.services.context import (
    ContextResult,
    ContextSource,
)
from app.services.llm_provider import (
    OpenAICompatibleProvider,
)


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(
        self,
        *,
        model,
        temperature,
        messages,
    ):
        self.calls.append(
            {
                "model": model,
                "temperature": temperature,
                "messages": messages,
            }
        )

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Generated answer."
                    )
                )
            ]
        )


class FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(
            completions=FakeCompletions()
        )


def create_provider():
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="test-model",
        base_url="https://example.com/v1",
    )

    provider.client = FakeClient()

    return provider


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


def test_provider_generates_answer():
    provider = create_provider()

    result = provider.generate(
        query="What is the finance policy?",
        context=create_context(),
    )

    assert result == "Generated answer."

    calls = provider.client.chat.completions.calls

    assert len(calls) == 1

    call = calls[0]

    assert call["model"] == "test-model"
    assert call["temperature"] == 0.1

    messages = call["messages"]

    assert len(messages) == 2

    assert messages[0]["role"] == "system"

    assert (
        "only the supplied document context"
        in messages[0]["content"]
    )

    assert messages[1]["role"] == "user"

    assert (
        "Finance department policy information."
        in messages[1]["content"]
    )

    assert (
        "What is the finance policy?"
        in messages[1]["content"]
    )


def test_provider_does_not_send_source_metadata_to_llm():
    provider = create_provider()

    context = ContextResult(
        text=(
            "[Source: finance-policy.txt, chunk 0]\n"
            "Confidential finance information."
        ),
        sources=[
            ContextSource(
                document_id=100,
                filename="finance-policy.txt",
                chunk_index=0,
            )
        ],
    )

    provider.generate(
        query="Tell me about finance.",
        context=context,
    )

    messages = (
        provider.client
        .chat
        .completions
        .calls[0]["messages"]
    )

    user_message = messages[1]["content"]

    assert "Confidential finance information." in (
        user_message
    )

    # Internal source metadata is not separately
    # transmitted to the LLM.
    assert "document_id" not in user_message
    assert "department_ids" not in user_message


def test_provider_returns_empty_string_when_llm_returns_none():
    provider = create_provider()

    provider.client.chat.completions.create = (
        lambda **kwargs: SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=None
                    )
                )
            ]
        )
    )

    result = provider.generate(
        query="Test question",
        context=create_context(),
    )

    assert result == ""
