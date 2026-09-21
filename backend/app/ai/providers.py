"""AI provider abstraction (spec §39).

Current active provider: the deterministic guidance engine (no external calls).
Any LLM integration (OpenAI, Azure, local models, ...) REQUIRES INTEGRATION:
implement `AIProvider`, wire it in `get_ai_provider`, add credentials via env
only, and extend the tests. It must always run behind the safety pipeline.
"""

from typing import Protocol

from app.core.config import settings


class AIProvider(Protocol):
    def complete(self, prompt: str, context: str) -> str:
        """Return assistant text for the given user message."""
        ...


class GuidanceEngineProvider:
    """Deterministic, offline guidance renderer — the active default provider."""

    def complete(self, prompt: str, context: str) -> str:
        # The pipeline renders guidance directly; this provider exists to keep
        # the abstraction explicit and honest about what is actually running.
        return ""


def get_ai_provider() -> AIProvider:
    if settings.ai_provider == "none":
        return GuidanceEngineProvider()
    # Any other provider value REQUIRES INTEGRATION before it functions.
    raise NotImplementedError(
        f"AI provider '{settings.ai_provider}' is not integrated. "
        "Set MEDISAVE_AI_PROVIDER=none or implement the integration."
    )
