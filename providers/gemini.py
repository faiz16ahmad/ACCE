"""Google Gemini LLM provider.

First real LLM integration (free tier, good for development). Selected via
`ACCE_LLM__PROVIDER=gemini` in `.env`; the stub remains the default. Adding
OpenAI, Anthropic, GLM, DeepSeek, or OpenRouter later means implementing the
same `LLMProvider` interface and registering it — no module changes.

The `google-genai` SDK is an optional dependency; it is imported lazily so
the rest of ACCE works without it.
"""

from __future__ import annotations

import logging
import os

from .base import LLMProvider

log = logging.getLogger(__name__)

INSTALL_HINT = "Install the extra: uv sync --extra gemini  (or: pip install -e .[gemini])"


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        api_key: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 4096,
        base_url: str | None = None,
        **_: object,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.base_url = base_url
        self._client = None

    def _client_factory(self):
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - depends on the extra
            raise RuntimeError(
                "GeminiProvider requires the 'google-genai' package. " + INSTALL_HINT
            ) from exc

        if not self.api_key:
            raise RuntimeError(
                "GeminiProvider requires an API key — set ACCE_LLM__API_KEY "
                "or the GEMINI_API_KEY environment variable."
            )
        if self.base_url:
            return genai.Client(api_key=self.api_key, http_options={"base_url": self.base_url})
        return genai.Client(api_key=self.api_key)

    @property
    def client(self):
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    def complete(self, prompt: str, *, system: str | None = None, **kwargs: object) -> str:
        genai = self.client
        config = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }
        if system:
            config["system_instruction"] = system

        response = genai.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return response.text or ""
