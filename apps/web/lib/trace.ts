// Validate the fields we render; no unchecked server data enters the view.
export type Invocation = {
  id: string;
  kind: "model" | "tool";
  name: string;
  provider: string | null;
  model_invocation_id: string | null;
  status: string;
  requested_sequence: number;
  completed_sequence: number | null;
  requested_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  error_code: string | null;
};
export type TraceEvent = {
  sequence: number;
  kind: string;
  run_revision: number;
  step_number: number | null;
  created_at: string;
  retry_of: string | null;
  to_status: string | null;
  invocation: Invocation | null;
};
export type Trace = {
  schema_version: 1;
  run_id: string;
  agent_version_id: string;
  status: string;
  revision: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  observed_at: string;
  elapsed_ms: number | null;
  event_sequence: number;
  history_complete: boolean;
  model_calls: number;
  tool_calls: number;
  checkpoint: null | {
    event_sequence: number;
    schema_version: number | null;
    tokens: null | {
      attempts: number;
      input_tokens: number;
      output_tokens: number;
      unknown_attempts: number;
    };
    cost: null | { known_nanousd: number; unknown_attempts: number };
    retries_scheduled: number | null;
    error_code: string | null;
    final_summary: string | null;
    final_summary_truncated: boolean;
  };
  approval: null | {
    id: string;
    status: string;
    requested_at: string;
    decided_at: string | null;
  };
  events: TraceEvent[];
  next_after_sequence: number | null;
};
const record = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const integer = (v: unknown): v is number =>
  typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
const text = (v: unknown, max: number): v is string =>
  typeof v === "string" && v.length <= max;
const uuid = (v: unknown): v is string =>
  text(v, 36) && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(v);
const time = (v: unknown): v is string =>
  text(v, 40) && Number.isFinite(Date.parse(v));
const duration = (v: unknown) =>
  v === null || (typeof v === "number" && Number.isFinite(v) && v >= 0);
const status = (v: unknown) =>
  typeof v === "string" &&
  [
    "QUEUED",
    "RUNNING",
    "WAITING_FOR_APPROVAL",
    "RETRYING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
  ].includes(v);
const errorCode = (v: unknown) =>
  v === null || (text(v, 64) && /^[a-z][a-z0-9_]*$/.test(v));
const nullableInt = (v: unknown) => v === null || integer(v);
const nullableTime = (v: unknown) => v === null || time(v);
const nullableId = (v: unknown) => v === null || uuid(v);
function invocation(v: unknown, watermark: number, sequence: number): boolean {
  if (v === null) return true;
  if (
    !record(v) ||
    !uuid(v.id) ||
    !["model", "tool"].includes(String(v.kind)) ||
    !text(v.name, 200) ||
    !(v.provider === null || text(v.provider, 200)) ||
    !nullableId(v.model_invocation_id) ||
    !["REQUESTED", "SUCCEEDED", "FAILED"].includes(String(v.status)) ||
    !integer(v.requested_sequence) ||
    v.requested_sequence < 1 ||
    v.requested_sequence > watermark ||
    !nullableInt(v.completed_sequence) ||
    !time(v.requested_at) ||
    !nullableTime(v.completed_at) ||
    !duration(v.duration_ms) ||
    !errorCode(v.error_code)
  )
    return false;
  if (sequence !== v.requested_sequence && sequence !== v.completed_sequence)
    return false;
  if (v.status === "REQUESTED")
    return (
      v.completed_sequence === null &&
      v.completed_at === null &&
      v.duration_ms === null &&
      v.error_code === null
    );
  return (
    integer(v.completed_sequence) &&
    v.completed_sequence > v.requested_sequence &&
    v.completed_sequence <= watermark &&
    v.completed_at !== null &&
    v.duration_ms !== null &&
    (v.status === "FAILED" ? v.error_code !== null : v.error_code === null)
  );
}

export function trace(
  value: unknown,
  runId: string,
  after = 0,
  expected?: number,
): Trace {
  const bad = () => {
    throw Error("Invalid trace");
  };
  if (
    !record(value) ||
    value.schema_version !== 1 ||
    !uuid(value.run_id) ||
    value.run_id.toLowerCase() !== runId.toLowerCase() ||
    !uuid(value.agent_version_id) ||
    !status(value.status) ||
    !integer(value.revision) ||
    !time(value.created_at) ||
    !nullableTime(value.started_at) ||
    !nullableTime(value.finished_at) ||
    !time(value.observed_at) ||
    !duration(value.elapsed_ms) ||
    !integer(value.event_sequence) ||
    (expected !== undefined && value.event_sequence !== expected) ||
    typeof value.history_complete !== "boolean" ||
    !integer(value.model_calls) ||
    !integer(value.tool_calls) ||
    !nullableInt(value.next_after_sequence) ||
    !Array.isArray(value.events) ||
    value.events.length > 50
  )
    return bad();
  const c = value.checkpoint;
  if (c !== null) {
    if (
      !record(c) ||
      !integer(c.event_sequence) ||
      c.event_sequence > value.event_sequence ||
      !nullableInt(c.schema_version) ||
      !nullableInt(c.retries_scheduled) ||
      !errorCode(c.error_code) ||
      !(c.final_summary === null || text(c.final_summary, 8192)) ||
      typeof c.final_summary_truncated !== "boolean"
    )
      return bad();
    const t = c.tokens,
      cost = c.cost;
    if (
      t !== null &&
      (!record(t) ||
        !integer(t.attempts) ||
        !integer(t.input_tokens) ||
        !integer(t.output_tokens) ||
        !integer(t.unknown_attempts) ||
        t.unknown_attempts > t.attempts)
    )
      return bad();
    if (
      cost !== null &&
      (!record(cost) ||
        !integer(cost.known_nanousd) ||
        !integer(cost.unknown_attempts))
    )
      return bad();
  }
  const a = value.approval;
  if (
    a !== null &&
    (!record(a) ||
      !uuid(a.id) ||
      !["PENDING", "APPROVED", "REJECTED"].includes(String(a.status)) ||
      !time(a.requested_at) ||
      !nullableTime(a.decided_at))
  )
    return bad();
  let previous = after;
  for (const event of value.events) {
    if (
      !record(event) ||
      !integer(event.sequence) ||
      event.sequence !== previous + 1 ||
      event.sequence > value.event_sequence ||
      !text(event.kind, 100) ||
      !integer(event.run_revision) ||
      !nullableInt(event.step_number) ||
      !time(event.created_at) ||
      !nullableId(event.retry_of) ||
      !(event.to_status === null || status(event.to_status)) ||
      !invocation(event.invocation, value.event_sequence, event.sequence)
    )
      return bad();
    previous = event.sequence;
  }
  if (
    value.next_after_sequence !==
      (previous < value.event_sequence ? previous : null) ||
    (previous < value.event_sequence && value.events.length === 0) ||
    after > value.event_sequence
  )
    return bad();
  return value as Trace;
}

export function usd(nanousd: number): string {
  const digits = nanousd.toString().padStart(10, "0");
  return `$${digits.slice(0, -9)}.${digits.slice(-9)}`;
}
export function elapsed(ms: number | null): string {
  return ms === null ? "Not recorded" : `${(ms / 1000).toFixed(3)} s`;
}
