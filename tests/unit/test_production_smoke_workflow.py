from pathlib import Path


WORKFLOW_PATH = Path(".github/workflows/production-smoke.yaml")


def test_production_smoke_workflow_is_scheduled_and_manually_runnable() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "schedule:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow
    assert "github.ref == 'refs/heads/main'" in workflow


def test_production_smoke_workflow_keeps_credentials_scoped_and_enforces_budgets() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "${{ secrets.MCP_API_TOKEN }}" in workflow
    assert "MCP_SMOKE_ENDPOINT: https://james-joseph-associates.vercel.app/mcp" in workflow
    assert "--max-candidate-search-ms 20000" in workflow
    assert "--max-exhaustive-search-ms 10000" in workflow
