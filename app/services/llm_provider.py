from collections.abc import Iterator, Sequence
import re

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from app.core.config import get_settings
from app.services.context import ContextResult


class LLMProviderError(Exception):
    """Raised when the configured LLM provider cannot generate an answer."""


_SOURCE_REFERENCE_RE = re.compile(
    r"(?:【[^【】\[\]\r\n]{1,300},\s*chunk\s*\d+\s*】|"
    r"\[[^【】\[\]\r\n]{1,300},\s*chunk\s*\d+\s*\])",
    re.IGNORECASE,
)


def clean_generated_answer(answer: str) -> str:
    """Remove internal source metadata that must never be shown as answer text."""
    cleaned = _SOURCE_REFERENCE_RE.sub("", answer)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


def clean_stream_chunks(chunks: Iterator[str]) -> Iterator[str]:
    """Sanitize a provider token stream without leaking source metadata."""
    pending = ""

    for fragment in chunks:
        if not fragment:
            continue

        pending += fragment

        while True:
            match = _SOURCE_REFERENCE_RE.search(pending)
            if match is None:
                break

            before = pending[:match.start()]
            after = pending[match.end():]

            if before:
                yield before

            pending = after

        opener_positions = [
            index
            for index in (pending.rfind("["), pending.rfind("【"))
            if index >= 0
        ]

        if not opener_positions:
            if pending:
                yield pending
                pending = ""
            continue

        opener = max(opener_positions)
        candidate = pending[opener:]

        if "\n" in candidate or len(candidate) > 320:
            yield pending
            pending = ""
            continue

        closing = "]" if candidate.startswith("[") else "】"

        if closing in candidate:
            yield pending
            pending = ""
            continue

        prefix = pending[:opener]

        if prefix:
            yield prefix

        pending = candidate

    if pending:
        yield clean_generated_answer(pending)


SYSTEM_PROMPT = (
    "You answer questions using only the supplied document context.\n\n"
    "Rules:\n"
    "1. Use only the provided context for factual answers.\n"
    "2. Do not invent facts.\n"
    "3. If the context does not contain the answer, say that the information "
    "was not found in the available documents.\n"
    "4. Do not discuss or infer user permissions.\n"
    "5. Keep the answer concise and direct.\n"
    "6. Previous user questions are conversation context only. They are not "
    "evidence and must never be treated as document facts.\n"
    "7. Do not use previous assistant answers as factual evidence.\n"
    "8. Never include document filenames, document IDs, chunk numbers, or "
    "internal source references in the answer. Source metadata is shown "
    "separately by the application.\n"
    "9. Do not emit citation-like brackets such as [filename, chunk 3] or "
    "【filename, chunk 3】. Answer only the user's question."
)


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float = 30.0,
    ):
        self.model = model

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=2,
        )

    @staticmethod
    def _extract_content(
        chunk,
    ) -> str | None:
        if not chunk.choices:
            return None

        delta = chunk.choices[0].delta
        content = delta.content

        if content is None:
            return None

        return content

    def _request(
        self,
        *,
        messages: list[dict[str, str]],
    ) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=0.1,
                messages=messages,
            )

        except APITimeoutError as exc:
            raise LLMProviderError(
                "LLM provider request timed out"
            ) from exc

        except APIConnectionError as exc:
            raise LLMProviderError(
                "LLM provider connection failed"
            ) from exc

        except RateLimitError as exc:
            raise LLMProviderError(
                "LLM provider rate limit exceeded"
            ) from exc

        except InternalServerError as exc:
            raise LLMProviderError(
                "LLM provider server error"
            ) from exc

        except APIError as exc:
            raise LLMProviderError(
                "LLM provider request failed"
            ) from exc

        if not response.choices:
            raise LLMProviderError(
                "LLM provider returned no choices"
            )

        content = response.choices[0].message.content

        if content is None:
            raise LLMProviderError(
                "LLM provider returned no content"
            )

        content = clean_generated_answer(content)

        if not content:
            raise LLMProviderError(
                "LLM provider returned empty content"
            )

        return content

    def _stream_request(
        self,
        *,
        messages: list[dict[str, str]],
    ) -> Iterator[str]:
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                temperature=0.1,
                messages=messages,
                stream=True,
            )

            emitted_any = False

            def raw_content_stream() -> Iterator[str]:
                nonlocal emitted_any

                for chunk in stream:
                    content = self._extract_content(chunk)

                    if content is None:
                        continue

                    emitted_any = True
                    yield content

            for safe_fragment in clean_stream_chunks(raw_content_stream()):
                if safe_fragment:
                    yield safe_fragment

            if not emitted_any:
                raise LLMProviderError(
                    "LLM provider returned no content"
                )

        except APITimeoutError as exc:
            raise LLMProviderError(
                "LLM provider request timed out"
            ) from exc

        except APIConnectionError as exc:
            raise LLMProviderError(
                "LLM provider connection failed"
            ) from exc

        except RateLimitError as exc:
            raise LLMProviderError(
                "LLM provider rate limit exceeded"
            ) from exc

        except InternalServerError as exc:
            raise LLMProviderError(
                "LLM provider server error"
            ) from exc

        except APIError as exc:
            raise LLMProviderError(
                "LLM provider request failed"
            ) from exc

    def generate(
        self,
        *,
        query: str,
        context: ContextResult,
    ) -> str:
        return self._request(
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        f"Document context:\n\n"
                        f"{context.text}\n\n"
                        f"Question:\n{query}"
                    ),
                },
            ]
        )

    def generate_conversational(
        self,
        *,
        query: str,
        context: ContextResult,
        previous_user_messages: Sequence[str],
    ) -> str:
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        for previous_message in previous_user_messages:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Previous user question:\n"
                        f"{previous_message}"
                    ),
                }
            )

        messages.append(
            {
                "role": "user",
                "content": (
                    f"Document context:\n\n"
                    f"{context.text}\n\n"
                    f"Current question:\n{query}"
                ),
            }
        )

        return self._request(
            messages=messages
        )

    def stream(
        self,
        *,
        query: str,
        context: ContextResult,
    ) -> Iterator[str]:
        yield from self._stream_request(
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        f"Document context:\n\n"
                        f"{context.text}\n\n"
                        f"Question:\n{query}"
                    ),
                },
            ]
        )

    def stream_conversational(
        self,
        *,
        query: str,
        context: ContextResult,
        previous_user_messages: Sequence[str],
    ) -> Iterator[str]:
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        for previous_message in previous_user_messages:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Previous user question:\n"
                        f"{previous_message}"
                    ),
                }
            )

        messages.append(
            {
                "role": "user",
                "content": (
                    f"Document context:\n\n"
                    f"{context.text}\n\n"
                    f"Current question:\n{query}"
                ),
            }
        )

        yield from self._stream_request(
            messages=messages
        )


def get_llm_provider() -> OpenAICompatibleProvider:
    settings = get_settings()

    if not settings.llm_api_key:
        raise RuntimeError(
            "LLM_API_KEY is not configured"
        )

    return OpenAICompatibleProvider(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
    )
