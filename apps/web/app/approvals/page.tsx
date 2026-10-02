import ConsoleShell from "../components/console-shell";
import ApprovalConsole from "../approval-console";
export const metadata = { title: "Local approvals | Runveil" };
export default function Approvals() {
  return (
    <ConsoleShell active="Local approvals" operator>
      <div className="page-heading">
        <div>
          <p className="section-label">Local operator / decision surface</p>
          <h1>Runveil approvals</h1>
          <p className="lede">
            Inspect the exact proposal before authorizing a change.
          </p>
        </div>
      </div>
      <div className="evidence-notice">
        <strong>Separate authority</strong>
        <span>
          This console supports the existing Phase 6 review and host-patch
          profiles. Phase 10 sandbox decisions remain in the local worker CLI.
        </span>
      </div>
      <ApprovalConsole />
    </ConsoleShell>
  );
}
