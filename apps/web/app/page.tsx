import Link from "next/link";
import ConsoleShell from "./components/console-shell";
import { Diff, Status } from "./components/evidence";
import RunTable from "./components/run-table";
import { featuredRun, showcaseRuns } from "../lib/showcase";

export default function Home() {
  return (
    <ConsoleShell active="Overview">
      <div className="page-heading">
        <div>
          <p className="section-label">Software engineering / Phase 10</p>
          <h1>Every change has a record.</h1>
          <p className="lede">
            Follow a coding task from failing tests to an exact, approved patch.
            <br className="desktop-break" /> Inspect the evidence at every step.
          </p>
        </div>
        <a className="button primary" href={`/runs/${featuredRun.id}`}>
          Inspect a complete run
        </a>
      </div>
      <div className="evidence-notice">
        <strong>Recorded evidence</strong>
        <span>
          Real acceptance runs from 02 Oct 2026. Public fixtures and a scripted
          provider, presented read-only.
        </span>
      </div>
      <section className="overview-summary" aria-label="Acceptance outcomes">
        <div>
          <strong>{showcaseRuns.length}</strong>
          <span>recorded runs</span>
        </div>
        <div>
          <strong>
            {showcaseRuns.filter((run) => run.outcome === "Passed").length}
          </strong>
          <span>validated repairs</span>
        </div>
        <div>
          <strong>
            {showcaseRuns.filter((run) => run.outcome === "Rejected").length}
          </strong>
          <span>rejected before mutation</span>
        </div>
        <div>
          <strong>
            {showcaseRuns.filter((run) => run.faultInjection).length}
          </strong>
          <span>validation failure probe</span>
        </div>
      </section>
      <section className="feature-run" aria-labelledby="featured-title">
        <div className="feature-story">
          <p className="section-label">A complete execution</p>
          <h2 id="featured-title">
            A missing lower bound.
            <br />A reviewable repair.
          </h2>
          <p>
            {featuredRun.description} The original implementation let negative
            values through. A recorded search located the return statement; the
            baseline test reproduced the failure.
          </p>
          <ol className="story-steps">
            <li>
              <span>01</span>
              <div>
                <strong>Inspect and reproduce</strong>
                <p>
                  Read the sandbox snapshot, search the source, run the fixed
                  tests.
                </p>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <strong>Pause for a decision</strong>
                <p>
                  Bind approval to the exact before/after text and proposal
                  digest.
                </p>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <strong>Apply and verify</strong>
                <p>
                  Revalidate the workspace, apply with WRITE permission, test
                  again.
                </p>
              </div>
            </li>
          </ol>
          <a className="text-link" href={`/runs/${featuredRun.id}`}>
            Follow the execution record
          </a>
        </div>
        <div className="feature-evidence">
          <div className="file-heading">
            <span className="mono">{featuredRun.approval.proposal.path}</span>
            <Status value={featuredRun.outcome} />
          </div>
          <Diff value={featuredRun.diff} />
          <div className="test-transition">
            <div>
              <span className="small muted">Before the patch</span>
              <strong>Baseline failed</strong>
              <code>AssertionError: -3 != 0</code>
            </div>
            <div>
              <span className="small muted">After approved application</span>
              <strong>Tests passed</strong>
              <code>Exit code {featuredRun.validation?.exit_code}</code>
            </div>
          </div>
          <p className="evidence-caption">
            Exact diff and results from run{" "}
            <span className="mono">{featuredRun.id.slice(0, 8)}</span>. No patch
            is applied by this page.
          </p>
        </div>
      </section>
      <section className="section-block">
        <div className="section-heading">
          <div>
            <h2>Recorded runs</h2>
            <p className="muted">
              Success, rejection and failed validation remain inspectable.
            </p>
          </div>
          <Link className="text-link" href="/runs">
            Browse all {showcaseRuns.length} runs
          </Link>
        </div>
        <RunTable
          runs={showcaseRuns.filter((run) => run.outcome !== "Rejected")}
        />
      </section>
      <section className="scope-note">
        <h2>Bounded by design</h2>
        <p>
          These runs demonstrate workflow mechanics across three project-owned
          coding tasks. Execution uses disposable Docker sandboxes. They do not
          measure general coding ability or authorize changes to a host
          repository.
        </p>
        <a className="text-link" href="/traces">
          Inspect a local run with a trace token
        </a>
      </section>
    </ConsoleShell>
  );
}
