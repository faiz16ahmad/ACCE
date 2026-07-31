from ..base import LLMProvider


class StubLLMProvider(LLMProvider):
    """Echoes a placeholder string so interface wiring is exercised end-to-end."""

    name = "stub"

    def __init__(self, **_: object) -> None:
        # Accepts the LLM config kwargs so the factory can pass the same
        # arguments to every provider.
        pass

    def complete(self, prompt: str, *, system: str | None = None, **kwargs: object) -> str:
        return f"[stub-llm] response for: {prompt[:200]}"
