from collections.abc import Iterator, Sequence

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
    "7. Do not use previous assistant answers as factual evidence."
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

        content = content.strip()

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

            for chunk in stream:
                content = self._extract_content(chunk)

                if content is None:
                    continue

                emitted_any = True
                yield content

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
