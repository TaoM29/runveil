"""An offline provider with ordered, detached fixtures and no implicit retries."""

from collections.abc import Sequence

from runveil_core.models import ModelRequest, ModelResponse, ProviderError, ProviderErrorCode


class ScriptedProvider:
    def __init__(self, script: Sequence[ModelResponse | ProviderErrorCode]) -> None:
        self._script = tuple(
            item if isinstance(item, ProviderErrorCode) else item.model_dump_json()
            for item in script
        )
        self._position = 0
        self._requests: list[str] = []

    @property
    def requests(self) -> tuple[ModelRequest, ...]:
        return tuple(ModelRequest.model_validate_json(item) for item in self._requests)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        # No await between consuming a fixture and recording its request.
        self._requests.append(request.model_dump_json())
        if self._position == len(self._script):
            raise ProviderError(ProviderErrorCode.SCRIPT_EXHAUSTED)
        item = self._script[self._position]
        self._position += 1
        if isinstance(item, ProviderErrorCode):
            raise ProviderError(item)
        return ModelResponse.model_validate_json(item)
