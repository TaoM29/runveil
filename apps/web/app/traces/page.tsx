import ConsoleShell from "../components/console-shell";
import TraceConsole from "./trace-console";
export const metadata = { title: "Live trace | Runveil" };
export default function Traces() {
  return (
    <ConsoleShell active="Live trace" operator>
      <div className="page-heading">
        <div>
          <p className="section-label">Local operator / read-only inspection</p>
          <h1>Runveil traces</h1>
          <p className="lede">
            Read the durable execution history of an existing run.
          </p>
        </div>
      </div>
      <div className="evidence-notice">
        <strong>Authenticated snapshot</strong>
        <span>
          Refresh manually for progress. Raw proposals and tool output remain
          outside this trace API; use the recorded runs to explore public Phase
          10 evidence.
        </span>
      </div>
      <TraceConsole />
    </ConsoleShell>
  );
}
