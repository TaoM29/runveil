import httpx
import pytest
from agentrail_api.main import create_app


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
