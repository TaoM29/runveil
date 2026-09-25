import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from runveil_api.main import create_app


@pytest.mark.asyncio
async def test_liveness_contract() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok", "service": "api"}


@pytest.mark.asyncio
async def test_unknown_route_is_not_a_successful_health_check() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/runs")
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [None, "postgresql+psycopg://test:do-not-leak@127.0.0.1:1/missing"])
async def test_readiness_failure_does_not_break_liveness(
    url: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    if url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", url)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            readiness = await client.get("/ready")
            health = await client.get("/health")
    assert readiness.status_code == 503
    assert readiness.json() == {"status": "unavailable", "database": "unavailable"}
    assert "do-not-leak" not in readiness.text
    assert health.status_code == 200


@pytest.mark.asyncio
async def test_readiness_times_out_a_stalled_query() -> None:
    async def stall(*args: object) -> None:
        await asyncio.sleep(10)

    connection = AsyncMock()
    connection.execute.side_effect = stall
    engine = MagicMock()
    engine.connect.return_value.__aenter__ = AsyncMock(return_value=connection)
    engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)
    app = create_app()
    app.state.database = engine
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await asyncio.wait_for(client.get("/ready"), timeout=4)
    assert response.status_code == 503
    engine.connect.return_value.__aexit__.assert_awaited_once()
