import { CandidateMatchWorkspace } from "./candidate-match-workspace";

export default function MatchPage() {
  return (
    <main className="min-h-screen bg-[#f3f4ee] text-zinc-950">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-6 py-8 sm:px-8 lg:px-10">
        <header className="grid gap-6 rounded-md border border-zinc-200 bg-white p-6 shadow-sm lg:grid-cols-[minmax(0,1.7fr)_minmax(280px,0.9fr)] lg:p-8">
          <div className="max-w-4xl">
            <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">
              Candidate matching
            </p>
            <h1 className="mt-3 text-4xl font-semibold leading-tight text-zinc-950 sm:text-5xl">
              Turn recruiter context into a usable shortlist
            </h1>
            <p className="mt-5 max-w-3xl text-lg leading-8 text-zinc-700">
              Start from a role brief, a reference CV, or a target company.
              Search the current corpus, inspect the evidence, and only then
              ask the reasoning model to rank the strongest fits already stored
              in the canonical database.
            </p>
          </div>

          <div className="grid gap-4 rounded-md border border-emerald-200 bg-emerald-50 p-5">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">
                Best use today
              </p>
              <p className="mt-2 text-lg font-semibold text-zinc-950">
                Internal recruiter demo and UAT
              </p>
            </div>

            <dl className="grid gap-3 text-sm leading-6 text-zinc-800">
              <div>
                <dt className="font-semibold text-zinc-950">Search surface</dt>
                <dd>Role brief, uploaded CV, or company context.</dd>
              </div>
              <div>
                <dt className="font-semibold text-zinc-950">Evidence shown</dt>
                <dd>CV retrieval, graph context, contacts, jobs, and opportunities.</dd>
              </div>
              <div>
                <dt className="font-semibold text-zinc-950">Final output</dt>
                <dd>Recruiter-style shortlist with reasons, strengths, and gaps.</dd>
              </div>
            </dl>
          </div>
        </header>

        <nav className="flex flex-wrap gap-3">
          <a
            href="#role-brief-workflow"
            className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-900 shadow-sm transition hover:border-zinc-500"
          >
            Role brief workflow
          </a>
          <a
            href="#candidate-preview"
            className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-900 shadow-sm transition hover:border-zinc-500"
          >
            Candidate preview
          </a>
          <a
            href="#shortlist-results"
            className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-900 shadow-sm transition hover:border-zinc-500"
          >
            Shortlist
          </a>
          <a
            href="#company-intelligence"
            className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-900 shadow-sm transition hover:border-zinc-500"
          >
            Company lookup
          </a>
        </nav>

        <section className="grid gap-4 lg:grid-cols-3">
          <div className="rounded-md border border-zinc-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-semibold uppercase text-zinc-500">
              Workflow 1
            </p>
            <h2 className="mt-2 text-xl font-semibold text-zinc-950">
              Role brief to shortlist
            </h2>
            <p className="mt-3 text-sm leading-6 text-zinc-700">
              Paste a job description, inspect the search pool, then run the
              shortlist once the evidence looks sensible.
            </p>
          </div>

          <div className="rounded-md border border-zinc-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-semibold uppercase text-zinc-500">
              Workflow 2
            </p>
            <h2 className="mt-2 text-xl font-semibold text-zinc-950">
              CV to similar candidates
            </h2>
            <p className="mt-3 text-sm leading-6 text-zinc-700">
              Upload one PDF or Word CV to use it as a transient search query
              without persisting the uploaded file.
            </p>
          </div>

          <div className="rounded-md border border-zinc-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-semibold uppercase text-zinc-500">
              Workflow 3
            </p>
            <h2 className="mt-2 text-xl font-semibold text-zinc-950">
              Company and relationship lookup
            </h2>
            <p className="mt-3 text-sm leading-6 text-zinc-700">
              Check who works somewhere, who knows them, which jobs exist there,
              and what interaction history is already stored.
            </p>
          </div>
        </section>

        <CandidateMatchWorkspace />
      </section>
    </main>
  );
}
