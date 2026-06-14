import Link from "next/link";

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
              Search the CV corpus against a role brief
            </h1>
            <p className="mt-5 max-w-2xl text-lg leading-8 text-zinc-700">
              Paste a job description and review the strongest current-resume
              matches already stored in the canonical database.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <Link
              href="/"
              className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
            >
              Back to home
            </Link>
            <Link
              href="/review"
              className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
            >
              Review database
            </Link>
          </div>
        </header>

        <CandidateMatchWorkspace />
      </section>
    </main>
  );
}
