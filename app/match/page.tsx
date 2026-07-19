import { CandidateMatchWorkspace } from "./candidate-match-workspace";
import { requireAuthorizedUser } from "@/lib/auth";

export default async function MatchPage() {
  await requireAuthorizedUser();

  return (
    <main className="min-h-screen bg-[#eef1ec] text-zinc-950">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-8 sm:px-8 lg:px-10">
        <header className="overflow-hidden rounded-md border border-zinc-900 bg-[#101714] text-white shadow-sm">
          <div className="grid gap-6 px-6 py-8 sm:px-8 lg:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.9fr)] lg:px-10 lg:py-10">
            <div className="max-w-4xl">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-emerald-300">
                Match workspace
              </p>
              <h1 className="mt-4 text-4xl font-semibold leading-tight sm:text-5xl">
                Turn live recruiter input into grounded shortlist output
              </h1>
              <p className="mt-5 max-w-3xl text-lg leading-8 text-zinc-200">
                Start from a role brief, a reference CV, or a target company.
                Inspect the retrieved evidence first, then run shortlist
                reasoning over a candidate pool that already looks right.
              </p>
            </div>

            <aside className="grid gap-4 rounded-md border border-white/10 bg-white/6 p-5">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-300">
                  Workflow
                </p>
                <p className="mt-2 text-2xl font-semibold text-white">
                  Search, inspect, shortlist
                </p>
              </div>

              <div className="grid gap-3 text-sm leading-6 text-zinc-200">
                <div className="rounded-md border border-white/10 bg-black/10 p-3">
                  <p className="font-semibold text-white">Step 1</p>
                  <p>Retrieve candidate evidence from the current corpus.</p>
                </div>
                <div className="rounded-md border border-white/10 bg-black/10 p-3">
                  <p className="font-semibold text-white">Step 2</p>
                  <p>Preview people, CVs, graph context, and company links.</p>
                </div>
                <div className="rounded-md border border-white/10 bg-black/10 p-3">
                  <p className="font-semibold text-white">Step 3</p>
                  <p>Run final ranking only once the pool is credible.</p>
                </div>
              </div>
            </aside>
          </div>
        </header>

        <nav className="flex flex-wrap gap-3">
          <a
            href="#role-brief-workflow"
            className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-900 shadow-sm transition hover:border-zinc-500"
          >
            Search workflow
          </a>
          <a
            href="#search-results"
            className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-900 shadow-sm transition hover:border-zinc-500"
          >
            Retrieval output
          </a>
          <a
            href="#shortlist-results"
            className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-900 shadow-sm transition hover:border-zinc-500"
          >
            Shortlist
          </a>
          <a
            href="#candidate-preview"
            className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-900 shadow-sm transition hover:border-zinc-500"
          >
            Candidate profile
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
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Retrieval
            </p>
            <p className="mt-3 text-xl font-semibold text-zinc-950">
              Hybrid search over stored CV evidence
            </p>
            <p className="mt-3 text-sm leading-6 text-zinc-700">
              Use a role brief or uploaded CV to pull a candidate pool before
              any ranking call is made.
            </p>
          </div>

          <div className="rounded-md border border-zinc-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Inspection
            </p>
            <p className="mt-3 text-xl font-semibold text-zinc-950">
              Visible evidence instead of black-box output
            </p>
            <p className="mt-3 text-sm leading-6 text-zinc-700">
              Inspect CV excerpts, candidate details, skills, contacts, jobs,
              and opportunities before shortlisting.
            </p>
          </div>

          <div className="rounded-md border border-zinc-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Final pass
            </p>
            <p className="mt-3 text-xl font-semibold text-zinc-950">
              Recruiter-facing shortlist output
            </p>
            <p className="mt-3 text-sm leading-6 text-zinc-700">
              The reasoning model is the last stage, not the first stage.
            </p>
          </div>
        </section>

        <CandidateMatchWorkspace />
      </section>
    </main>
  );
}
