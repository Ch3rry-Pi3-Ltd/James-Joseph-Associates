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

from backend.llm.telemetry import invoke_provider_with_telemetry
from backend.settings import get_settings


def get_openai_embedding_client(api_key: str | None = None) -> OpenAI:
    """
    Return an OpenAI client for embedding requests.
    """

    settings = get_settings()
    resolved_api_key = _normalize_optional_secret(api_key or settings.openai_api_key)
    if not isinstance(resolved_api_key, str) or resolved_api_key == "":
        raise RuntimeError(
            "OpenAI API key is required before generating document embeddings."
        )
    if settings.openai_embedding_timeout_seconds <= 0:
        raise RuntimeError("OpenAI embedding timeout must be greater than zero.")
    if settings.openai_embedding_max_retries < 0:
        raise RuntimeError("OpenAI embedding retries must not be negative.")
    return OpenAI(
        api_key=resolved_api_key,
        timeout=settings.openai_embedding_timeout_seconds,
        max_retries=settings.openai_embedding_max_retries,
    )


def embed_texts(
    texts: list[str],
    *,
    model: str | None = None,
    dimensions: int | None = None,
    api_key: str | None = None,
    workflow: str | None = None,
    run_id: str | None = None,
) -> list[list[float]]:
    """
    Return embeddings for a batch of chunk texts.
    """

    vectors, _ = embed_texts_with_telemetry(
        texts,
        model=model,
        dimensions=dimensions,
        api_key=api_key,
        workflow=workflow,
        run_id=run_id,
    )
    return vectors


def embed_texts_with_telemetry(
    texts: list[str],
    *,
    model: str | None = None,
    dimensions: int | None = None,
    api_key: str | None = None,
    workflow: str | None = None,
    run_id: str | None = None,
) -> tuple[list[list[float]], dict[str, Any] | None]:
    """Return embeddings plus content-free provider latency telemetry."""

    normalized_texts = [text.strip() for text in texts if text.strip() != ""]
    if not normalized_texts:
        return [], None

    settings = get_settings()
    resolved_model = model or settings.openai_embedding_model
    resolved_dimensions = (
        dimensions if dimensions is not None else settings.openai_embedding_dimensions
    )

    client = get_openai_embedding_client(api_key=api_key)
    resolved_workflow = workflow or (
        "candidate_query_embedding"
        if len(normalized_texts) == 1
        else "document_chunk_embedding_batch"
    )
    response, telemetry = invoke_provider_with_telemetry(
        lambda: client.embeddings.create(
            model=resolved_model,
            input=normalized_texts,
            dimensions=resolved_dimensions,
        ),
        workflow=resolved_workflow,
        provider="openai",
        model=resolved_model,
        run_id=run_id,
        usage_extractor=_extract_embedding_usage,
    )
    return [item.embedding for item in response.data], telemetry


def vector_to_pgvector_literal(values: list[float]) -> str:
    """
    Return a pgvector-compatible literal string for one embedding.
    """

    if not values:
        raise ValueError("Embedding vector must not be empty.")
    return (
        "["
        + ",".join(f"{value:.12f}".rstrip("0").rstrip(".") for value in values)
        + "]"
    )


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


def _normalize_optional_secret(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _extract_embedding_usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    result: dict[str, int] = {}
    if isinstance(prompt_tokens, int):
        result["input_tokens"] = prompt_tokens
    if isinstance(total_tokens, int):
        result["total_tokens"] = total_tokens
    return result


__all__ = [
    "embed_texts",
    "embed_texts_with_telemetry",
    "get_openai_embedding_client",
    "summarize_embedding_configuration",
    "vector_to_pgvector_literal",
]
