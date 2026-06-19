import backend.services.document_embeddings as document_embeddings
from backend.services.document_embeddings import (
    get_openai_embedding_client,
    vector_to_pgvector_literal,
)


def test_vector_to_pgvector_literal_returns_pgvector_shape() -> None:
    result = vector_to_pgvector_literal([0.1, 0.25, -0.5])

    assert result.startswith("[")
    assert result.endswith("]")
    assert result == "[0.1,0.25,-0.5]"


def test_vector_to_pgvector_literal_rejects_empty_vectors() -> None:
    try:
        vector_to_pgvector_literal([])
    except ValueError as error:
        assert "must not be empty" in str(error)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for empty vector.")


def test_get_openai_embedding_client_strips_surrounding_key_whitespace(
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    class FakeSettings:
        openai_api_key = "  sk-test-value\r\n"

    class FakeOpenAI:
        def __init__(self, *, api_key: str) -> None:
            captured["api_key"] = api_key

    monkeypatch.setattr(document_embeddings, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(document_embeddings, "OpenAI", FakeOpenAI)

    client = get_openai_embedding_client()

    assert isinstance(client, FakeOpenAI)
    assert captured["api_key"] == "sk-test-value"
