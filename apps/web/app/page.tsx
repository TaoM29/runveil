export default function Home() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-20">
      <p className="text-sm font-semibold uppercase tracking-widest text-slate-600">
        Phase 0 · Foundation
      </p>
      <h1 className="mt-4 text-4xl font-semibold">AgentRail</h1>
      <p className="mt-6 text-lg leading-relaxed">
        A production-style runtime for reliable, observable and evaluable AI
        agents.
      </p>
      <p className="mt-4 leading-relaxed text-slate-700">
        The project foundation is in place. Agent execution, traces and
        evaluations are planned for later phases.
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
