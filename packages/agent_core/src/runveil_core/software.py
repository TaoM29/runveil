"""The closed inspect/test/propose workflow for the project-owned fixture tasks."""

from runveil_core.approvals import PROPOSAL_TOOL
from runveil_core.models import Message
from runveil_core.sandbox import TEST_TOOL, TestsResult
from runveil_core.sandbox_patch import PATCH_POLICY
from runveil_core.sandbox_review import INSPECT_TOOL
from runveil_core.sandbox_search import SEARCH_TOOL
from runveil_core.tools import ToolError, ToolErrorCode, ToolPolicy

SOFTWARE_PROFILE = "software-engineering-v1"
SOFTWARE_POLICY = ToolPolicy(
    allowed_tools=(*PATCH_POLICY.allowed_tools, TEST_TOOL), permissions=PATCH_POLICY.permissions
)

SEARCH_PROFILE = "software-engineering-v2"
SEARCH_POLICY = ToolPolicy(
    allowed_tools=(*SOFTWARE_POLICY.allowed_tools, SEARCH_TOOL),
    permissions=SOFTWARE_POLICY.permissions,
)


def baseline_failed(result: TestsResult) -> bool:
    return result.status == "tests_failed" and result.exit_code == 1


def workflow_tool(messages: tuple[Message, ...], *, search: bool = False) -> str:
    """Only completed, ordered observations advance the pre-approval workflow."""
    observations = [m for m in messages if m.role == "tool"]
    names = [m.tool_name for m in observations]
    if not names:
        return INSPECT_TOOL
    if search and names == [INSPECT_TOOL]:
        return SEARCH_TOOL
    prefix = [INSPECT_TOOL, SEARCH_TOOL] if search else [INSPECT_TOOL]
    if names == prefix:
        return TEST_TOOL
    if names == [*prefix, TEST_TOOL]:
        try:
            result = TestsResult.model_validate_json(observations[-1].content)
        except ValueError:
            raise ToolError(ToolErrorCode.INVALID_OUTPUT) from None
        if baseline_failed(result):
            return PROPOSAL_TOOL
    raise ToolError(ToolErrorCode.DENIED)
