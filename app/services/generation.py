from dataclasses import dataclass
from typing import Iterator, Protocol, Sequence

from app.services.context import ContextResult


@dataclass(frozen=True)
class GenerationResult:
    answer: str


class LLMProvider(Protocol):
    def generate(
        self,
        *,
        query: str,
        context: ContextResult,
    ) -> str:
        ...

    def generate_conversational(
        self,
        *,
        query: str,
        context: ContextResult,
        previous_user_messages: Sequence[str],
    ) -> str:
        ...

    def stream(
        self,
        *,
        query: str,
        context: ContextResult,
    ) -> Iterator[str]:
        ...

    def stream_conversational(
        self,
        *,
        query: str,
        context: ContextResult,
        previous_user_messages: Sequence[str],
    ) -> Iterator[str]:
        ...


class GenerationService:
    def __init__(
        self,
        provider: LLMProvider | None = None,
    ):
        self.provider = provider

    def _validate_query(
        self,
        query: str,
    ) -> None:
        if not query.strip():
            raise ValueError(
                "Query cannot be empty"
            )

    def _validate_answer(
        self,
        answer: str,
    ) -> GenerationResult:
        if not answer or not answer.strip():
            raise ValueError(
                "LLM returned an empty answer"
            )

        return GenerationResult(
            answer=answer.strip()
        )

    def generate_answer(
        self,
        *,
        query: str,
        context: ContextResult,
    ) -> GenerationResult:
        self._validate_query(query)

        if not context.text.strip():
            return GenerationResult(
                answer=(
                    "I couldn't find any relevant "
                    "information in the documents "
                    "you are authorized to access."
                )
            )

        if self.provider is None:
            raise RuntimeError(
                "LLM provider is required when "
                "context is available"
            )

        answer = self.provider.generate(
            query=query,
            context=context,
        )

        return self._validate_answer(answer)

    def generate_conversational_answer(
        self,
        *,
        query: str,
        context: ContextResult,
        previous_user_messages: Sequence[str],
    ) -> GenerationResult:
        self._validate_query(query)

        if not context.text.strip():
            return GenerationResult(
                answer=(
                    "I couldn't find any relevant "
                    "information in the documents "
                    "you are authorized to access."
                )
            )

        if self.provider is None:
            raise RuntimeError(
                "LLM provider is required when "
                "context is available"
            )

        normalized_history = [
            message.strip()
            for message in previous_user_messages
            if message and message.strip()
        ]

        answer = self.provider.generate_conversational(
            query=query,
            context=context,
            previous_user_messages=normalized_history,
        )

        return self._validate_answer(answer)

    def stream_answer(
        self,
        *,
        query: str,
        context: ContextResult,
    ) -> Iterator[str]:
        self._validate_query(query)

        if not context.text.strip():
            yield (
                "I couldn't find any relevant "
                "information in the documents "
                "you are authorized to access."
            )
            return

        if self.provider is None:
            raise RuntimeError(
                "LLM provider is required when "
                "context is available"
            )

        yield from self.provider.stream(
            query=query,
            context=context,
        )

    def stream_conversational_answer(
        self,
        *,
        query: str,
        context: ContextResult,
        previous_user_messages: Sequence[str],
    ) -> Iterator[str]:
        self._validate_query(query)

        if not context.text.strip():
            yield (
                "I couldn't find any relevant "
                "information in the documents "
                "you are authorized to access."
            )
            return

        if self.provider is None:
            raise RuntimeError(
                "LLM provider is required when "
                "context is available"
            )

        normalized_history = [
            message.strip()
            for message in previous_user_messages
            if message and message.strip()
        ]

        yield from self.provider.stream_conversational(
            query=query,
            context=context,
            previous_user_messages=normalized_history,
        )
