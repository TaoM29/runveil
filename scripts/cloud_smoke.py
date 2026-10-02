"""Disposable TLS/PostgreSQL/image acceptance, isolated from AWS and developer data."""

import argparse
import os
import re
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

API_PROBE = """
import json, os, ssl, time, urllib.error, urllib.request
context = ssl.create_default_context(cafile="/client-ca.pem")
base = "https://api:8443"
for attempt in range(45):
    try:
        with urllib.request.urlopen(base + "/ready", context=context, timeout=2) as response:
            assert response.status == 200
        break
    except (OSError, urllib.error.URLError):
        time.sleep(1)
else:
    raise SystemExit("private_api_not_ready")
route = "/runs/" + os.environ["RUN_ID"] + "/trace"
request = urllib.request.Request(base + route, headers={
    "Authorization": "Bearer " + os.environ["RUNVEIL_TRACE_TOKEN"]})
with urllib.request.urlopen(request, context=context, timeout=3) as response:
    assert json.load(response)["status"] == "QUEUED"
for route, status in ((route, 401), ("/openapi.json", 404), ("/approvals/invalid", 404)):
    try:
        urllib.request.urlopen(base + route, context=context, timeout=3)
        raise SystemExit("unauthorized_route")
    except urllib.error.HTTPError as error:
        assert error.code == status
"""


def run(*args: str, env: dict[str, str] | None = None, timeout: int = 120) -> str:
    result = subprocess.run(
        args,
        env=None if env is None else os.environ | env,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout.strip()


def smoke(image: str) -> None:
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image) is None:
        raise ValueError("Use a built local image ID")
    name = f"runveil-cloud-{uuid4().hex[:12]}"
    print(f"cloud_smoke_resources={name}", flush=True)
    containers: list[str] = []
    network = False
    with tempfile.TemporaryDirectory(prefix="runveil-cloud-") as directory:
        root = Path(directory)
        cert, key = root / "certificate.pem", root / "key.pem"
        run(
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-subj",
            "/CN=database",
            "-addext",
            "subjectAltName=DNS:database,DNS:localhost,DNS:api",
        )
        key.chmod(0o644)  # Disposable test material; PostgreSQL copies it to a mode-0600 file.
        root.chmod(0o755)
        values = {
            "RUNVEIL_DB_HOST": "database",
            "RUNVEIL_DB_USER": "runveil",
            "RUNVEIL_DB_PASSWORD": secrets.token_hex(32),
            "RUNVEIL_API_PASSWORD": secrets.token_hex(32),
            "RUNVEIL_WORKER_PASSWORD": secrets.token_hex(32),
            "RUNVEIL_RELAY_PASSWORD": secrets.token_hex(32),
            "RUNVEIL_QUEUE_URL": "https://sqs.eu-west-1.amazonaws.com/123456789012/offline",
            "AWS_EC2_METADATA_DISABLED": "true",
        }
        try:
            run("docker", "network", "create", "--internal", name)
            network = True
            database = f"{name}-database"
            containers.append(database)
            run(
                "docker",
                "run",
                "--rm",
                "-d",
                "--name",
                database,
                "--network",
                name,
                "--network-alias",
                "database",
                "-v",
                f"{directory}:/certs:ro",
                "-e",
                "POSTGRES_PASSWORD",
                "-e",
                "POSTGRES_USER=runveil",
                "-e",
                "POSTGRES_DB=runveil",
                "--entrypoint",
                "sh",
                "postgres:17.9-bookworm",
                "-ec",
                "cp /certs/key.pem /tmp/server.key; chown postgres:postgres /tmp/server.key; "
                "chmod 600 /tmp/server.key; exec docker-entrypoint.sh postgres "
                "-c ssl=on -c ssl_cert_file=/certs/certificate.pem -c ssl_key_file=/tmp/server.key",
                env={"POSTGRES_PASSWORD": values["RUNVEIL_DB_PASSWORD"]},
            )
            for _ in range(60):
                try:
                    run(
                        "docker",
                        "exec",
                        database,
                        "pg_isready",
                        "-h",
                        "127.0.0.1",
                        "-U",
                        "runveil",
                        "-d",
                        "runveil",
                    )
                    break
                except subprocess.CalledProcessError:
                    time.sleep(1)
            else:
                raise ValueError("Test database did not become ready")

            def task(actor: str, settings: dict[str, str], *, background: bool = False) -> str:
                identity = f"{name}-{actor}"
                containers.append(identity)
                args = [
                    "docker",
                    "run",
                    "--init",
                    "--name",
                    identity,
                    "--network",
                    name,
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "-v",
                    f"{cert}:/app/certs/rds.pem:ro",
                ]
                if background:
                    args.append("-d")
                else:
                    args.append("--rm")
                if actor == "api":
                    args.extend(["--network-alias", "api"])
                for setting in settings:
                    args.extend(["-e", setting])
                return run(*args, image, actor, env=settings)

            assert task("migrate", values).endswith("migration_succeeded")
            run_id = task("submit", values).removeprefix("run_id=")
            assert re.fullmatch(r"[0-9a-f-]{36}", run_id)
            print(
                "PASS image: explicit migrations and fixed-fixture enrollment over verified TLS",
                flush=True,
            )
            api = values | {
                "RUNVEIL_DB_USER": "runveil_api",
                "RUNVEIL_DB_PASSWORD": values["RUNVEIL_API_PASSWORD"],
                "RUNVEIL_TRACE_TOKEN": secrets.token_urlsafe(32),
                "RUNVEIL_TLS_CERTIFICATE": cert.read_text(),
                "RUNVEIL_TLS_KEY": key.read_text(),
            }
            api = {
                k: v
                for k, v in api.items()
                if not k.endswith("_PASSWORD") or k == "RUNVEIL_DB_PASSWORD"
            }
            task("api", api, background=True)
            client = f"{name}-client"
            containers.append(client)
            run(
                "docker",
                "run",
                "--rm",
                "--name",
                client,
                "--network",
                name,
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "-v",
                f"{cert}:/client-ca.pem:ro",
                "-e",
                "RUNVEIL_TRACE_TOKEN",
                "-e",
                "RUN_ID",
                "--entrypoint",
                "python",
                image,
                "-c",
                API_PROBE,
                env={"RUNVEIL_TRACE_TOKEN": api["RUNVEIL_TRACE_TOKEN"], "RUN_ID": run_id},
            )
            run(
                "docker",
                "exec",
                f"{name}-api",
                "python",
                "scripts/cloud_entrypoint.py",
                "healthcheck",
            )
            print(
                "PASS image: TLS API, trace authentication, route restrictions and health probe",
                flush=True,
            )
            for actor in ("relay", "worker"):
                settings = {k: v for k, v in values.items() if not k.endswith("_PASSWORD")}
                settings.update(
                    RUNVEIL_DB_USER=f"runveil_{actor}",
                    RUNVEIL_DB_PASSWORD=values[f"RUNVEIL_{actor.upper()}_PASSWORD"],
                )
                task(actor, settings, background=True)
                for _ in range(45):
                    if "broker_service_started" in run("docker", "logs", f"{name}-{actor}"):
                        break
                    time.sleep(1)
                else:
                    raise ValueError("Broker process did not finish startup")
                assert (
                    run("docker", "inspect", "--format", "{{.State.Running}}", f"{name}-{actor}")
                    == "true"
                )
                run("docker", "stop", "--time", "115", f"{name}-{actor}", timeout=130)
                assert (
                    run("docker", "inspect", "--format", "{{.State.ExitCode}}", f"{name}-{actor}")
                    == "0"
                )
            print(
                "PASS image: fixed relay/consumer start and stop in a network with no AWS access",
                flush=True,
            )
        finally:
            cleanup_failed = False
            for container in reversed(containers):
                try:
                    subprocess.run(
                        ["docker", "rm", "-f", "-v", container], capture_output=True, timeout=10
                    )
                except subprocess.TimeoutExpired:
                    cleanup_failed = True
            if network:
                try:
                    run("docker", "network", "rm", name, timeout=10)
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    cleanup_failed = True
            if cleanup_failed:
                raise RuntimeError(f"Cleanup requires operator attention: {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    try:
        smoke(args.image)
    except Exception:
        print("cloud_smoke_failed")
        raise SystemExit(1) from None
