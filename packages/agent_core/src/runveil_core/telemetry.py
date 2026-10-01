"""Opt-in, payload-free observations; never part of an execution decision."""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal

from opentelemetry.context import Context
from opentelemetry.trace import Span, StatusCode, Tracer, set_span_in_context

_tracer: ContextVar[Tracer | None] = ContextVar("runveil_tracer", default=None)
_parent: ContextVar[Span | None] = ContextVar("runveil_span", default=None)


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
                self.span.set_attributes({f"runveil.{key}": value for key, value in values.items()})
                if "outcome" in values:
                    self.span.set_status(
                        StatusCode.ERROR
                        if values["outcome"] in {"failed", "exception", "interrupted"}
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
