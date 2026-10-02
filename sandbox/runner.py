"""Container-only entrypoint. Never import or execute fixture code on the host."""

import hashlib
import json
import os
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time

FIXTURES = {"clamp-v1", "boundary-v1", "timeout-v1", "output-v1"}
PATHS = ("TASK.md", "clamp.py", "test_clamp.py")


def inspect_files() -> list[dict[str, str]]:
    if set(os.listdir(".")) != set(PATHS):
        raise ValueError("Unexpected fixture entry")
    files = []
    for path in PATHS:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("Invalid fixture file")
            content = source.read(4097)
        if len(content) > 4096 or b"\0" in content:
            raise ValueError("Invalid fixture text")
        files.append({"path": path, "content": content.decode("utf-8")})
    return files


def workspace_digest(files: list[dict[str, str]]) -> str:
    # Matches the core's canonical InspectionResult field order/UTF-8 encoding.
    encoded = json.dumps(
        {"files": files, "cleanup_confirmed": True}, ensure_ascii=False, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_tests() -> dict[str, str | int | bool | None]:
    """Capture bounded untrusted output; stop the test process group before reading files."""
    process = subprocess.Popen(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", ".", "-v"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8"},
    )
    output = bytearray()
    status = "timeout"
    code: int | None = None
    try:
        assert process.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            deadline = time.monotonic() + 8
            while (remaining := deadline - time.monotonic()) > 0:
                if not selector.select(remaining):
                    break
                chunk = os.read(process.stdout.fileno(), min(1024, 2049 - len(output)))
                if not chunk:
                    code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
                    if code not in (0, 1):
                        raise ValueError("Unexpected test exit")
                    status = "passed" if code == 0 else "tests_failed"
                    break
                output.extend(chunk)
                if len(output) > 2048:
                    status = "output_limit"
                    break
    except subprocess.TimeoutExpired:
        pass
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        if process.stdout is not None:
            process.stdout.close()
    return {
        "status": status,
        "exit_code": code,
        "output": bytes(output[:2048]).decode("utf-8", errors="replace"),
        "output_truncated": status == "output_limit",
    }


def apply_patch() -> int:
    # Newline framing avoids relying on Docker's stdin EOF behavior.
    signal.alarm(8)  # Bound input wait even if the host disappears before sending.
    try:
        raw = sys.stdin.buffer.readline(32770)
    finally:
        signal.alarm(0)
    if len(raw) > 32769 or not raw.endswith(b"\n"):
        return 125
    payload = json.loads(raw)
    if set(payload) != {"approval_id", "proposal", "inspection"}:
        return 125
    proposal = payload["proposal"]
    if (
        set(proposal) != {"schema_version", "path", "before", "after"}
        or proposal["schema_version"] != 1
        or proposal["path"] != "clamp.py"
        or not isinstance(proposal["before"], str)
        or not isinstance(proposal["after"], str)
        or proposal["before"] == proposal["after"]
        or "\0" in proposal["after"]
        or len(proposal["after"].encode()) > 4096
    ):
        return 125
    before = inspect_files()
    if (
        payload["inspection"] != {"files": before, "cleanup_confirmed": True}
        or proposal["before"] != before[1]["content"]
    ):
        print(json.dumps({"error": "sandbox_preimage_mismatch"}))
        return 0
    expected = [dict(file) for file in before]
    expected[1]["content"] = proposal["after"]
    # No fixture code has run yet in this new private workspace.
    descriptor = os.open(
        ".runveil-patch", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "wb") as target:
        target.write(proposal["after"].encode())
        target.flush()
        os.fsync(target.fileno())
    os.replace(".runveil-patch", "clamp.py")
    if inspect_files() != expected:
        return 125
    tests = validate_tests()
    after = inspect_files()
    if after != expected:
        return 125
    print(
        json.dumps(
            {
                "applied": True,
                "proposal_digest": hashlib.sha256(
                    json.dumps(proposal, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "before_digest": workspace_digest(before),
                "after_digest": workspace_digest(after),
                "tests": tests,
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    inspection = len(sys.argv) == 3 and sys.argv[1:] == ["clamp-v1", "inspect"]
    patch = len(sys.argv) == 3 and sys.argv[1:] == ["clamp-v1", "apply"]
    if not (inspection or patch) and (len(sys.argv) != 2 or sys.argv[1] not in FIXTURES):
        return 125
    shutil.copytree("/opt/fixtures/" + sys.argv[1], "/workspace/repository", symlinks=True)
    os.chdir("/workspace/repository")
    if inspection:
        output = json.dumps({"files": inspect_files()}, ensure_ascii=False)
        if len(output.encode()) > 12000:
            return 125
        print(output)
        return 0
    if patch:
        return apply_patch()
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
