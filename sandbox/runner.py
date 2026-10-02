"""Container-only entrypoint. Never import or execute fixture code on the host."""

import json
import os
import shutil
import stat
import subprocess
import sys

FIXTURES = {"clamp-v1", "boundary-v1", "timeout-v1", "output-v1"}


def main() -> int:
    inspection = len(sys.argv) == 3 and sys.argv[1:] == ["clamp-v1", "inspect"]
    if not inspection and (len(sys.argv) != 2 or sys.argv[1] not in FIXTURES):
        return 125
    shutil.copytree("/opt/fixtures/" + sys.argv[1], "/workspace/repository", symlinks=True)
    os.chdir("/workspace/repository")
    if inspection:
        files = []
        for path in ("TASK.md", "clamp.py", "test_clamp.py"):
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    return 125
                content = source.read(4097)
            if len(content) > 4096 or b"\0" in content:
                return 125
            files.append({"path": path, "content": content.decode("utf-8")})
        output = json.dumps({"files": files}, ensure_ascii=False)
        if len(output.encode()) > 12000:
            return 125
        print(output)
        return 0
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
