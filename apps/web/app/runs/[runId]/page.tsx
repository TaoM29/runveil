import Link from "next/link";
import { notFound } from "next/navigation";
import ConsoleShell from "../../components/console-shell";
import { Diff, Status, TestOutput } from "../../components/evidence";
import { recordedTime, showcaseRuns } from "../../../lib/showcase";

export const metadata = { title: "Execution record | Runveil" };
export function generateStaticParams() {
  return showcaseRuns.map((run) => ({ runId: run.id }));
}

const stages: Record<string, { title: string; description: string }> = {
  "repository.inspect": {
    title: "Inspect repository",
    description: "Captured the complete three-file sandbox snapshot.",
  },
  "repository.search": {
    title: "Search snapshot",
    description: "Located literal matches in the inspected source.",
  },
  "tests.run": {
    title: "Reproduce failure",
    description: "Recorded the failing baseline before proposing a change.",
  },
  "repository.propose_patch": {
    title: "Propose exact patch",
    description: "Recorded before/after content for human review.",
  },
  "repository.apply_patch": {
    title: "Apply and validate",
    description:
      "Revalidated the workspace, applied the approved change and ran tests.",
  },
};

export default async function RunPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  const run = showcaseRuns.find((item) => item.id === runId);
  if (!run) notFound();
  return (
    <ConsoleShell active="Recorded runs">
      <Link className="back-link" href="/runs">
        Back to recorded runs
      </Link>
      <div className="page-heading run-heading">
        <div>
          <p className="section-label">{run.fixture} / execution record</p>
          <h1>{run.title}</h1>
          <p className="lede">{run.description}</p>
          <p className="mono muted small">{run.id}</p>
        </div>
        <Status value={run.outcome} />
      </div>
      <div className="evidence-notice">
        <strong>Recorded, read-only</strong>
        <span>
          {run.faultInjection
            ? "Fault injection: an ineffective repair was deliberately approved to verify failure inspection."
            : "A public scripted-fixture run retained from Phase 10G acceptance."}{" "}
          No actions on this page change a run.
        </span>
      </div>
      <nav className="section-nav" aria-label="Run sections">
        <a href="#execution">Execution</a>
        <a href="#proposal">Proposal & decision</a>
        <a href="#tests">Test outcomes</a>
        <a href="#provenance">Provenance</a>
      </nav>
      <div className="run-layout">
        <aside className="execution-rail" id="execution">
          <h2>Execution path</h2>
          <p className="small muted">Persisted tool calls, in order.</p>
          <ol>
            {run.tools.map((tool) => (
              <li key={tool.id}>
                <div className="rail-step">
                  <span className="rail-marker" aria-hidden="true">
                    ✓
                  </span>
                  <div>
                    <h3>{stages[tool.name]?.title ?? tool.name}</h3>
                    <p>{stages[tool.name]?.description}</p>
                    <span className="small muted">
                      Events {tool.requested_sequence} /{" "}
                      {tool.completed_sequence ?? "unresolved"}
                    </span>
                  </div>
                </div>
                {tool.name === "repository.propose_patch" && (
                  <div className="rail-decision">
                    <strong>Approval decision</strong>
                    <Status value={run.approval.status} />
                    <p>
                      {run.approval.decided_at
                        ? recordedTime(run.approval.decided_at)
                        : "Not recorded"}
                    </p>
                  </div>
                )}
              </li>
            ))}
          </ol>
          <p className="small muted">
            A completed tool call is not a passing test. Test outcomes are shown
            separately.
          </p>
          {!run.applied && (
            <p className="rail-stop">
              Stopped before mutation. No post-change tests were run.
            </p>
          )}
        </aside>
        <div className="run-evidence">
          <section className="result-banner">
            <div>
              <p className="section-label">Observed outcome</p>
              <h2>
                {run.applied
                  ? run.validation?.status === "passed"
                    ? "Approved change. Passing tests."
                    : "Patch applied. Validation failed."
                  : "Proposal rejected. No mutation."}
              </h2>
              <p>
                {run.applied
                  ? "The durable mutation record confirms application in the disposable sandbox."
                  : "The recorded approval decision terminated this workflow before application."}
              </p>
            </div>
            {run.errorCode && <code>{run.errorCode}</code>}
          </section>
          <section className="panel" id="proposal">
            <div className="section-heading">
              <div>
                <p className="section-label">Exact change</p>
                <h2>Proposal & decision</h2>
              </div>
              <Status value={run.approval.status} />
            </div>
            <div className="file-heading">
              <span className="mono">{run.approval.proposal.path}</span>
              <span className="small muted">Unified diff</span>
            </div>
            <Diff value={run.diff} />
            <div className="panel-body">
              <p>
                Approval covered this exact replacement and fixed tests in a
                disposable sandbox. Application still required a separately
                authorized worker with WRITE and EXECUTE permissions.
              </p>
              <details>
                <summary>Inspect complete before / after text</summary>
                <div className="source-pair">
                  {(["before", "after"] as const).map((part) => (
                    <section key={part}>
                      <h3>{part === "before" ? "Before" : "After"}</h3>
                      <pre tabIndex={0}>{run.approval.proposal[part]}</pre>
                    </section>
                  ))}
                </div>
                <details>
                  <summary>
                    Exact escaped proposal, including whitespace
                  </summary>
                  <pre tabIndex={0}>
                    {JSON.stringify(run.approval.proposal, null, 2).replace(
                      /[\u007f-\uffff]/g,
                      (c) =>
                        `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`,
                    )}
                  </pre>
                </details>
              </details>
            </div>
          </section>
          {run.search && (
            <section className="panel">
              <div className="section-heading">
                <div>
                  <p className="section-label">Before the proposal</p>
                  <h2>Search evidence</h2>
                </div>
                <code>{run.search.query}</code>
              </div>
              <p className="panel-description">
                Literal query across {run.search.filesScanned} files in the
                original snapshot. {run.search.matches.length} recorded matches
                {run.search.truncated
                  ? "; result truncated"
                  : "; no truncation"}
                .
              </p>
              <ul className="search-matches">
                {run.search.matches.map((match, index) => (
                  <li key={index}>
                    <span className="mono small">
                      {match.path}:{match.line}
                    </span>
                    <pre>{match.excerpt}</pre>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <section className="panel" id="tests">
            <div className="section-heading">
              <div>
                <p className="section-label">Validation evidence</p>
                <h2>Test outcomes</h2>
              </div>
            </div>
            <div className="panel-body">
              <TestOutput title="Baseline" result={run.baseline} />
              <TestOutput title="After the patch" result={run.validation} />
              {run.cleanup !== null && (
                <p className="small muted">
                  Mutation container cleanup:{" "}
                  {run.cleanup ? "confirmed" : "not confirmed"}.
                </p>
              )}
            </div>
          </section>
          <section className="panel" id="provenance">
            <div className="section-heading">
              <div>
                <p className="section-label">Identity & source</p>
                <h2>Provenance</h2>
              </div>
            </div>
            <dl className="identity-list">
              {[
                ["Profile", run.profile],
                ["Run status / revision", `${run.status} / ${run.revision}`],
                ["Review requested", recordedTime(run.approval.requested_at)],
                [
                  "Decision recorded",
                  run.approval.decided_at
                    ? recordedTime(run.approval.decided_at)
                    : "Not recorded",
                ],
                ["Approval ID", run.approval.id],
                ["Proposal digest", run.approval.digest],
                ["Original snapshot digest", run.inspectionDigest],
                [
                  "Postimage digest",
                  run.postimageDigest ?? "No mutation recorded",
                ],
                ["Image", run.image],
                ["Implementation digest", run.implementationDigest],
                ["Committed evidence file", run.source],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <p className="panel-description">
              This view uses selected fields from the committed public fixture
              record. It is not a live trace or a model-quality benchmark. The
              archive does not include full model messages or token/cost
              accounting.
            </p>
          </section>
        </div>
      </div>
    </ConsoleShell>
  );
}
