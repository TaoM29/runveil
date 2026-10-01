"""Bounded review data, deliberately without a mutation capability."""

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from runveil_core.agents import JsonValue
from runveil_core.models import Contract

REVIEW_CONFIGURATION: dict[str, JsonValue] = {"workflow": "patch-review-v1"}
MAX_PROPOSAL_BYTES = 65_536


class PatchProposal(Contract):
    schema_version: Literal[1] = 1
    path: Annotated[str, Field(min_length=1, max_length=240)]
    before: Annotated[str, Field(max_length=16384)]
    after: Annotated[str, Field(max_length=16384)]

    @model_validator(mode="after")
    def validate_replacement(self) -> Self:
        if (
            any(part in ("", ".", "..") for part in self.path.split("/"))
            or any(
                not (char.isascii() and (char.isalnum() or char in "._-/")) for char in self.path
            )
            or self.before == self.after
            or "\x00" in self.before + self.after
        ):
            raise ValueError("Invalid single-file replacement proposal")
        if len(self.canonical().encode("utf-8")) > MAX_PROPOSAL_BYTES:
            raise ValueError("Proposal exceeds its byte limit")
        return self

    def canonical(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()


class ApprovalRequest(Contract):
    id: UUID
    run_id: UUID
    proposal: PatchProposal
    digest: str
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    requested_at: datetime
    decided_at: datetime | None
