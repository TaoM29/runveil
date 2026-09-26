"""Explicitly opt-in single paid invocation; never imported or invoked by CI."""

import argparse
import asyncio
import json
import os
from collections.abc import Sequence

from pydantic import SecretStr
from runveil_core.models import (
    FinishAction,
    Message,
    ModelRequest,
    ProviderError,
    validate_response,
)

from runveil_providers.chat import OpenAICompatibleProvider
from runveil_providers.configuration import ProviderConfiguration


async def _verify(configuration: ProviderConfiguration, model: str) -> None:
    request = ModelRequest(
        model=model,
        messages=(
            Message(
                role="user", content="Finish with summary 'Fixture complete' and no artifacts."
            ),
        ),
        max_output_tokens=256,
        timeout_seconds=30.0,
    )
    async with OpenAICompatibleProvider(configuration) as provider:
        response = await provider.generate(request)
        action = validate_response(request, response)
        if not isinstance(action, FinishAction) or action.result.artifacts:
            raise ValueError("Unexpected fixture action")
        print(
            json.dumps(
                {
                    "status": "passed",
                    "action": "finish",
                    "usage": response.usage.model_dump(mode="json"),
                    "latency_ms": round(response.latency_ms, 2),
                }
            )
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Make one billable structured fixture invocation.")
    parser.add_argument(
        "--live", action="store_true", help="Explicitly enable a live provider call"
    )
    args = parser.parse_args(argv)
    if not args.live:
        parser.error("Pass --live to explicitly enable a billable provider request")
    try:
        model = os.environ.get("RUNVEIL_PROVIDER_MODEL", "")
        key = os.environ.get("RUNVEIL_PROVIDER_API_KEY")
        configuration = ProviderConfiguration(
            base_url=os.environ.get("RUNVEIL_PROVIDER_BASE_URL", "https://api.openai.com/v1"),
            api_key=SecretStr(key) if key is not None else None,
        )
        asyncio.run(_verify(configuration, model))
    except ProviderError as error:
        print(json.dumps({"status": "failed", "error_code": error.code.value}))
        return 1
    except ValueError:
        print(
            json.dumps({"status": "failed", "error_code": "invalid_live_configuration_or_result"})
        )
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
