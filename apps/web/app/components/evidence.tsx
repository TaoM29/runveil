export function Status({ value }: { value: string }) {
  const tone = ["Passed", "SUCCEEDED", "APPROVED", "passed"].includes(value)
    ? "success"
    : ["Validation failed", "FAILED", "tests_failed"].includes(value)
      ? "danger"
      : ["Rejected", "REJECTED", "PENDING", "WAITING_FOR_APPROVAL"].includes(
            value,
          )
        ? "warning"
        : "neutral";
  return (
    <span className={`status status-${tone}`}>
      {value.replaceAll("_", " ").toLowerCase()}
    </span>
  );
}
export function Diff({ value }: { value: string }) {
  const lines = value.split("\n");
  return (
    <pre className="diff-code" tabIndex={0} aria-label="Recorded unified diff">
      {lines.map((line, index) => (
        <span
          key={index}
          className={
            line.startsWith("+") && !line.startsWith("+++")
              ? "diff-add"
              : line.startsWith("-") && !line.startsWith("---")
                ? "diff-remove"
                : line.startsWith("@@")
                  ? "diff-hunk"
                  : ""
          }
        >
          {line}
          {index < lines.length - 1 ? "\n" : ""}
        </span>
      ))}
    </pre>
  );
}
export function TestOutput({
  title,
  result,
}: {
  title: string;
  result: {
    status: string;
    output: string;
    exit_code: number | null;
    output_truncated: boolean;
  } | null;
}) {
  return (
    <section className="test-result">
      <div className="section-heading">
        <h3>{title}</h3>
        {result && <Status value={result.status} />}
      </div>
      {result ? (
        <>
          <p className="muted small">
            Exit code {result.exit_code ?? "not recorded"}
            {result.output_truncated
              ? " · Output truncated in the record"
              : " · Complete recorded output"}
          </p>
          <pre
            tabIndex={0}
            aria-label={`${title} output`}
            className="test-output"
          >
            {result.output}
          </pre>
        </>
      ) : (
        <p className="muted">
          Not run. The proposal was rejected before application.
        </p>
      )}
    </section>
  );
}
