"""HTTP decisions reuse the durable approval boundary and never execute a patch."""

import asyncio
import secrets
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import httpx
import pytest
from runveil_api import approvals as api
from runveil_api.main import create_app
from runveil_core.approvals import ApprovalRequest
from runveil_core.tools import ToolError
from runveil_persistence.approvals import ApprovalRepository
from runveil_persistence.history import HistoryRepository
from runveil_persistence.models import JobRow
from runveil_tools.repository import RepositoryAccess
from runveil_worker.patch_worker import submit_patch, work_patch_once
from runveil_worker.review_worker import submit_review, work_review_once
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from test_approvals import PROPOSAL, review_run
from test_worker import expire

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize(
    "profile", ["patch-review-v1", "repository-review-v1", "repository-patch-v1"]
)
@pytest.mark.parametrize("decision", ["APPROVED", "REJECTED"])
async def test_inspection_and_one_time_decision(
    database: AsyncEngine, tmp_path: Path, profile: str, decision: str
) -> None:
    sessions = async_sessionmaker(database)
    file = tmp_path / "a.txt"
    file.write_text("public fixture")
    access = RepositoryAccess(files=("a.txt",))
    if profile == "patch-review-v1":
        run_id = await review_run(database)
        async with sessions.begin() as session:
            await ApprovalRepository(session).request(run_id, PROPOSAL)
    elif profile == "repository-review-v1":
        run_id = await submit_review(sessions, tmp_path, access)
        await work_review_once(sessions, tmp_path, access, run_id=run_id)
    else:
        run_id = await submit_patch(sessions, tmp_path, "a.txt")
        await work_patch_once(sessions, tmp_path, "a.txt", run_id=run_id)
    async with sessions.begin() as session:
        history = await HistoryRepository(session).events(run_id)
        job = await session.get(JobRow, run_id)
        deadline = job.deadline_at if job else None
    app = create_app()
    token = secrets.token_urlsafe(32)
    app.state.database = database
    app.state.approval_token_digest = api.token_digest(token)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = f"/approvals/{run_id}"
        assert (await client.get(path)).status_code == 401
        client.headers["Authorization"] = "Bearer " + token
        assert (await client.get(f"/approvals/{uuid4()}")).status_code == 404
        response = await client.get(path)
        assert response.status_code == 200
        view = response.json()
        assert view["profile"] == profile and view["mutation"] is None
        assert view["request"]["proposal"]["before"] == (
            PROPOSAL.before if profile == "patch-review-v1" else file.read_text()
        )
        assert (view["workspace"] is None) == (profile == "patch-review-v1")
        body = {
            "decision": decision,
            "expected_profile": profile,
            "expected_approval_id": view["request"]["id"],
            "expected_revision": view["run_revision"],
            "expected_digest": view["request"]["digest"],
        }
        for field, wrong in (
            (
                "expected_profile",
                "patch-review-v1" if profile != "patch-review-v1" else "repository-patch-v1",
            ),
            ("expected_approval_id", str(uuid4())),
            ("expected_revision", 0),
            ("expected_digest", "0" * 64),
        ):
            assert (
                await client.post(path + "/decision", json=body | {field: wrong})
            ).status_code == 409
        assert (
            await client.post(path + "/decision", json=body | {"allow_write": True})
        ).status_code == 422
        async with sessions.begin() as session:
            assert await HistoryRepository(session).events(run_id) == history
        results = await asyncio.gather(
            client.post(path + "/decision", json=body),
            client.post(path + "/decision", json=body),
        )
        assert sorted(result.status_code for result in results) == [200, 409]
        view = (await client.get(path)).json()
        assert view["request"]["status"] == decision and view["mutation"] is None
        assert view["run_status"] == (
            "FAILED"
            if decision == "REJECTED"
            else "SUCCEEDED"
            if profile == "patch-review-v1"
            else "RUNNING"
        )
    async with sessions.begin() as session:
        job = await session.get(JobRow, run_id)
        if job:
            assert job.token is None and job.expires_at is None and job.deadline_at == deadline
    assert file.read_text() == "public fixture"
    if profile == "repository-patch-v1":
        if decision == "APPROVED":
            with pytest.raises(ToolError, match="tool_permission_denied"):
                await work_patch_once(sessions, tmp_path, "a.txt", run_id=run_id)
            assert file.read_text() == "public fixture"
            await expire(sessions, run_id)
            await work_patch_once(sessions, tmp_path, "a.txt", run_id=run_id, allow_write=True)
            assert file.read_text() == view["request"]["proposal"]["after"]
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer " + token},
            ) as inspector:
                applied = (await inspector.get(path)).json()
                assert applied["mutation"] == {"status": "SUCCEEDED", "error_code": None}
                assert applied["run_status"] == "SUCCEEDED"
        else:
            assert await work_patch_once(sessions, tmp_path, "a.txt", run_id=run_id) is None
            assert file.read_text() == "public fixture"


async def test_timeout_rolls_back_decision(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = await review_run(database)
    sessions = async_sessionmaker(database)
    async with sessions.begin() as session:
        proposal = await ApprovalRepository(session).request(run_id, PROPOSAL)
    original = ApprovalRepository.resolve
    resolved = asyncio.Event()

    async def stall(
        self: ApprovalRepository,
        run_id: UUID,
        *,
        decision: Literal["APPROVED", "REJECTED"],
        expected_revision: int,
        expected_digest: str,
    ) -> ApprovalRequest:
        result = await original(
            self,
            run_id,
            decision=decision,
            expected_revision=expected_revision,
            expected_digest=expected_digest,
        )
        resolved.set()
        await asyncio.sleep(10)
        return result

    monkeypatch.setattr(ApprovalRepository, "resolve", stall)
    monkeypatch.setattr(api, "REQUEST_TIMEOUT", 0.5)
    app = create_app()
    token = secrets.token_urlsafe(32)
    app.state.database = database
    app.state.approval_token_digest = api.token_digest(token)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        response = await client.post(
            f"/approvals/{run_id}/decision",
            json={
                "decision": "APPROVED",
                "expected_profile": "patch-review-v1",
                "expected_approval_id": str(proposal.id),
                "expected_revision": 2,
                "expected_digest": proposal.digest,
            },
        )
        assert response.status_code == 503
        assert resolved.is_set()
    async with sessions.begin() as session:
        assert (await ApprovalRepository(session).get(run_id)).status == "PENDING"
