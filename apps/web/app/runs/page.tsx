import ConsoleShell from "../components/console-shell";
import RunList from "./run-list";
import { showcaseRuns } from "../../lib/showcase";

export const metadata = { title: "Recorded runs | Runveil" };
export default function Runs() {
  return (
    <ConsoleShell active="Recorded runs">
      <div className="page-heading">
        <div>
          <p className="section-label">Execution archive</p>
          <h1>Recorded runs</h1>
          <p className="lede">
            Seven retained runs. Every outcome has evidence.
          </p>
        </div>
      </div>
      <div className="evidence-notice">
        <strong>Read-only archive</strong>
        <span>
          Six Phase 10G acceptance runs and one Phase 10F fault-injection run.
          This is not a live run listing.
        </span>
      </div>
      <RunList runs={showcaseRuns} />
    </ConsoleShell>
  );
}
