"""Public calibration scripts: answers are fixtures, never model-quality evidence."""

from runveil_core.models import FinalResult, FinishAction, ToolAction
from runveil_core.runtime import ModelPricing, RuntimeConfig
from runveil_core.tools import Permission, ToolPolicy

from runveil_evaluations.contracts import EvalCase, EvalSuite

POLICY = ToolPolicy(
    allowed_tools=("repository.read_file", "repository.search"), permissions=(Permission.READ,)
)


def configuration(max_steps: int) -> RuntimeConfig:
    if max_steps not in (3, 5):
        raise ValueError("Only the two calibration budgets are supported")
    return RuntimeConfig(
        schema_version=8,
        provider="scripted",
        model="eval-fixture-v1",
        system_prompt="Inspect the public code fixture using only granted read tools.",
        tool_policy=POLICY,
        max_steps=max_steps,
        timeout_seconds=5.0,
        max_elapsed_seconds=60,
        max_input_tokens=1000,
        max_total_output_tokens=1000,
        max_cost_nanousd=1_000_000,
        max_identical_tool_calls=2,
        max_model_calls=3,
        max_tool_calls=2,
        pricing=ModelPricing(
            price_id="synthetic-eval-v1",
            provider="scripted",
            model="eval-fixture-v1",
            input_nanousd_per_token=1000,
            output_nanousd_per_token=2000,
        ),
    )


def finish(summary: str) -> str:
    return FinishAction(
        action="finish", result=FinalResult(summary=summary, artifacts=())
    ).model_dump_json()


READ = ToolAction(
    action="tool_call",
    tool_name="repository.read_file",
    arguments={"path": "example.py"},
    decision_summary="Read the allowlisted public source.",
).model_dump_json()
SEARCH = ToolAction(
    action="tool_call",
    tool_name="repository.search",
    arguments={"query": "def clamp"},
    decision_summary="Locate the public function.",
).model_dump_json()

SUITE = EvalSuite(
    name="code-reading-calibration",
    version="1",
    cases=(
        EvalCase(
            id="literal",
            task="What does `return 7` return? Answer with the integer only.",
            file_content="def constant():\n    return 7\n",
            responses=(finish("7"),),
            expected_summary="7",
            expected_tools=(),
        ),
        EvalCase(
            id="read-default",
            task="Read example.py. What is the default separator?",
            file_content='def join(parts, sep="-"):\n    return sep.join(parts)\n',
            responses=(READ, finish("-")),
            expected_summary="-",
            expected_tools=("repository.read_file",),
        ),
        EvalCase(
            id="search-and-read",
            task="Locate then read clamp. What is its upper bound?",
            file_content="def clamp(value):\n    return min(10, max(0, value))\n",
            responses=(SEARCH, READ, finish("10")),
            expected_summary="10",
            expected_tools=("repository.search", "repository.read_file"),
        ),
    ),
)
