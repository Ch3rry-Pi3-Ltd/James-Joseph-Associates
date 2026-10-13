import { requireAuthorizedUser } from "@/lib/auth";

import { CvDocumentSearchWorkspace } from "./cv-document-search-workspace";

export default async function CvSearchPage() {
  await requireAuthorizedUser();

  return (
    <main className="app-canvas min-h-screen text-zinc-950">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-8 sm:px-8 lg:px-10">
        <header className="workspace-hero">
          <div className="grid gap-7 px-6 py-8 sm:px-8 lg:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)] lg:px-10 lg:py-10">
            <div className="max-w-4xl">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-emerald-300">
                Exhaustive CV search
              </p>
              <h1 className="mt-4 text-4xl font-semibold leading-tight sm:text-5xl">
                Find every exact match, with the coverage to prove it
              </h1>
              <p className="mt-5 max-w-3xl text-lg leading-8 text-zinc-200">
                Search the complete extracted text of all current CVs, page through every
                match, identify data gaps, and export the full result set without sending
                each document to an LLM.
              </p>
            </div>

            <aside className="workspace-card-contrast grid gap-4 p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-300">
                Search scope
              </p>
              <p className="text-2xl font-semibold text-white">Canonical current CVs</p>
              <ul className="grid gap-2 text-sm leading-6 text-zinc-200">
                <li>Full extracted document text</li>
                <li>Every result available through pagination</li>
                <li>Coverage and missing-text exclusions reported</li>
                <li>No per-document model calls</li>
              </ul>
            </aside>
          </div>
        </header>

        <CvDocumentSearchWorkspace />
      </section>
    </main>
  );
}
