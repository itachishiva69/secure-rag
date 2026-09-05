import pytest

from app.services.context import (
    ContextResult,
    ContextSource,
)
from app.services.generation import (
    GenerationService,
)


class FakeProvider:
    def __init__(
        self,
        answer="Generated answer.",
    ):
        self.answer = answer
        self.calls = []

    def generate(
        self,
        *,
        query,
        context,
    ):
        self.calls.append(
            {
                "query": query,
                "context": context,
            }
        )

        return self.answer


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


def test_generation_service_generates_answer():
    provider = FakeProvider()

    service = GenerationService(
        provider=provider,
    )

    context = create_context()

    result = service.generate_answer(
        query="What is the finance policy?",
        context=context,
    )

    assert result.answer == "Generated answer."

    assert len(provider.calls) == 1

    call = provider.calls[0]

    assert call["query"] == (
        "What is the finance policy?"
    )

    assert call["context"] == context


def test_generation_service_strips_answer():
    provider = FakeProvider(
        answer="  Generated answer.  "
    )

    service = GenerationService(
        provider=provider,
    )

    result = service.generate_answer(
        query="What is the finance policy?",
        context=create_context(),
    )

    assert result.answer == "Generated answer."


def test_generation_service_rejects_empty_query():
    provider = FakeProvider()

    service = GenerationService(
        provider=provider,
    )

    with pytest.raises(
        ValueError,
        match="Query cannot be empty",
    ):
        service.generate_answer(
            query="   ",
            context=create_context(),
        )

    assert provider.calls == []


def test_generation_service_handles_empty_context():
    provider = FakeProvider()

    service = GenerationService(
        provider=provider,
    )

    context = ContextResult(
        text="",
        sources=[],
    )

    result = service.generate_answer(
        query="What is the finance policy?",
        context=context,
    )

    assert result.answer == (
        "I couldn't find any relevant "
        "information in the documents "
        "you are authorized to access."
    )

    # The LLM must not be called when there is
    # no authorized context.
    assert provider.calls == []


def test_generation_service_rejects_empty_llm_answer():
    provider = FakeProvider(
        answer="   "
    )

    service = GenerationService(
        provider=provider,
    )

    with pytest.raises(
        ValueError,
        match="LLM returned an empty answer",
    ):
        service.generate_answer(
            query="What is the finance policy?",
            context=create_context(),
        )

    assert len(provider.calls) == 1