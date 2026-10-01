export type Profile =
  "patch-review-v1" | "repository-review-v1" | "repository-patch-v1";
export type Inspection = {
  profile: Profile;
  run_status: string;
  run_revision: number;
  request: {
    id: string;
    run_id: string;
    digest: string;
    status: "PENDING" | "APPROVED" | "REJECTED";
    proposal: {
      schema_version: 1;
      path: string;
      before: string;
      after: string;
    };
  };
  workspace: null | {
    root_digest: string;
    content_digest: string;
    implementation_digest: string;
  };
  mutation: null | { status: string; error_code: string | null };
};
export const consequences: Record<Profile, string> = {
  "patch-review-v1":
    "Approval completes this standalone review. It cannot write a file.",
  "repository-review-v1":
    "Approval permits the review worker to continue. It cannot write a file.",
  "repository-patch-v1":
    "Approval permits this exact file replacement. A separately started worker still needs an explicit write grant and a matching workspace. This screen does not start it.",
};
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const digest = (value: unknown): value is string =>
  typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
const uuid = (value: unknown): value is string =>
  typeof value === "string" &&
  /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value);

// Refuse malformed/foreign inspection data before enabling decisions. The API remains authoritative.
export function inspection(value: unknown, runId: string): Inspection {
  if (
    !record(value) ||
    !record(value.request) ||
    !record(value.request.proposal)
  )
    throw Error("Invalid inspection");
  const r = value.request,
    p = r.proposal as Record<string, unknown>,
    w = value.workspace,
    m = value.mutation;
  if (
    typeof value.profile !== "string" ||
    !Object.hasOwn(consequences, value.profile) ||
    ![
      "QUEUED",
      "RUNNING",
      "WAITING_FOR_APPROVAL",
      "RETRYING",
      "SUCCEEDED",
      "FAILED",
      "CANCELLED",
    ].includes(String(value.run_status)) ||
    !Number.isSafeInteger(value.run_revision) ||
    Number(value.run_revision) < 0 ||
    !uuid(r.id) ||
    !uuid(r.run_id) ||
    r.run_id.toLowerCase() !== runId.toLowerCase() ||
    !digest(r.digest) ||
    !["PENDING", "APPROVED", "REJECTED"].includes(String(r.status)) ||
    p.schema_version !== 1 ||
    typeof p.path !== "string" ||
    p.path.length > 240 ||
    typeof p.before !== "string" ||
    typeof p.after !== "string" ||
    p.before.length > 32768 ||
    p.after.length > 32768 ||
    !(
      w === null ||
      (record(w) &&
        digest(w.root_digest) &&
        digest(w.content_digest) &&
        digest(w.implementation_digest))
    ) ||
    (value.profile === "patch-review-v1") !== (w === null) ||
    !(
      m === null ||
      (record(m) &&
        ["REQUESTED", "SUCCEEDED", "FAILED"].includes(String(m.status)) &&
        (m.error_code === null || typeof m.error_code === "string"))
    )
  )
    throw Error("Invalid inspection");
  return value as Inspection;
}
