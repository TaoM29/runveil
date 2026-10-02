"""Sandbox evidence search and approved repair for project-owned fixture tasks."""

import asyncio

from runveil_worker.sandbox_patch_worker import main
from runveil_worker.telemetry import telemetry

if __name__ == "__main__":
    try:
        with telemetry():
            raise SystemExit(asyncio.run(main(workflow=True, search=True)))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception:
        print("software_search_failed")
        raise SystemExit(1) from None
