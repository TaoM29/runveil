import type { ShowcaseRun } from "../../lib/showcase";
import { Status } from "./evidence";

export default function RunTable({ runs }: { runs: ShowcaseRun[] }) {
  return (
    <div
      className="table-scroll"
      tabIndex={0}
      role="region"
      aria-label="Recorded runs, scroll horizontally if needed"
    >
      <p className="table-hint">
        Scroll horizontally for approval and test results.
      </p>
      <table className="run-table">
        <caption className="sr-only">
          Recorded coding tasks and their observed outcomes
        </caption>
        <thead>
          <tr>
            <th scope="col">Task / run</th>
            <th scope="col">Outcome</th>
            <th scope="col">Approval</th>
            <th scope="col">Post-change tests</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <th scope="row">
                <a className="run-link" href={`/runs/${run.id}`}>
                  {run.title}
                </a>
                <span className="run-subtitle">
                  {run.fixture} · {run.id.slice(0, 8)}
                  {run.faultInjection ? " · Fault injection" : ""}
                </span>
              </th>
              <td>
                <Status value={run.outcome} />
              </td>
              <td>
                {run.approval.status === "APPROVED" ? "Approved" : "Rejected"}
              </td>
              <td>
                {run.validation ? (
                  <Status value={run.validation.status} />
                ) : (
                  <span className="muted">Not run</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
