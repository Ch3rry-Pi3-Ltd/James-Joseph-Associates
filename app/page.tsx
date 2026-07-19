import Link from "next/link";
import { requireAuthorizedUser } from "@/lib/auth";

type FoundationItem = {
  label: string;
  status: "Live" | "Ready" | "Planned";
};

type WorkspaceSection = {
  title: string;
  description: string;
  state: "Foundation ready" | "Planned" | "Waiting for data";
  href?: string;
  actionLabel?: string;
};

const foundationItems: FoundationItem[] = [
  { label: "FastAPI backend", status: "Live" },
  { label: "Versioned API routes", status: "Live" },
  { label: "Structured error responses", status: "Ready" },
  { label: "HTTP metadata helpers", status: "Ready" },
  { label: "Canonical Supabase schema", status: "Live" },
  { label: "LangGraph foundation", status: "Ready" },
];

const workspaceSections: WorkspaceSection[] = [
  {
    title: "Company Intelligence",
    description:
      "Look up target firms and inspect linked candidates, contacts, jobs, and opportunities already in the canonical layer.",
    state: "Foundation ready",
    href: "/company",
    actionLabel: "Open company lookup",
  },
  {
    title: "Review Surface",
    description:
      "Inspect recent canonical rows, source provenance, document activity, and system-level landing checks.",
    state: "Foundation ready",
    href: "/review",
    actionLabel: "Open review surface",
  },
  {
    title: "Job Matching",
    description:
      "Search the CV corpus, inspect evidence, and turn a live brief into a recruiter-usable shortlist.",
    state: "Foundation ready",
    href: "/match",
    actionLabel: "Open matching",
  },
  {
    title: "Workflow Actions",
    description:
      "Surface controlled next actions for outreach, CRM sync, and operator approval.",
    state: "Planned",
  },
];

function getStatusClass(status: FoundationItem["status"]): string {
  if (status === "Live") {
    return "border-emerald-400/30 bg-emerald-400/12 text-emerald-200";
  }

  if (status === "Ready") {
    return "border-cyan-400/30 bg-cyan-400/12 text-cyan-200";
  }

  return "border-rose-400/30 bg-rose-400/12 text-rose-200";
}

function getSectionStateClass(state: WorkspaceSection["state"]): string {
  if (state === "Foundation ready") {
    return "border-emerald-300/40 bg-emerald-400/10 text-emerald-700";
  }

  if (state === "Waiting for data") {
    return "border-amber-300/40 bg-amber-400/10 text-amber-700";
  }

  return "border-rose-300/40 bg-rose-400/10 text-rose-700";
}

export default async function Home() {
  await requireAuthorizedUser();

  return (
    <main className="min-h-screen bg-[#eef1ec] text-zinc-950">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-8 sm:px-8 lg:px-10">
        <header className="overflow-hidden rounded-md border border-zinc-900 bg-[#111815] text-white shadow-sm">
          <div
            className="relative min-h-[30rem] bg-cover bg-center"
            style={{
              backgroundImage:
                "url('https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=1600&q=80')",
            }}
            aria-label="Recruitment operations workspace"
          >
            <div className="absolute inset-0 bg-black/55" />

            <div className="relative grid min-h-[30rem] gap-8 px-6 py-8 sm:px-8 lg:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.9fr)] lg:px-10 lg:py-10">
              <div className="flex flex-col justify-between gap-8">
                <div className="max-w-4xl">
                  <p className="text-sm font-semibold uppercase tracking-[0.18em] text-emerald-300">
                    James Joseph Associates
                  </p>

                  <h1 className="mt-4 text-4xl font-semibold leading-tight sm:text-5xl lg:text-6xl">
                    Recruitment intelligence workspace
                  </h1>

                  <p className="mt-5 max-w-3xl text-lg leading-8 text-zinc-200">
                    Search the current corpus, inspect live company context, and
                    turn recruiter input into grounded evidence instead of
                    black-box output.
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-md border border-white/15 bg-white/8 p-4 backdrop-blur-sm">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-300">
                      Search
                    </p>
                    <p className="mt-2 text-lg font-semibold">
                      Retrieve candidates and documents
                    </p>
                  </div>

                  <div className="rounded-md border border-white/15 bg-white/8 p-4 backdrop-blur-sm">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-300">
                      Context
                    </p>
                    <p className="mt-2 text-lg font-semibold">
                      Surface company, contact, and opportunity links
                    </p>
                  </div>

                  <div className="rounded-md border border-white/15 bg-white/8 p-4 backdrop-blur-sm">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-300">
                      Reasoning
                    </p>
                    <p className="mt-2 text-lg font-semibold">
                      Produce recruiter-usable shortlist output
                    </p>
                  </div>
                </div>
              </div>

              <aside className="grid content-start gap-5 self-end rounded-md border border-white/10 bg-[#121b17]/85 p-5 backdrop-blur-sm">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-300">
                    Current operating mode
                  </p>
                  <p className="mt-2 text-2xl font-semibold text-white">
                    Evidence-first recruiter workflow
                  </p>
                </div>

                <dl className="grid gap-3 text-sm leading-6 text-zinc-200">
                  <div>
                    <dt className="font-semibold text-white">Primary tabs</dt>
                    <dd>Review, Company, Match</dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-white">Data layer</dt>
                    <dd>Candidates, CVs, contacts, companies, jobs, opportunities</dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-white">Operator control</dt>
                    <dd>Search first, inspect evidence, then shortlist</dd>
                  </div>
                </dl>

                <div className="flex flex-wrap gap-3 pt-1">
                  <Link
                    href="/match"
                    className="inline-flex h-11 items-center justify-center rounded-md bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:bg-zinc-200"
                  >
                    Open matching
                  </Link>

                  <a
                    href="/api/v1/health"
                    className="inline-flex h-11 items-center justify-center rounded-md border border-white/20 px-4 text-sm font-semibold text-white transition hover:bg-white/8"
                  >
                    Check API health
                  </a>
                </div>
              </aside>
            </div>
          </div>
        </header>

        <section className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="grid gap-6 rounded-md border border-zinc-200/80 bg-[linear-gradient(180deg,#ffffff_0%,#f3f7f3_100%)] p-6 shadow-[0_24px_60px_rgba(15,23,42,0.08)] sm:p-8">
            <div className="flex flex-col gap-4 border-b border-zinc-200 pb-6 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.14em] text-zinc-500">
                  Core workstreams
                </p>
                <h2 className="mt-2 max-w-md text-4xl font-semibold leading-tight text-zinc-950">
                  Use the platform as one connected workflow
                </h2>
              </div>

              <p className="max-w-xl text-sm leading-7 text-zinc-600">
                Each tab should expose a distinct operational surface without
                breaking the canonical data model underneath.
              </p>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              {workspaceSections.map((section, index) => (
                <article
                  key={section.title}
                  className="relative grid gap-5 overflow-hidden rounded-md border border-zinc-200/80 bg-white p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)]"
                >
                  <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-emerald-400 via-cyan-400 to-sky-500" />

                  <div className="flex items-start justify-between gap-4 pt-2">
                    <div className="grid gap-3">
                      <span className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-400">
                        0{index + 1}
                      </span>
                      <h3 className="max-w-[14rem] text-2xl font-semibold leading-tight text-zinc-950">
                        {section.title}
                      </h3>
                    </div>
                    <span
                      className={`shrink-0 rounded-md border px-3 py-1 text-xs font-semibold ${getSectionStateClass(
                        section.state,
                      )}`}
                    >
                      {section.state}
                    </span>
                  </div>

                  <p className="text-base leading-7 text-zinc-700">
                    {section.description}
                  </p>

                  {section.href && section.actionLabel ? (
                    <div>
                      <Link
                        href={section.href}
                        className="inline-flex h-11 items-center justify-center rounded-md bg-zinc-950 px-4 text-sm font-semibold text-white transition hover:bg-zinc-800"
                      >
                        {section.actionLabel}
                      </Link>
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          </div>

          <aside className="grid gap-6 rounded-md border border-zinc-900 bg-[radial-gradient(circle_at_top_left,#20342b_0%,#111815_65%)] p-6 text-white shadow-[0_24px_60px_rgba(15,23,42,0.28)] sm:p-8">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.14em] text-emerald-300">
                Platform status
              </p>
              <h2 className="mt-2 text-4xl font-semibold leading-tight">
                Current implementation map
              </h2>
            </div>

            <div className="grid gap-3">
              {foundationItems.map((item) => (
                <article
                  key={item.label}
                  className="flex items-center justify-between gap-4 rounded-md border border-white/10 bg-black/12 px-4 py-3 backdrop-blur-sm"
                >
                  <div className="flex items-center gap-3">
                    <span className="h-2.5 w-2.5 rounded-full bg-emerald-300 shadow-[0_0_16px_rgba(110,231,183,0.8)]" />
                    <span className="text-sm font-medium text-white">
                      {item.label}
                    </span>
                  </div>
                  <span
                    className={`shrink-0 rounded-md border px-3 py-1 text-xs font-semibold ${getStatusClass(
                      item.status,
                    )}`}
                  >
                    {item.status}
                  </span>
                </article>
              ))}
            </div>

            <div className="rounded-md border border-emerald-400/20 bg-emerald-400/10 p-5 text-sm leading-7 text-zinc-100">
              The active product direction is deterministic retrieval and review
              over canonical data, with reasoning applied only after the
              evidence looks correct.
            </div>
          </aside>
        </section>

        <section className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="grid gap-5 rounded-md border border-zinc-200/80 bg-[linear-gradient(180deg,#fffdf7_0%,#f5efe3_100%)] p-6 shadow-[0_24px_60px_rgba(15,23,42,0.08)] sm:p-8">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.14em] text-zinc-500">
                Live route
              </p>
              <h2 className="mt-2 max-w-md text-4xl font-semibold leading-tight text-zinc-950">
                Backend health and deployment checks
              </h2>
            </div>

            <div className="rounded-md border border-zinc-900/10 bg-zinc-950 p-4 font-mono text-sm text-emerald-200 shadow-inner">
              GET /api/v1/health
            </div>

            <div className="flex flex-wrap gap-2">
              <span className="rounded-md border border-emerald-300/50 bg-emerald-400/10 px-3 py-1 text-sm font-medium text-emerald-800">
                FastAPI live
              </span>
              <span className="rounded-md border border-sky-300/50 bg-sky-400/10 px-3 py-1 text-sm font-medium text-sky-800">
                Vercel routed
              </span>
            </div>

            <p className="max-w-lg text-base leading-7 text-zinc-700">
              This remains the quickest operator check that the deployed app is
              reachable and the backend route map is intact.
            </p>
          </div>

          <div className="grid gap-6 rounded-md border border-zinc-200/80 bg-[linear-gradient(180deg,#ffffff_0%,#f6f5fb_100%)] p-6 shadow-[0_24px_60px_rgba(15,23,42,0.08)] sm:p-8">
            <div className="flex flex-col gap-4 border-b border-zinc-200 pb-6 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.14em] text-zinc-500">
                  Operator path
                </p>
                <h2 className="mt-2 max-w-md text-4xl font-semibold leading-tight text-zinc-950">
                  Move through the tabs in sequence
                </h2>
              </div>

              <p className="max-w-xl text-sm leading-7 text-zinc-600">
                Inspect data, surface company context, then match candidates
                against live briefs using the same canonical layer.
              </p>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <article className="relative rounded-md border border-zinc-200 bg-[#f6faf8] p-5 shadow-[0_12px_32px_rgba(15,23,42,0.06)]">
                <span className="absolute right-4 top-4 text-sm font-semibold text-zinc-300">
                  01
                </span>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                  Review
                </p>
                <p className="mt-4 text-xl font-semibold leading-8 text-zinc-950">
                  Inspect recent canonical records
                </p>
              </article>

              <article className="relative rounded-md border border-zinc-200 bg-[#f8f8fb] p-5 shadow-[0_12px_32px_rgba(15,23,42,0.06)]">
                <span className="absolute right-4 top-4 text-sm font-semibold text-zinc-300">
                  02
                </span>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                  Company
                </p>
                <p className="mt-4 text-xl font-semibold leading-8 text-zinc-950">
                  Surface linked candidates, jobs, and contacts
                </p>
              </article>

              <article className="relative rounded-md border border-zinc-200 bg-[#fff8f4] p-5 shadow-[0_12px_32px_rgba(15,23,42,0.06)]">
                <span className="absolute right-4 top-4 text-sm font-semibold text-zinc-300">
                  03
                </span>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                  Match
                </p>
                <p className="mt-4 text-xl font-semibold leading-8 text-zinc-950">
                  Turn a role brief into a recruiter shortlist
                </p>
              </article>
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}
