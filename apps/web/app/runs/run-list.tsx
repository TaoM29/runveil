"use client";
import { useState } from "react";
import type { ShowcaseRun } from "../../lib/showcase";
import RunTable from "../components/run-table";

export default function RunList({ runs }: { runs: ShowcaseRun[] }) {
  const [query, setQuery] = useState("");
  const [outcome, setOutcome] = useState("All outcomes");
  const visible = runs.filter(
    (run) =>
      `${run.title} ${run.fixture} ${run.id}`
        .toLowerCase()
        .includes(query.toLowerCase().trim()) &&
      (outcome === "All outcomes" || run.outcome === outcome),
  );
  return (
    <section className="section-block">
      <div className="filter-bar">
        <label>
          Find a run
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Task, fixture or run ID"
          />
        </label>
        <label>
          Outcome
          <select
            value={outcome}
            onChange={(event) => setOutcome(event.target.value)}
          >
            {["All outcomes", "Passed", "Rejected", "Validation failed"].map(
              (value) => (
                <option key={value}>{value}</option>
              ),
            )}
          </select>
        </label>
        <p className="muted small" role="status">
          {visible.length} of {runs.length} runs
        </p>
      </div>
      {visible.length ? (
        <RunTable runs={visible} />
      ) : (
        <div className="empty-state">
          <h2>No matching runs</h2>
          <p>
            Try another task name or clear the filters to see the recorded
            executions.
          </p>
          <button
            className="button"
            onClick={() => {
              setQuery("");
              setOutcome("All outcomes");
            }}
          >
            Clear filters
          </button>
        </div>
      )}
      <p className="small muted archive-note">
        All times in the record are UTC. The validation-failure probe
        deliberately proposed an ineffective repair; it is not a normal provider
        result.
      </p>
    </section>
  );
}
