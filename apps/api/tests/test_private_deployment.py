import asyncio

import httpx
import pytest
from runveil_api.private import app
from runveil_worker.service import supervise


@pytest.mark.asyncio
async def test_private_surface_has_no_mutation_or_docs_routes() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://private"
    ) as client:
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/runs/invalid/trace")).status_code == 503
        assert (await client.post("/approvals/invalid/decision", json={})).status_code == 404
        assert (await client.get("/openapi.json")).status_code == 404


@pytest.mark.asyncio
async def test_supervisor_backs_off_redacts_errors_and_stops(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stop = asyncio.Event()
    calls = 0
    delays: list[float | None] = []

    async def operation() -> object:
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise RuntimeError("private payload must not be logged")
        stop.set()
        return None

    original = asyncio.wait_for

    async def wait_for(future: object, timeout: float | None) -> object:
        delays.append(timeout)
        # Preserve cancellation/await semantics, but avoid real retry delays in this test.
        assert asyncio.iscoroutine(future)
        return await original(future, timeout=0 if not stop.is_set() else 1)

    monkeypatch.setattr(asyncio, "wait_for", wait_for)
    await supervise(operation, stop)
    assert calls == 3 and delays == [2, 4, 1]
    assert capsys.readouterr().out == "broker_iteration_failed\nbroker_iteration_failed\n"
