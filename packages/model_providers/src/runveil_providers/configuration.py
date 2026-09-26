"""Operator-only transport configuration, never part of invocation payloads."""

from ipaddress import ip_address
from typing import Self

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr, model_validator


class ProviderConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    base_url: str = "https://api.openai.com/v1"
    api_key: SecretStr | None = None

    @model_validator(mode="after")
    def validate_transport(self) -> Self:
        try:
            url = httpx.URL(self.base_url)
            loopback = url.host == "localhost"
            if not loopback:
                try:
                    loopback = ip_address(url.host).is_loopback
                except ValueError:
                    pass
            if (
                not url.host
                or url.userinfo
                or url.query
                or url.fragment
                or (url.scheme != "https" and not (url.scheme == "http" and loopback))
            ):
                raise ValueError
            if self.api_key is not None:
                key = self.api_key.get_secret_value()
                if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
                    raise ValueError
            elif not loopback:
                raise ValueError
        except (ValueError, httpx.InvalidURL):
            raise ValueError("Invalid provider transport configuration") from None
        return self
