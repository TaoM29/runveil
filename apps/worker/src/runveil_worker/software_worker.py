"""Project-owned fixture workflow: inspect, test, propose, approve, apply and validate."""

import asyncio

from runveil_worker.sandbox_patch_worker import main
from runveil_worker.telemetry import telemetry

if __name__ == "__main__":
    try:
        with telemetry():
            raise SystemExit(asyncio.run(main(workflow=True)))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception:
        print("software_workflow_failed")
        raise SystemExit(1) from None
