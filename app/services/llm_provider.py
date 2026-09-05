from openai import OpenAI

from app.core.config import get_settings
from app.services.context import ContextResult


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
    ):
        self.model = model

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    def generate(
        self,
        *,
        query: str,
        context: ContextResult,
    ) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You answer questions using only "
                        "the supplied document context.\n\n"
                        "Rules:\n"
                        "1. Use only the provided context.\n"
                        "2. Do not invent facts.\n"
                        "3. If the context does not contain "
                        "the answer, say that the information "
                        "was not found in the available "
                        "documents.\n"
                        "4. Do not discuss or infer user "
                        "permissions.\n"
                        "5. Keep the answer concise and "
                        "direct."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Document context:\n\n"
                        f"{context.text}\n\n"
                        f"Question:\n{query}"
                    ),
                },
            ],
        )

        content = response.choices[0].message.content

        if content is None:
            return ""

        return content
        

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
    )