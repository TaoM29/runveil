"""Container-only entrypoint. Never import or execute fixture code on the host."""

import os
import shutil
import subprocess
import sys

FIXTURES = {"clamp-v1", "boundary-v1", "timeout-v1", "output-v1"}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in FIXTURES:
        return 125
    shutil.copytree("/opt/fixtures/" + sys.argv[1], "/workspace/repository")
    os.chdir("/workspace/repository")
    try:
        return subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", ".", "-v"],
            stdin=subprocess.DEVNULL,
            timeout=8,
            check=False,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8"},
        ).returncode
    except subprocess.TimeoutExpired:
        return 124


if __name__ == "__main__":
    raise SystemExit(main())
