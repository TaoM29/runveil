"""Telemetry correlates with durable evidence and stays outside retry/authority decisions."""

import asyncio
import io
import json
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Span, Tracer
from runveil_core.telemetry import using_tracer
from runveil_persistence.invocations import InvocationRepository
from runveil_persistence.traces import read_trace
from runveil_worker.telemetry import JsonSpanExporter, provider
from runveil_worker.worker import CALLS_PROFILE, COST_PROFILE, submit, work_once
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from test_retries import Clock
from test_retries import clock as clock

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_retry_spans_correlate_with_persisted_intents_and_accounting(
    database: AsyncEngine,
    clock: Clock,
) -> None:
    sessions = async_sessionmaker(database)
    run_id = await submit(sessions, profile=COST_PROFILE)
    clock.at = datetime.now(UTC)
    output = InMemorySpanExporter()
    sdk = TracerProvider(shutdown_on_exit=False)
    sdk.add_span_processor(SimpleSpanProcessor(output))
    try:
        with using_tracer(sdk.get_tracer("runveil.runtime")):
            for delay in (1, 2, 0):
                outcome = await work_once(sessions, run_id=run_id, profile=COST_PROFILE)
                assert outcome is not None
                clock.advance(delay)
        spans = output.get_finished_spans()
        roots = [s for s in spans if s.name == "agent.execute"]
        assert len(roots) == 3 and all(s.parent is None for s in roots)
        assert [s.attributes["runveil.outcome"] for s in roots if s.attributes] == [
            "retry_wait",
            "retry_wait",
            "succeeded",
        ]
        async with sessions.begin() as session:
            trace = await read_trace(session, run_id)
            assert trace.checkpoint is not None and trace.checkpoint.cost is not None
            assert roots[-1].attributes is not None
            assert (
                roots[-1].attributes["runveil.known_nanousd"] == trace.checkpoint.cost.known_nanousd
            )
            calls = [s for s in spans if s.name != "agent.execute"]
            assert len(calls) == trace.model_calls + trace.tool_calls == 5
            for span in calls:
                assert span.attributes is not None
                identity = UUID(str(span.attributes["runveil.invocation_id"]))
                repo = InvocationRepository(session)
                call = (
                    await repo.get_model(run_id, identity)
                    if span.name == "model.attempt"
                    else await repo.get_tool(run_id, identity)
                )
                assert span.attributes["runveil.request_sequence"] == call.requested_event_sequence
                assert span.attributes["runveil.run_id"] == str(run_id)
        stream = io.StringIO()
        exporter = JsonSpanExporter(stream)
        assert exporter.export(spans) == SpanExportResult.SUCCESS
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        assert len(records) == 8 and all(
            len(line) <= 4096 for line in stream.getvalue().splitlines()
        )
        assert all(not span.events for span in spans)
        assert "fixture" not in stream.getvalue() and "messages" not in stream.getvalue()
        assert all(
            set(record)
            == {
                "event",
                "service",
                "name",
                "trace_id",
                "span_id",
                "parent_span_id",
                "start_ns",
                "end_ns",
                "attributes",
            }
            for record in records
        )
        # Even SDK spans containing accidental payload/exception fields cannot leak them.
        with sdk.get_tracer("runveil.runtime").start_as_current_span("agent.execute") as raw:
            raw.set_attribute("task", "private-sentinel")
            raw.set_attribute("runveil.outcome", "private-sentinel")
            raw.record_exception(ValueError("private-sentinel"))
        safe = io.StringIO()
        assert (
            JsonSpanExporter(safe).export(output.get_finished_spans()[-1:])
            == SpanExportResult.SUCCESS
        )
        assert "private-sentinel" not in safe.getvalue()
    finally:
        sdk.shutdown()


async def test_broken_span_and_output_do_not_change_execution(database: AsyncEngine) -> None:
    sessions = async_sessionmaker(database)
    broken = Mock(spec=Tracer)
    span = Mock(spec=Span)
    span.set_attributes.side_effect = RuntimeError("private-sentinel")
    span.end.side_effect = RuntimeError("private-sentinel")
    broken.start_span.return_value = span
    first = await submit(sessions, profile=CALLS_PROFILE)
    with using_tracer(broken):
        outcome = await work_once(sessions, run_id=first, profile=CALLS_PROFILE)
    assert outcome is not None and outcome[1].final_result is not None

    class BrokenOutput(io.StringIO):
        def write(self, value: str) -> int:
            raise OSError("private-output-sentinel")

    sdk = provider(BrokenOutput())
    try:
        second = await submit(sessions, profile=CALLS_PROFILE)
        with using_tracer(sdk.get_tracer("runveil.runtime")):
            other = await work_once(sessions, run_id=second, profile=CALLS_PROFILE)
        assert other is not None and other[1] == outcome[1]
        # Join/drain outside execution; exporter catches the sink error itself.
        await asyncio.to_thread(sdk.shutdown)
        async with sessions.begin() as session:
            for run_id in (first, second):
                trace = await read_trace(session, run_id)
                assert (
                    trace.status == "SUCCEEDED" and trace.model_calls == 2 and trace.tool_calls == 1
                )
    finally:
        sdk.shutdown()
