import { CandidateMatchWorkspace } from "./candidate-match-workspace";

export default function MatchPage() {
  return (
    <main className="min-h-screen bg-[#f7f7f2] text-zinc-950">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-8 sm:px-8 lg:px-10">
        <header className="flex flex-col gap-5 border-b border-zinc-200 pb-8 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold uppercase text-emerald-700">
              Candidate matching
            </p>
            <h1 className="mt-3 text-4xl font-semibold leading-tight text-zinc-950 sm:text-5xl">
              Turn recruiter context into a usable shortlist
            </h1>
            <p className="mt-5 max-w-2xl text-lg leading-8 text-zinc-700">
              Start from a role brief, a reference CV, or a target company.
              Search the current corpus, inspect the retrieved evidence, and
              only then ask the reasoning model to rank the strongest fits
              already stored in the canonical database.
            </p>
          </div>
        </header>

        <section className="grid gap-4 lg:grid-cols-3">
          <div className="border border-zinc-200 bg-white p-5">
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

          <div className="border border-zinc-200 bg-white p-5">
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

          <div className="border border-zinc-200 bg-white p-5">
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
