"""Fixed entry points for the private image; never log credentials or raw failures."""

import asyncio
import os
import ssl
import sys
import urllib.request
from pathlib import Path

import uvicorn
from runveil_persistence.database import create_engine
from runveil_persistence.deployment import ROLES, cloud_database_url, migrate, require_schema
from runveil_worker.service import serve
from runveil_worker.sqs import queue_region
from runveil_worker.worker import CALLS_PROFILE, submit
from sqlalchemy.ext.asyncio import async_sessionmaker


def write_tls() -> None:
    for name, key in (("certificate", "RUNVEIL_TLS_CERTIFICATE"), ("key", "RUNVEIL_TLS_KEY")):
        path = Path(f"/tmp/{name}.pem")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(os.environ.pop(key))


def healthcheck() -> None:
    context = ssl.create_default_context(cafile="/tmp/certificate.pem")
    context.check_hostname = False
    context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    with urllib.request.urlopen(
        "https://127.0.0.1:8443/ready", context=context, timeout=3
    ) as response:
        if response.status != 200:
            raise ValueError("API not ready")


async def administration(mode: str) -> None:
    engine = create_engine(cloud_database_url())
    try:
        if mode == "migrate":
            passwords = {actor: os.environ[f"RUNVEIL_{actor.upper()}_PASSWORD"] for actor in ROLES}
            async with engine.begin() as connection:
                await connection.run_sync(lambda conn: migrate(conn, passwords))
            print("migration_succeeded", flush=True)
        elif mode == "submit":
            await require_schema(engine)
            url = os.environ["RUNVEIL_QUEUE_URL"]
            queue_region(url)
            run_id = await submit(async_sessionmaker(engine), profile=CALLS_PROFILE, queue_url=url)
            print(f"run_id={run_id}", flush=True)
        else:
            raise ValueError("Unknown administrative command")
    finally:
        await engine.dispose()


def main() -> int:
    try:
        if len(sys.argv) != 2:
            raise ValueError("Choose an explicit deployment command")
        actor = sys.argv[1]
        if actor == "healthcheck":
            healthcheck()
        elif actor == "api":
            if os.environ["RUNVEIL_DB_USER"] != ROLES["api"]:
                raise ValueError("Unexpected API identity")
            write_tls()
            uvicorn.run(
                "runveil_api.private:app",
                host="0.0.0.0",
                port=8443,
                ssl_certfile="/tmp/certificate.pem",
                ssl_keyfile="/tmp/key.pem",
                access_log=False,
                log_level="critical",
                proxy_headers=False,
                timeout_graceful_shutdown=30,
            )
        elif actor in ("worker", "relay"):
            if os.environ["RUNVEIL_DB_USER"] != ROLES[actor]:
                raise ValueError("Unexpected worker identity")
            asyncio.run(
                serve("worker" if actor == "worker" else "relay", os.environ["RUNVEIL_QUEUE_URL"])
            )
        elif actor in ("migrate", "submit"):
            asyncio.run(administration(actor))
        else:
            raise ValueError("Unsupported deployment command")
        return 0
    except (KeyboardInterrupt, asyncio.CancelledError):
        return 130
    except Exception:
        print("deployment_failed", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
