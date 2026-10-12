import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.core.read_budget import remaining_read_seconds
from backend.services import mcp_server as subject


def test_search_cache_is_scoped_to_principal_and_arguments(monkeypatch):
    subject._search_cache.clear()
    monkeypatch.setattr(subject, "stable_read_cache_ttl_seconds", lambda: 15)
    monkeypatch.setattr(subject, "_audit_tool_event", AsyncMock())
    monkeypatch.setattr(subject, "get_settings", lambda: SimpleNamespace(mcp_tool_timeout_seconds=30))
    calls = []

    def load():
        assert 0 < remaining_read_seconds() <= 28
        calls.append(1)
        return {"search_results": [{"candidate_id": "synthetic"}]}

    async def invoke(principal, query):
        ctx = SimpleNamespace(
            request_context=SimpleNamespace(request=SimpleNamespace(
                state=SimpleNamespace(mcp_principal_hash=principal))),
            request_id="test", session=SimpleNamespace(),
        )
        return await subject._execute_read_tool(
            ctx=ctx, tool_name="search_candidates_for_role",
            arguments={"role_brief": query}, operation=load,
        )

    async def exercise():
        first = await invoke("principal-a", "SFTR")
        first["search_results"].clear()
        assert len((await invoke("principal-a", "SFTR"))["search_results"]) == 1
        await invoke("principal-b", "SFTR")
        await invoke("principal-a", "Python")

    try:
        asyncio.run(exercise())
        assert len(calls) == 3
    finally:
        subject._search_cache.clear()
