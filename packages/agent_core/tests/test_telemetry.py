"""Best-effort span lifetimes never swallow application exceptions or expose content."""

import asyncio
from unittest.mock import Mock
from uuid import uuid4

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Span, Tracer
from runveil_core.telemetry import observe, using_tracer


@pytest.mark.asyncio
async def test_concurrent_roots_and_cancellation_do_not_capture_exception_text() -> None:
    output = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(output))
    tracer = provider.get_tracer("test")
    failure = asyncio.CancelledError("private-exception-sentinel")

    async def operation(cancel: bool) -> None:
        with observe("agent.execute", root=True, run_id=str(uuid4())):
            await asyncio.sleep(0)
            with observe("model.attempt"):
                if cancel:
                    raise failure

    try:
        with using_tracer(tracer):
            results = await asyncio.gather(
                operation(False), operation(True), return_exceptions=True
            )
        assert results[0] is None and isinstance(results[1], asyncio.CancelledError)
        spans = output.get_finished_spans()
        roots = [s for s in spans if s.name == "agent.execute"]
        assert len(roots) == 2 and all(s.parent is None for s in roots)
        assert len({s.context.trace_id for s in roots if s.context}) == 2
        for child in (s for s in spans if s.name == "model.attempt"):
            assert child.context is not None and child.parent is not None
            root = next(
                s for s in roots if s.context and s.context.trace_id == child.context.trace_id
            )
            assert root.context is not None and child.parent.span_id == root.context.span_id
        assert all(not s.events for s in spans)
        assert "private-exception-sentinel" not in repr(spans)
        # Default scope is disabled again; no accidental process-global instrumentation.
        with observe("agent.execute", root=True):
            pass
        assert len(output.get_finished_spans()) == 4
    finally:
        provider.shutdown()


def test_broken_instrumentation_preserves_original_exception() -> None:
    tracer = Mock(spec=Tracer)
    span = Mock(spec=Span)
    span.set_attributes.side_effect = RuntimeError("private telemetry failure")
    span.end.side_effect = RuntimeError("private telemetry failure")
    tracer.start_span.return_value = span
    original = ValueError("private application failure")
    with using_tracer(tracer):
        with pytest.raises(ValueError) as caught:
            with observe("agent.execute", root=True) as observation:
                observation.fields(outcome="succeeded")
                raise original
        assert caught.value is original
        tracer.start_span.side_effect = RuntimeError("private start failure")
        with observe("agent.execute", root=True) as observation:
            observation.fields(outcome="succeeded")


def test_attributes_are_filtered_before_reaching_a_custom_tracer() -> None:
    output = InMemorySpanExporter()
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(output))
    run_id = str(uuid4())
    try:
        with using_tracer(provider.get_tracer("test")):
            with observe(
                "agent.execute", root=True, run_id=run_id, prompt="private-prompt-sentinel"
            ) as observation:
                observation.fields(
                    invocation_id="private-token-sentinel",
                    outcome="private-outcome-sentinel",
                    input_tokens=True,
                    output_tokens=-1,
                    known_nanousd=2**63,
                    usage_complete="private-usage-sentinel",
                )
                observation.fields(steps=3, usage_complete=False, outcome="succeeded")
        spans = output.get_finished_spans()
        assert len(spans) == 1
        assert dict(spans[0].attributes or {}) == {
            "runveil.run_id": run_id,
            "runveil.steps": 3,
            "runveil.usage_complete": False,
            "runveil.outcome": "succeeded",
        }
        assert not spans[0].events
    finally:
        provider.shutdown()
