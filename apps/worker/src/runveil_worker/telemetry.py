"""Local, bounded JSON span output; no network exporters or payload logging."""

import json
import os
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import TextIO
from uuid import UUID

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanLimits, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from runveil_core.telemetry import using_tracer

NAMES = {"agent.execute", "model.attempt", "tool.dispatch", "tool.apply_patch"}
NUMBERS = {
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
OUTCOMES = {
    "failed",
    "succeeded",
    "approval_wait",
    "retry_wait",
    "returned",
    "exception",
    "interrupted",
}


class JsonSpanExporter(SpanExporter):
    """Select safe attributes again at export; never serialize SDK exceptions/resources."""

    def __init__(self, stream: TextIO) -> None:
        self.stream = stream

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            for span in spans:
                if span.name not in NAMES or span.context is None:
                    continue
                attributes: dict[str, str | int | bool] = {}
                for key, value in (span.attributes or {}).items():
                    if not key.startswith("runveil."):
                        continue
                    field = key.removeprefix("runveil.")
                    if field in {"run_id", "invocation_id"} and isinstance(value, str):
                        attributes[field] = str(UUID(value))
                    elif field in NUMBERS and type(value) is int and 0 <= value <= 2**63 - 1:
                        attributes[field] = value
                    elif field == "usage_complete" and type(value) is bool:
                        attributes[field] = value
                    elif field == "outcome" and isinstance(value, str) and value in OUTCOMES:
                        attributes[field] = value
                line = json.dumps(
                    {
                        "event": "execution.span",
                        "service": "runveil-worker",
                        "name": span.name,
                        "trace_id": format(span.context.trace_id, "032x"),
                        "span_id": format(span.context.span_id, "016x"),
                        "parent_span_id": format(span.parent.span_id, "016x")
                        if span.parent
                        else None,
                        "start_ns": span.start_time,
                        "end_ns": span.end_time,
                        "attributes": attributes,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
                if len(line.encode("utf-8")) > 4096:
                    return SpanExportResult.FAILURE
                self.stream.write(line + "\n")
            self.stream.flush()
            return SpanExportResult.SUCCESS
        except Exception:
            # Including BrokenPipeError: no exception content may reach stderr/logging.
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        # Stream ownership belongs to the caller; never close stderr.
        pass


def provider(stream: TextIO) -> TracerProvider:
    result = TracerProvider(
        resource=Resource({"service.name": "runveil-worker"}),
        sampler=ALWAYS_ON,
        shutdown_on_exit=False,
        span_limits=SpanLimits(
            max_attributes=16, max_events=0, max_links=0, max_attribute_length=64
        ),
    )
    result.add_span_processor(
        BatchSpanProcessor(
            JsonSpanExporter(stream),
            max_queue_size=256,
            max_export_batch_size=32,
            schedule_delay_millis=1000,
            export_timeout_millis=1000,
        )
    )
    return result


@contextmanager
def telemetry() -> Iterator[None]:
    """CLI scope only. Library callers opt in explicitly with using_tracer instead."""
    configured = None
    tracer = None
    if os.environ.get("RUNVEIL_TELEMETRY") == "json":
        try:
            configured = provider(sys.stderr)
            tracer = configured.get_tracer("runveil.runtime")
        except Exception:
            pass
    try:
        if tracer is None:
            yield
        else:
            with using_tracer(tracer):
                yield
    finally:
        if configured is not None:
            try:
                # Only after execution/DB cleanup; SDK's bounded join may take up to 30s.
                configured.shutdown()
            except Exception:
                pass
