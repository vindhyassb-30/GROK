"""Pluggable LLM interface.

The organization logic never calls a provider directly; it depends on the
``LLM`` protocol. A deterministic ``MockLLM`` lets the whole desk run offline
and reproducibly. A real provider (xAI Grok, OpenAI, ...) can be dropped in by
implementing the same ``complete`` method.
"""

from __future__ import annotations

import hashlib
from typing import List, Optional, Protocol, runtime_checkable


@runtime_checkable
class LLM(Protocol):
    """Minimal LLM contract used across the desk."""

    def complete(self, system: str, prompt: str) -> str:
        """Return a model completion for the given system + user prompt."""
        ...


class MockLLM:
    """Deterministic, offline stand-in for a real model.

    It never invents figures: it only phrases/summarises the structured inputs it
    is handed. Determinism comes from hashing the prompt so repeated runs match,
    which is what the acceptance tests rely on.
    """

    def __init__(self, canned: Optional[dict] = None):
        self._canned = canned or {}
        self.calls: List[tuple] = []

    def complete(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        for key, response in self._canned.items():
            if key in prompt:
                return response
        digest = hashlib.sha256((system + "\x00" + prompt).encode()).hexdigest()[:8]
        # Phrasing only -- no fabricated data. Echoes a bounded view of the prompt.
        head = prompt.strip().splitlines()[0] if prompt.strip() else "(empty)"
        return f"[mock:{digest}] {head[:160]}"
