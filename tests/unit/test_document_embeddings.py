from backend.services.document_embeddings import vector_to_pgvector_literal


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
