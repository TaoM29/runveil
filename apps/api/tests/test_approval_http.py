"""Fail-closed authentication and bounded, non-reflecting HTTP input."""

import secrets
from uuid import uuid4

import httpx
import pytest
from runveil_api.approvals import token_digest
from runveil_api.main import create_app


@pytest.mark.asyncio
async def test_authentication_precedes_input_and_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("RUNVEIL_APPROVAL_TOKEN", raising=False)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            path = f"/approvals/{uuid4()}/decision"
            assert (await client.post(path)).json() == {"error": "approvals_disabled"}
            token = secrets.token_urlsafe(32)
            app.state.approval_token_digest = token_digest(token)
            for headers in ({}, {"Authorization": "Bearer " + secrets.token_urlsafe(32)}):
                response = await client.post(path, headers=headers, content="private invalid body")
                assert response.status_code == 401
                assert response.json() == {"error": "unauthorized"}
                assert response.headers["cache-control"] == "no-store"
            client.headers["Authorization"] = "Bearer " + token
            assert (await client.post("/approvals/not-a-uuid/decision")).status_code == 422
            assert (await client.post(path)).status_code == 503
            # A sentinel suffices: malformed requests must never reach the database.
            app.state.database = object()
            assert (await client.post(path, content="private")).status_code == 415
            for body, status in ((b"x" * 2049, 413), (b'{"private":true}', 422)):
                response = await client.post(
                    path, content=body, headers={"Content-Type": "application/json"}
                )
                assert response.status_code == status
                assert "private" not in response.text
            response = await client.get(
                path.removesuffix("/decision"),
                headers=[("Authorization", "Bearer " + token)] * 2,
            )
            assert response.status_code == 401
    assert app.state.approval_token_digest is None
    assert token_digest("short") is None

    monkeypatch.setenv("RUNVEIL_APPROVAL_TOKEN", token)
    async with app.router.lifespan_context(app):
        assert app.state.approval_token_digest == token_digest(token)
    monkeypatch.setenv("RUNVEIL_APPROVAL_TOKEN", "invalid")
    async with app.router.lifespan_context(app):
        assert app.state.approval_token_digest is None
