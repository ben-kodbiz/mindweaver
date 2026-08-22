"""LLM provider interface.

All chat/generation code talks to this interface so no business logic
depends on a specific runtime (Ollama, llama.cpp, LM Studio, remote APIs).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMProvider(ABC):
    name: str
    model_name: str

    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        """Return the assistant's text completion for ``messages``."""
