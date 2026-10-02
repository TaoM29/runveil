import evidence from "../../../docs/operations/evidence/phase10g/tasks.json";
import failedValidation from "../../../docs/operations/evidence/phase10f/failed-validation.json";

type ToolRecord = {
  id: string;
  name: string;
  status: string;
  requested_sequence: number;
  completed_sequence: number | null;
  result: unknown;
  request?: unknown;
};
type TestResult = {
  status: string;
  exit_code: number | null;
  output: string;
  output_truncated: boolean;
};
type EvidenceRecord = {
  run_id: string;
  profile: string;
  status: string;
  revision: number;
  error_code: string | null;
  patch_applied: boolean | null;
  diff: string;
  inspection_digest: string;
  sandbox: { fixture: string; image: string; implementation_digest: string };
  approval: {
    id: string;
    status: string;
    digest: string;
    requested_at: string;
    decided_at: string | null;
    proposal: { path: string; before: string; after: string };
  };
  mutation: {
    result: {
      tests: TestResult;
      after_digest: string;
      cleanup_confirmed: boolean;
    };
  } | null;
  tools: ToolRecord[];
};

const tasks: Record<string, { title: string; description: string }> = {
  "clamp-v1": {
    title: "Repair integer bounds",
    description: "Keep values inside the inclusive lower and upper limits.",
  },
  "slug-v1": {
    title: "Normalize whitespace",
    description: "Build a lowercase slug with one separator between words.",
  },
  "mean-v1": {
    title: "Preserve fractional means",
    description: "Return the arithmetic mean without rounding down.",
  },
};
function object(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
function baseline(tools: ToolRecord[]): TestResult | null {
  const result = object(
    tools.find((tool) => tool.name === "tests.run")?.result,
  );
  if (
    typeof result.status !== "string" ||
    typeof result.output !== "string" ||
    typeof result.output_truncated !== "boolean" ||
    !(result.exit_code === null || typeof result.exit_code === "number")
  )
    return null;
  return {
    status: result.status,
    output: result.output,
    output_truncated: result.output_truncated,
    exit_code: result.exit_code,
  };
}
function search(tools: ToolRecord[]) {
  const tool = tools.find((item) => item.name === "repository.search");
  const result = object(tool?.result);
  const query = object(tool?.request).query;
  if (
    typeof query !== "string" ||
    !Array.isArray(result.matches) ||
    typeof result.truncated !== "boolean" ||
    typeof result.files_scanned !== "number"
  )
    return null;
  const matches = result.matches.map((value: unknown) => {
    const match = object(value);
    if (
      typeof match.path !== "string" ||
      typeof match.line !== "number" ||
      typeof match.excerpt !== "string"
    )
      throw Error("Invalid committed search evidence");
    return { path: match.path, line: match.line, excerpt: match.excerpt };
  });
  return {
    query,
    matches,
    truncated: result.truncated,
    filesScanned: result.files_scanned,
  };
}
function present(record: EvidenceRecord, faultInjection = false) {
  const task = tasks[record.sandbox.fixture];
  if (!task) throw Error("Unknown showcase fixture");
  const outcome =
    record.approval.status === "REJECTED"
      ? "Rejected"
      : record.status === "SUCCEEDED"
        ? "Passed"
        : "Validation failed";
  return {
    id: record.run_id,
    ...task,
    outcome,
    faultInjection,
    fixture: record.sandbox.fixture,
    profile: record.profile,
    status: record.status,
    revision: record.revision,
    errorCode: record.error_code,
    applied: record.patch_applied,
    diff: record.diff,
    approval: record.approval,
    image: record.sandbox.image,
    implementationDigest: record.sandbox.implementation_digest,
    inspectionDigest: record.inspection_digest,
    postimageDigest: record.mutation?.result.after_digest ?? null,
    cleanup: record.mutation?.result.cleanup_confirmed ?? null,
    baseline: baseline(record.tools),
    validation: record.mutation?.result.tests ?? null,
    search: search(record.tools),
    tools: record.tools.map(
      ({ id, name, status, requested_sequence, completed_sequence }) => ({
        id,
        name,
        status,
        requested_sequence,
        completed_sequence,
      }),
    ),
    source: faultInjection
      ? "docs/operations/evidence/phase10f/failed-validation.json"
      : "docs/operations/evidence/phase10g/tasks.json",
  };
}
// Only these reviewed public fixture artifacts enter the showcase. No database or live trace payloads.
export const showcaseRuns = [
  ...evidence.runs.map((run) => present(run.final)),
  present(failedValidation.final, true),
];
export type ShowcaseRun = (typeof showcaseRuns)[number];
export const featuredRun = showcaseRuns[0];
export function recordedTime(value: string): string {
  return (
    new Date(value).toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZone: "UTC",
    }) + " UTC"
  );
}
