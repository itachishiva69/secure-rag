from dataclasses import dataclass
from typing import Protocol

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


class GenerationService:
    def __init__(
        self,
        provider: LLMProvider | None = None,
    ):
        self.provider = provider

    def generate_answer(
        self,
        *,
        query: str,
        context: ContextResult,
    ) -> GenerationResult:
        if not query.strip():
            raise ValueError(
                "Query cannot be empty"
            )

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

        if not answer or not answer.strip():
            raise ValueError(
                "LLM returned an empty answer"
            )

        return GenerationResult(
            answer=answer.strip()
        )