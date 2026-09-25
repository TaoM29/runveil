"""Boot both real HTTP servers and verify their public foundation contracts."""

import json
import os
import socket
import subprocess
import tempfile
import time
from contextlib import ExitStack
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def stop(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def wait_for_health(process: subprocess.Popen[bytes], port: int, service: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{service} exited with {process.returncode}")
        try:
            with urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                payload = json.load(response)
                if response.status != 200 or payload != {"status": "ok", "service": service}:
                    raise RuntimeError(f"Unexpected {service} health: {payload}")
                return
        except (URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {service}")


def main() -> None:
    # Invoke executables directly so cleanup owns each server process.
    api_port, web_port = free_port(), free_port()
    while web_port == api_port:
        web_port = free_port()
    commands = [
        (
            "api",
            api_port,
            ["uvicorn", "runveil_api.main:app", "--host", "127.0.0.1", "--port", str(api_port)],
        ),
        (
            "web",
            web_port,
            [
                "node",
                "node_modules/next/dist/bin/next",
                "start",
                "apps/web",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(web_port),
            ],
        ),
    ]
    with ExitStack() as stack:
        logs: list[tuple[str, BinaryIO]] = []
        try:
            for service, port, command in commands:
                log = stack.enter_context(tempfile.TemporaryFile())
                logs.append((service, log))
                process = subprocess.Popen(
                    command,
                    stdout=log,
                    stderr=log,
                    env={**os.environ, "NEXT_TELEMETRY_DISABLED": "1"},
                )
                stack.callback(stop, process)
                wait_for_health(process, port, service)
                print(f"PASS {service}: HTTP health contract")
            with urlopen(f"http://127.0.0.1:{web_port}/", timeout=5) as response:
                html = response.read().decode()
                if response.status != 200 or "Runveil" not in html or "Phase 0" not in html:
                    raise RuntimeError("Web page did not render the foundation content")
            print("PASS web: production home page")
            expected_ready = bool(os.environ.get("DATABASE_URL"))
            try:
                with urlopen(f"http://127.0.0.1:{api_port}/ready", timeout=5) as readiness:
                    ready_code, ready_body = readiness.status, json.load(readiness)
            except HTTPError as error:
                ready_code, ready_body = error.code, json.load(error)
                error.close()
            expected_body = (
                {"status": "ok", "database": "reachable"}
                if expected_ready
                else {"status": "unavailable", "database": "unavailable"}
            )
            if ready_code != (200 if expected_ready else 503) or ready_body != expected_body:
                raise RuntimeError("Unexpected API database readiness response")
            print("PASS api: database readiness contract")
        except (OSError, RuntimeError):
            for service, saved_log in logs:
                saved_log.seek(0)
                print(f"{service} logs:\n{saved_log.read().decode(errors='replace')}")
            raise


if __name__ == "__main__":
    main()
