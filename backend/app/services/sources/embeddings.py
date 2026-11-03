"""Text embeddings for semantic search over the source library."""

from collections.abc import Callable
from typing import Protocol

import numpy as np

from ...config import Settings

BATCH_SIZE = 64
MAX_INPUT_CHARS = 8000  # well under the model's 8k-token input limit


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, d) float32 array of L2-normalised vectors."""
        ...


def normalise(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def to_blob(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


class OpenAIEmbedder:
    """Embeds text with the OpenAI embeddings API (e.g. text-embedding-3-small)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.openai_embedding_model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.settings.openai_api_key.get_secret_value(),
                timeout=self.settings.openai_timeout_seconds,
                max_retries=self.settings.openai_max_retries,
            )
        return self._client

    def embed(self, texts: list[str]) -> np.ndarray:
        from ..generation import _translate_llm_error

        vectors: list[list[float]] = []
        client = self._get_client()
        for start in range(0, len(texts), BATCH_SIZE):
            batch = [(t or " ")[:MAX_INPUT_CHARS] for t in texts[start : start + BATCH_SIZE]]
            try:
                response = client.embeddings.create(model=self.model, input=batch)
            except Exception as exc:
                raise _translate_llm_error(exc) from exc
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors.extend(item.embedding for item in ordered)
        return normalise(np.array(vectors, dtype=np.float32))


def default_embedder_factory(settings: Settings) -> Callable[[], Embedder | None]:
    """Embeddings are optional: without an API key the library falls back to keyword search."""

    def factory() -> Embedder | None:
        return OpenAIEmbedder(settings) if settings.has_openai_key else None

    return factory
