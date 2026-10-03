"""Opt-in, payload-free observations; never part of an execution decision."""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal
from uuid import UUID

from opentelemetry.context import Context
from opentelemetry.trace import Span, StatusCode, Tracer, set_span_in_context

_tracer: ContextVar[Tracer | None] = ContextVar("runveil_tracer", default=None)
_parent: ContextVar[Span | None] = ContextVar("runveil_span", default=None)

NUMBER_FIELDS = frozenset(
    {
        "request_sequence",
        "steps",
        "retries_scheduled",
        "model_attempts",
        "input_tokens",
        "output_tokens",
        "unknown_usage_attempts",
        "known_nanousd",
        "unknown_cost_attempts",
    }
)
OUTCOMES = frozenset(
    {"failed", "succeeded", "approval_wait", "retry_wait", "returned", "exception", "interrupted"}
)


def safe_attribute(field: str, value: object) -> str | int | bool | None:
    if field in {"run_id", "invocation_id"} and isinstance(value, str) and len(value) <= 36:
        try:
            return str(UUID(value))
        except ValueError:
            return None
    if field in NUMBER_FIELDS and type(value) is int and 0 <= value <= 2**63 - 1:
        return value
    if field == "usage_complete" and type(value) is bool:
        return value
    if field == "outcome" and isinstance(value, str) and value in OUTCOMES:
        return value
    return None


@contextmanager
def using_tracer(tracer: Tracer) -> Iterator[None]:
    """Application-owned scope; does not install a global OTel provider."""
    token = _tracer.set(tracer)
    try:
        yield
    finally:
        _tracer.reset(token)


class Observation:
    def __init__(self, span: Span | None) -> None:
        self.span = span

    def fields(self, **values: str | int | bool) -> None:
        if self.span is not None:
            try:
                attributes = {
                    f"runveil.{key}": safe
                    for key, value in values.items()
                    if (safe := safe_attribute(key, value)) is not None
                }
                self.span.set_attributes(attributes)
                if "runveil.outcome" in attributes:
                    self.span.set_status(
                        StatusCode.ERROR
                        if attributes["runveil.outcome"] in {"failed", "exception", "interrupted"}
                        else StatusCode.OK
                    )
            except Exception:
                pass


@contextmanager
def observe(
    name: Literal["agent.execute", "model.attempt", "tool.dispatch", "tool.apply_patch"],
    *,
    root: bool = False,
    **fields: str | int | bool,
) -> Iterator[Observation]:
    span = None
    tracer = _tracer.get()
    if tracer is not None:
        try:
            parent = _parent.get()
            context = set_span_in_context(parent, Context()) if parent and not root else Context()
            span = tracer.start_span(
                name, context=context, record_exception=False, set_status_on_exception=False
            )
        except Exception:
            pass
    observation = Observation(span)
    observation.fields(**fields)
    token = _parent.set(span)
    try:
        yield observation
    except BaseException as exc:
        observation.fields(
            outcome="interrupted" if isinstance(exc, asyncio.CancelledError) else "exception"
        )
        raise
    finally:
        _parent.reset(token)
        if span is not None:
            try:
                span.end()
            except Exception:
                pass
