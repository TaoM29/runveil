"""Opt-in real Docker boundary acceptance; uses only the built project fixture image."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from runveil_tools.sandbox import OUTPUT_LIMIT, FixtureSandbox, _command


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--socket", type=Path, default=Path("/var/run/docker.sock"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runner = FixtureSandbox(args.image, socket=args.socket)
    with args.output.open("x", encoding="utf-8") as output:
        records = []
        for fixture, expected in (
            ("boundary-v1", "passed"),
            ("clamp-v1", "tests_failed"),
            ("timeout-v1", "timeout"),
            ("output-v1", "output_limit"),
        ):
            result = await runner.run(fixture)
            assert result.status == expected, result.model_dump_json()
            assert result.cleanup_confirmed
            if fixture == "timeout-v1":
                assert result.exit_code == 124  # In-container watchdog, not host timeout.
            if fixture == "output-v1":
                assert len(result.output.encode()) == OUTPUT_LIMIT
            records.append(
                {
                    **result.model_dump(mode="json", exclude={"output"}),
                    "output_bytes": len(result.output.encode()),
                    "output_sha256": hashlib.sha256(result.output.encode()).hexdigest(),
                    "output_excerpt": result.output[:1024],
                }
            )

        async def containers(*, running: bool = False) -> bytes:
            result = await _command(
                (
                    *runner._docker,
                    "ps",
                    "-q" if running else "-aq",
                    "--filter",
                    "label=runveil.sandbox=docker-fixture-v1",
                ),
                15,
            )
            assert result.code == 0
            return result.output

        before = await containers()
        running_before = await containers(running=True)
        task = asyncio.create_task(runner.run("timeout-v1"))
        try:
            # Wait for creation rather than assuming Docker startup latency.
            async with asyncio.timeout(10):
                while await containers(running=True) == running_before:
                    await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            else:
                raise AssertionError("Cancellation did not propagate")
            assert await containers() == before
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        output.write(
            json.dumps({"results": records, "cancellation_cleanup": True}, indent=2) + "\n"
        )
    print(
        "Sandbox acceptance passed: isolation, failed baseline, "
        "watchdog, output limit, cancellation."
    )


if __name__ == "__main__":
    asyncio.run(main())
