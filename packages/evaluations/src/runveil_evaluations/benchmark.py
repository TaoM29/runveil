"""Frozen public code-reading corpus v1; source is data, never executable input.

The held-out partition is reserved from tuning, not secret. Scripts contain answers
and establish harness evidence only. See docs/operations/BENCHMARK.md for rationales.
"""

from typing import Literal

from runveil_core.models import ToolAction

from runveil_evaluations.contracts import EvalCase, EvalSuite
from runveil_evaluations.fixtures import READ, SUITE, finish


def _case(
    identity: str, source: str, question: str, answer: str, *, locate: str | None = None
) -> EvalCase:
    responses: tuple[str, ...]
    if locate is None:
        task = f"Read example.py. {question} Return only the answer, without quotes or explanation."
        responses = (READ, finish(answer))
        tools: tuple[Literal["repository.read_file", "repository.search"], ...] = (
            "repository.read_file",
        )
    else:
        task = (
            f"Search example.py for `{locate}`, then read the file. {question} "
            "Return only the answer, without quotes or explanation."
        )
        search = ToolAction(
            action="tool_call",
            tool_name="repository.search",
            arguments={"query": locate},
            decision_summary="Locate the requested public source definition.",
        ).model_dump_json()
        responses = (search, READ, finish(answer))
        tools = ("repository.search", "repository.read_file")
    return EvalCase(
        id=identity,
        task=task,
        file_content=source,
        responses=responses,
        expected_summary=answer,
        expected_tools=tools,
    )


DEVELOPMENT = EvalSuite(
    name="controlled-code-reading",
    version="1",
    split="development",
    cases=(
        _case(
            "defaults-retries",
            "def fetch(url, retries=3):\n    return retries\n",
            "What is the default value of retries?",
            "3",
        ),
        _case(
            "defaults-keyword-only",
            "def render(title, *, compact=False):\n"
            "    return title if compact else title + '\\n'\n",
            "What is the default value of compact?",
            "False",
            locate="def render",
        ),
        _case(
            "branches-inclusive",
            "def band(value):\n    if value <= 5:\n        return 'low'\n    return 'high'\n",
            "What does band(5) return?",
            "low",
        ),
        _case(
            "branches-first-match",
            "def classify(value):\n    if value < 0:\n        return 'negative'\n"
            "    if value % 2 == 0:\n        return 'even'\n    return 'odd'\n",
            "What does classify(-2) return?",
            "negative",
            locate="def classify",
        ),
        _case(
            "collections-copy",
            "def size():\n    original = [1, 2]\n    copied = original[:]\n"
            "    copied.append(3)\n    return len(original)\n",
            "What does size() return?",
            "2",
        ),
        _case(
            "collections-fallback",
            "def timeout():\n    settings = {'timeout': 4}\n"
            "    return settings.get('missing', 9)\n",
            "What does timeout() return?",
            "9",
            locate="def timeout",
        ),
        _case(
            "strings-normalize",
            "def normalize(value):\n    return value.strip().lower()\n",
            "What does normalize(' A ') return?",
            "a",
        ),
        _case(
            "strings-split-limit",
            "def tail(value):\n    return value.split(':', 1)[1]\n",
            "What does tail('a:b:c') return?",
            "b:c",
            locate="def tail",
        ),
        _case(
            "iteration-range",
            "def total():\n    return sum(range(1, 6, 2))\n",
            "What does total() return?",
            "9",
        ),
        _case(
            "iteration-filter",
            "def count():\n    return len([n for n in range(6) if n % 2 == 0])\n",
            "What does count() return?",
            "3",
            locate="def count",
        ),
        _case(
            "exceptions-fallback",
            "def number(value):\n    try:\n        return int(value)\n"
            "    except ValueError:\n        return -1\n",
            "What does number('oops') return?",
            "-1",
        ),
        _case(
            "exceptions-finally",
            "def events():\n    log = []\n    try:\n        log.append('try')\n"
            "    finally:\n        log.append('finally')\n    return ','.join(log)\n",
            "What does events() return?",
            "try,finally",
            locate="def events",
        ),
        _case(
            "scope-shadowing",
            "LIMIT = 8\ndef local():\n    LIMIT = 2\n    return LIMIT\n",
            "What does local() return?",
            "2",
        ),
        _case(
            "scope-closure",
            "def build(prefix):\n    def label(value):\n        return prefix + value\n"
            "    return label\n",
            "What does build('pre-')('x') return?",
            "pre-x",
            locate="def build",
        ),
        _case(
            "inspection-async",
            "async def load(reader):\n    return await reader.read()\n",
            "Which reader method is awaited? Return its name only.",
            "read",
        ),
        _case(
            "inspection-resource-mode",
            "def first_line(path):\n    with open(path, 'r', encoding='utf-8') as stream:\n"
            "        return stream.readline()\n",
            "What mode is passed to open?",
            "r",
            locate="def first_line",
        ),
    ),
)

HELD_OUT = EvalSuite(
    name="controlled-code-reading",
    version="1",
    split="held-out",
    cases=(
        _case(
            "defaults-captured-value",
            "LIMIT = 4\ndef cap(value=LIMIT):\n    return value\nLIMIT = 9\n",
            "After the module statements, what does cap() return?",
            "4",
        ),
        _case(
            "branches-short-circuit",
            "def usable(items):\n    return bool(items) and items[0] > 0\n",
            "What does usable([]) return?",
            "False",
            locate="def usable",
        ),
        _case(
            "collections-alias",
            "def head():\n    values = [2, 4]\n    alias = values\n"
            "    alias[0] = 7\n    return values[0]\n",
            "What does head() return?",
            "7",
        ),
        _case(
            "strings-suffix",
            "def stem(name):\n    return name.removesuffix('.py')\n",
            "What does stem('copy.py.py') return?",
            "copy.py",
            locate="def stem",
        ),
        _case(
            "iteration-zip-bound",
            "def pairs():\n    return len(list(zip([1, 2, 3], ['a', 'b'])))\n",
            "What does pairs() return?",
            "2",
        ),
        _case(
            "exceptions-else",
            "def parse(value):\n    try:\n        int(value)\n"
            "    except ValueError:\n        return 'bad'\n    else:\n        return 'ok'\n",
            "What does parse('12') return?",
            "ok",
            locate="def parse",
        ),
        _case(
            "scope-nonlocal",
            "def counter():\n    value = 1\n    def bump():\n        nonlocal value\n"
            "        value += 2\n    bump()\n    return value\n",
            "What does counter() return?",
            "3",
        ),
        _case(
            "inspection-handler-type",
            "def lookup(mapping, key):\n    try:\n        return mapping[key]\n"
            "    except KeyError:\n        return None\n",
            "Which exception class is explicitly caught?",
            "KeyError",
            locate="def lookup",
        ),
    ),
)


def select_suite(name: str, split: str) -> EvalSuite:
    """Closed selection; held-out requires an explicit caller choice."""
    if name == "calibration" and split == "development":
        return SUITE
    if name == "code-reading" and split == "development":
        return DEVELOPMENT
    if name == "code-reading" and split == "held-out":
        return HELD_OUT
    raise ValueError("Unsupported suite/split combination")
