"""
Embedding helpers for semantic retrieval over canonical document chunks.

This module owns the first embedding-specific logic for the repository:

- read configured OpenAI embedding settings
- call the embeddings API for one or more chunk texts
- return vectors in a shape that can be written to pgvector

Chunking stays separate because chunking is deterministic local preprocessing,
while this module is the provider-backed semantic encoding layer.
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from backend.settings import get_settings


def get_openai_embedding_client(api_key: str | None = None) -> OpenAI:
    """
    Return an OpenAI client for embedding requests.
    """

    settings = get_settings()
    resolved_api_key = api_key or settings.openai_api_key
    if not isinstance(resolved_api_key, str) or resolved_api_key.strip() == "":
        raise RuntimeError(
            "OpenAI API key is required before generating document embeddings."
        )
    return OpenAI(api_key=resolved_api_key)


def embed_texts(
    texts: list[str],
    *,
    model: str | None = None,
    dimensions: int | None = None,
    api_key: str | None = None,
) -> list[list[float]]:
    """
    Return embeddings for a batch of chunk texts.
    """

    normalized_texts = [text.strip() for text in texts if text.strip() != ""]
    if not normalized_texts:
        return []

    settings = get_settings()
    resolved_model = model or settings.openai_embedding_model
    resolved_dimensions = (
        dimensions
        if dimensions is not None
        else settings.openai_embedding_dimensions
    )

    client = get_openai_embedding_client(api_key=api_key)
    response = client.embeddings.create(
        model=resolved_model,
        input=normalized_texts,
        dimensions=resolved_dimensions,
    )
    return [item.embedding for item in response.data]


def vector_to_pgvector_literal(values: list[float]) -> str:
    """
    Return a pgvector-compatible literal string for one embedding.
    """

    if not values:
        raise ValueError("Embedding vector must not be empty.")
    return "[" + ",".join(f"{value:.12f}".rstrip("0").rstrip(".") for value in values) + "]"


def summarize_embedding_configuration() -> dict[str, Any]:
    """
    Return the active embedding configuration for operator visibility.
    """

    settings = get_settings()
    return {
        "provider": "openai",
        "model": settings.openai_embedding_model,
        "dimensions": settings.openai_embedding_dimensions,
    }


__all__ = [
    "embed_texts",
    "get_openai_embedding_client",
    "summarize_embedding_configuration",
    "vector_to_pgvector_literal",
]
