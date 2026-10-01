import TraceConsole from "./trace-console";

export const metadata = { title: "Runveil | Run traces" };

export default function Traces() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <p className="text-sm font-semibold uppercase tracking-widest text-slate-600">
        Web console · Local operator
      </p>
      <h1 className="mt-3 text-4xl font-semibold">Runveil traces</h1>
      <p className="mt-4 text-slate-700">
        Inspect the recorded execution of one existing run. This screen is
        read-only.
      </p>
      <TraceConsole />
      {/* Full navigation deliberately discards in-memory credentials and data. */}
      {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
      <a className="mt-8 inline-block underline underline-offset-4" href="/">
        Open approval console (separate token required)
      </a>
    </main>
  );
}
