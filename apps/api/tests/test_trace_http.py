"""Trace capability is fail-closed, separate from approval, and non-reflecting."""

import secrets
from uuid import uuid4

import httpx
import pytest
from runveil_api.approvals import token_digest
from runveil_api.main import create_app


@pytest.mark.asyncio
async def test_trace_authentication_and_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("RUNVEIL_TRACE_TOKEN", raising=False)
    token = secrets.token_urlsafe(32)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            path = f"/runs/{uuid4()}/trace"
            assert (await client.get(path)).json() == {"error": "traces_disabled"}
            app.state.trace_token_digest = token_digest(token)
            assert (await client.get("/runs/private/trace?private=secret")).status_code == 401
            client.headers["Authorization"] = "Bearer " + token
            app.state.approval_token_digest = token_digest(secrets.token_urlsafe(32))
            assert (await client.get("/approvals/private")).status_code == 401
            assert (await client.get(path)).status_code == 503
            app.state.database = object()  # Invalid queries cannot reach storage.
            for query in (
                "limit=0",
                "limit=101",
                "after_sequence=-1",
                "limit=1&limit=2",
                "after_sequence=1",
                "expected_sequence=99999999999",
                "private=secret",
            ):
                response = await client.get(path + "?" + query)
                assert response.status_code == 422
                assert response.json() == {"error": "invalid_request"}
                assert response.headers["cache-control"] == "no-store"
            assert (
                await client.get(path, headers=[("Authorization", "Bearer " + token)] * 2)
            ).status_code == 401
    assert app.state.trace_token_digest is None
    monkeypatch.setenv("RUNVEIL_TRACE_TOKEN", token)
    async with app.router.lifespan_context(app):
        assert app.state.trace_token_digest == token_digest(token)
