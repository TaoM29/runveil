import ApprovalConsole from "./approval-console";

export default function Home() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <p className="text-sm font-semibold uppercase tracking-widest text-slate-600">
        Web console · Local operator
      </p>
      <h1 className="mt-3 text-4xl font-semibold">Runveil approvals</h1>
      <p className="mt-4 text-slate-700">
        Inspect one existing run and decide its exact proposal. Submission and
        worker execution remain separate operator steps.
      </p>
      <ApprovalConsole />
      <a
        className="mt-8 inline-block underline underline-offset-4"
        href="/health"
      >
        Check web service health
      </a>
    </main>
  );
}
