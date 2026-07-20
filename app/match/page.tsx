import { CandidateMatchWorkspace } from "./candidate-match-workspace";
import { UsageGuide } from "../usage-guide";
import { requireAuthorizedUser } from "@/lib/auth";

export default async function MatchPage() {
  await requireAuthorizedUser();

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#eef1ec_0%,#f6f6f1_40%,#fbfbf8_100%)] text-zinc-950">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-8 sm:px-8 lg:px-10">
        <header className="workspace-hero">
          <div className="grid gap-8 px-6 py-8 sm:px-8 lg:grid-cols-[minmax(0,1.25fr)_minmax(340px,0.75fr)] lg:px-10 lg:py-10">
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

              <div className="mt-8 grid gap-4 sm:grid-cols-3">
                <div className="workspace-card-contrast p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-200">
                    Retrieve
                  </p>
                  <p className="mt-3 text-sm leading-6 text-zinc-100">
                    Search CV evidence and linked company context first.
                  </p>
                </div>
                <div className="workspace-card-contrast p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-200">
                    Inspect
                  </p>
                  <p className="mt-3 text-sm leading-6 text-zinc-100">
                    Preview candidate profiles, documents, contacts, and jobs.
                  </p>
                </div>
                <div className="workspace-card-contrast p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-200">
                    Shortlist
                  </p>
                  <p className="mt-3 text-sm leading-6 text-zinc-100">
                    Apply reasoning only when the evidence already looks credible.
                  </p>
                </div>
              </div>
            </div>

            <aside className="grid gap-4 rounded-md border border-white/10 bg-white/6 p-5 backdrop-blur-sm">
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

        <UsageGuide
          eyebrow="Instructions"
          title="How to use the matching page"
          intro="This page is a three-stage workflow: load the brief, inspect the retrieval pool, then run the final shortlist only when the evidence looks credible."
          steps={[
            {
              title: "Load the role brief",
              body: "Paste a job description or upload a job-spec file, then choose whether to use the uploaded text or your own pasted brief as the working input.",
            },
            {
              title: "Run corpus search first",
              body: "Click Search corpus to retrieve the first candidate pool. Open the corpus results section to inspect the raw evidence, names, excerpts, and company context before ranking anything.",
            },
            {
              title: "Run the final shortlist",
              body: "Once the retrieval pool looks sensible, click the shortlist action. That sends the selected candidate pool into the final reasoning pass and returns ranked candidates with strengths, gaps, and CV links.",
            },
          ]}
          tip="Use the Company tab when you already know the firm. Use Match when the starting point is a role brief and you need the best candidate shortlist first."
        />

        <nav className="flex flex-wrap gap-3">
          {[
            ["#role-brief-workflow", "Search workflow"],
            ["#search-results", "Retrieval output"],
            ["#shortlist-results", "Shortlist"],
            ["#candidate-preview", "Candidate profile"],
            ["#company-intelligence", "Company lookup"],
          ].map(([href, label]) => (
            <a
              key={href}
              href={href}
              className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-200/80 bg-white/90 px-4 text-sm font-semibold text-zinc-900 shadow-[0_12px_30px_rgba(15,23,42,0.05)] transition hover:border-emerald-400 hover:bg-white"
            >
              {label}
            </a>
          ))}
        </nav>

        <section className="grid gap-4 lg:grid-cols-3">
          <div className="workspace-kpi p-5">
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

          <div className="workspace-kpi p-5">
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

          <div className="workspace-kpi p-5">
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
