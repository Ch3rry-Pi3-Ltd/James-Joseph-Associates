import Link from "next/link";

import { requireAuthorizedUser } from "@/lib/auth";

const workspaces = [
  {
    number: "01",
    title: "Company intelligence",
    description:
      "See the candidates, contacts, jobs, opportunities, and relationship history already connected to a target firm.",
    href: "/company",
    action: "Explore companies",
    accent: "from-cyan-400 to-teal-500",
  },
  {
    number: "02",
    title: "Evidence review",
    description:
      "Inspect canonical records, source provenance, document activity, extraction quality, and recent system movement.",
    href: "/review",
    action: "Open review",
    accent: "from-blue-500 to-cyan-400",
  },
  {
    number: "03",
    title: "Candidate matching",
    description:
      "Move from a live role brief to a transparent candidate pool, detailed evidence, and a recruiter-ready shortlist.",
    href: "/match",
    action: "Start matching",
    accent: "from-violet-500 to-blue-500",
  },
];

const foundationItems = [
  ["Canonical data", "Live"],
  ["Hybrid retrieval", "Live"],
  ["Grounded shortlists", "Live"],
  ["Source provenance", "Live"],
  ["Private exports", "Live"],
  ["Controlled workflows", "Ready"],
];

export default async function Home() {
  await requireAuthorizedUser();

  return (
    <main className="app-canvas min-h-screen">
      <section className="mx-auto w-full max-w-7xl px-6 sm:px-8 lg:px-10">
        <div className="home-hero">
          <div className="relative z-10 max-w-3xl">
            <p className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-[0.2em] text-[#2859e8]">
              <span className="h-2 w-2 rounded-full bg-[#0d6b6d]" />
              Evidence-led recruitment operations
            </p>
            <h1 className="home-display mt-7">
              See the signal.
              <span>Make the match.</span>
              <span className="home-display-accent">Recruit smarter.</span>
            </h1>
            <p className="mt-8 max-w-2xl text-lg leading-8 text-slate-600 sm:text-xl">
              One connected workspace for searching the candidate corpus,
              understanding company relationships, and producing shortlists that
              show their evidence.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/match" className="app-primary-action">
                Start a candidate search <span aria-hidden="true">→</span>
              </Link>
              <Link href="/company" className="app-secondary-action">
                Explore company context <span aria-hidden="true">→</span>
              </Link>
            </div>
          </div>

          <aside className="home-portal flex flex-col justify-between p-6 sm:p-8">
            <div className="flex items-center justify-between gap-4 text-[10px] font-extrabold uppercase tracking-[0.16em] text-cyan-200">
              <span>JJA / intelligence workflow</span>
              <span className="flex items-center gap-2 text-emerald-300">
                <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.8)]" />
                Live
              </span>
            </div>

            <div className="grid place-items-center py-10">
              <div className="home-portal-mark">JJA</div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {[
                ["01 / Search", "Find the strongest evidence"],
                ["02 / Connect", "See the company context"],
                ["03 / Assess", "Compare strengths and gaps"],
                ["04 / Deliver", "Review and export clearly"],
              ].map(([label, value]) => (
                <div
                  key={label}
                  className="rounded-2xl border border-cyan-200/15 bg-white/[0.035] p-4"
                >
                  <p className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-cyan-300">
                    {label}
                  </p>
                  <p className="mt-2 text-sm font-semibold text-white">{value}</p>
                </div>
              ))}
            </div>
          </aside>
        </div>

        <section className="border-y border-slate-900/10 py-16 sm:py-20">
          <div className="grid gap-8 lg:grid-cols-[0.72fr_1.28fr]">
            <div>
              <p className="text-xs font-extrabold uppercase tracking-[0.19em] text-[#0d6b6d]">
                Connected workspaces
              </p>
              <h2 className="mt-4 max-w-md text-4xl font-semibold leading-[1.05] tracking-[-0.045em] text-[#071b2a] sm:text-5xl">
                Three views. One source of truth.
              </h2>
              <p className="mt-5 max-w-lg text-base leading-7 text-slate-600">
                Move between company context, source review, and candidate
                matching without losing the canonical evidence underneath.
              </p>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              {workspaces.map((workspace) => (
                <article
                  key={workspace.title}
                  className="group relative flex min-h-[25rem] flex-col overflow-hidden rounded-[1.6rem] border border-slate-900/10 bg-white p-6 shadow-[0_22px_60px_rgba(7,27,42,0.065)] transition hover:-translate-y-1 hover:shadow-[0_28px_70px_rgba(7,27,42,0.1)]"
                >
                  <div className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${workspace.accent}`} />
                  <p className="text-xs font-bold tracking-[0.16em] text-slate-400">
                    {workspace.number}
                  </p>
                  <h3 className="mt-8 text-2xl font-semibold leading-tight tracking-[-0.03em] text-[#071b2a]">
                    {workspace.title}
                  </h3>
                  <p className="mt-5 flex-1 text-sm leading-7 text-slate-600">
                    {workspace.description}
                  </p>
                  <Link
                    href={workspace.href}
                    className="mt-8 inline-flex items-center gap-2 text-sm font-bold text-[#2859e8]"
                  >
                    {workspace.action}
                    <span className="transition group-hover:translate-x-1" aria-hidden="true">
                      →
                    </span>
                  </Link>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="grid gap-6 py-16 sm:py-20 lg:grid-cols-[1.12fr_0.88fr]">
          <div className="workspace-hero p-7 sm:p-10">
            <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-cyan-300">
              Built for recruiter judgement
            </p>
            <h2 className="mt-5 max-w-2xl text-4xl font-semibold leading-[1.08] tracking-[-0.04em] text-white sm:text-5xl">
              The system organises the evidence. You keep the decision.
            </h2>
            <p className="mt-6 max-w-2xl text-base leading-8 text-slate-300">
              Search, provenance, comparisons, strengths, gaps, contact routes,
              and export review stay visible. Model output never replaces the
              underlying candidate evidence.
            </p>
          </div>

          <div className="rounded-[2rem] border border-slate-900/10 bg-white/85 p-7 shadow-[0_22px_60px_rgba(7,27,42,0.065)] sm:p-9">
            <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-[#0d6b6d]">
              Platform status
            </p>
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              {foundationItems.map(([label, status]) => (
                <div
                  key={label}
                  className="flex items-center justify-between gap-3 rounded-2xl border border-slate-900/10 bg-[#f8faf9] px-4 py-3"
                >
                  <span className="text-sm font-semibold text-slate-700">{label}</span>
                  <span className="rounded-full bg-cyan-100 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-[0.12em] text-cyan-900">
                    {status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}
