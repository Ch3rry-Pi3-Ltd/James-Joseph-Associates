from backend.services.mcp_operations import (
    build_mcp_argument_metadata,
    fingerprint_mcp_principal,
)


def test_mcp_principal_fingerprint_is_stable_and_one_way() -> None:
    token = "sensitive-test-token"

    first = fingerprint_mcp_principal(token)
    second = fingerprint_mcp_principal(token)

    assert first == second
    assert first != token
    assert len(first) == 64
    assert token not in first


def test_mcp_argument_metadata_excludes_argument_values() -> None:
    metadata = build_mcp_argument_metadata(
        {
            "role_brief": "Sensitive role and candidate context",
            "search_limit": 10,
        }
    )

    assert metadata["argument_fields"] == ["role_brief", "search_limit"]
    assert metadata["serialized_character_count"] > 0
    assert "Sensitive role and candidate context" not in str(metadata)
