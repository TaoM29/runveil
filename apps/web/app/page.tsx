export default function Home() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-20">
      <p className="text-sm font-semibold uppercase tracking-widest text-slate-600">
        Web console · Foundation
      </p>
      <h1 className="mt-4 text-4xl font-semibold">Runveil</h1>
      <p className="mt-6 text-lg leading-relaxed">
        A custom Python runtime for durable, bounded AI-agent execution.
      </p>
      <p className="mt-4 leading-relaxed text-slate-700">
        The backend supports durable agent execution. This web console remains a
        foundation; trace and evaluation interfaces are planned.
      </p>
      <a
        className="mt-8 inline-block rounded underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-4"
        href="/health"
      >
        Check web service health
      </a>
    </main>
  );
}
