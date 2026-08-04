"""Run a content-free live smoke measurement against configured model providers."""

from __future__ import annotations

import json

from backend.llm.models import DEFAULT_REASONING_MODEL_PROFILE
from backend.llm.providers import build_langchain_chat_model
from backend.llm.telemetry import invoke_with_model_telemetry
from backend.services.document_embeddings import embed_texts_with_telemetry


def main() -> None:
    chat_model = build_langchain_chat_model(profile=DEFAULT_REASONING_MODEL_PROFILE)
    _, chat_telemetry = invoke_with_model_telemetry(
        chat_model,
        "Reply with the single word OK.",
        workflow="model_latency_smoke_chat",
        provider=DEFAULT_REASONING_MODEL_PROFILE.provider.value,
        model=DEFAULT_REASONING_MODEL_PROFILE.model_name,
    )
    vectors, embedding_telemetry = embed_texts_with_telemetry(
        ["recruitment intelligence latency probe"],
        workflow="model_latency_smoke_embedding",
    )

    print(
        json.dumps(
            {
                "purpose": "content-free provider latency smoke measurement",
                "representative_benchmark": False,
                "chat": chat_telemetry,
                "embedding": embedding_telemetry,
                "embedding_dimensions": len(vectors[0]) if vectors else 0,
                "notes": [
                    "Active production calls are non-streaming, so TTFT and ITL are null.",
                    "Queue, prefill and decode timings remain null unless the provider returns them.",
                    "No prompt, response, CV or candidate content is written to telemetry.",
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
