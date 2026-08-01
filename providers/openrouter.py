"""OpenRouter LLM provider.

OpenRouter provides access to many models via an OpenAI-compatible API.
Selected via `ACCE_LLM__PROVIDER=openrouter` in `.env`.

Uses stdlib urllib — no extra dependencies required.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

from .base import LLMProvider, ProviderError

log = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def __init__(
        self,
        model: str = "meta-llama/llama-3-8b-instruct:free",
        api_key: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 4096,
        base_url: str | None = None,
        **_: object,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.base_url = base_url or _OPENROUTER_URL

    def complete(self, prompt: str, *, system: str | None = None, **kwargs: object) -> str:
        if not self.api_key:
            raise ProviderError(
                "OpenRouterProvider requires an API key — set ACCE_LLM__API_KEY."
            )

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_output_tokens,
        }).encode("utf-8")

        req = urllib.request.Request(
            self.base_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://github.com/acce",
                "X-Title": "ACCE",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read(2_000_000)
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")[:500]
            raise ProviderError(
                f"OpenRouter HTTP {exc.code}: {error_body}"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ProviderError(f"OpenRouter connection failed: {exc}") from exc

        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise ProviderError(f"OpenRouter returned invalid JSON: {exc}") from exc

        # OpenAI-compatible response shape
        choices = data.get("choices") or []
        if not choices:
            error_msg = data.get("error", {}).get("message", "") if isinstance(data.get("error"), dict) else str(data.get("error", ""))
            raise ProviderError(f"OpenRouter returned no choices: {error_msg or data}")

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise ProviderError(f"OpenRouter returned empty content: {data}")

        return content
