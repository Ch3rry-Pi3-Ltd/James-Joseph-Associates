/**
 * Home dashboard shell for the James Joseph Associates intelligence app.
 *
 * This page is the first visible product surface for the project.
 *
 * It gives the frontend a stable way to talk about:
 *
 * - API availability
 * - recruitment intelligence areas
 * - future candidate/job matching workflows
 * - proposed action review
 * - system foundation status
 *
 * In plain language:
 *
 * - this page answers the question:
 *
 *     "What will the first user-facing shell of the intelligence system look like?"
 *
 * - it does not fetch real candidate data
 * - it does not connect to Supabase
 * - it does not call LangChain
 * - it does not call LangGraph
 * - it does not perform authentication
 * - it does not pretend fake recommendations are real
 *
 * Notes
 * -----
 * - This is intentionally a static Server Component.
 * - It can be deployed safely before real data exists.
 * - The visible sections match the backend/API roadmap.
 * - Later, individual sections can become real components under `app/components/`.
 * - The API status card points people to the real health endpoint:
 *
 *     /api/v1/health
 */

type FoundationItem = {
  /**
   * Short label for one foundation capability.
   *
   * Example:
   *
   *     "FastAPI backend"
   */
  label: string;

  /**
   * Current implementation status shown in the UI.
   *
   * This is display text only. It is not calculated from live checks yet.
   */
  status: "Live" | "Ready" | "Planned";
};

type WorkspaceSection = {
  /**
   * Title shown for one dashboard area.
   */
  title: string;

  /**
   * Short product-facing description of what this area will support.
   */
  description: string;

  /**
   * Current state shown to users.
   *
   * For now, this should stay honest and avoid implying unfinished workflows are
   * already active.
   */
  state: "Foundation ready" | "Planned" | "Waiting for data";
};

const foundationItems: FoundationItem[] = [
  {
    label: "FastAPI backend",
    status: "Live",
  },
  {
    label: "Versioned API routes",
    status: "Live",
  },
  {
    label: "Structured error responses",
    status: "Ready",
  },
  {
    label: "HTTP metadata helpers",
    status: "Ready",
  },
  {
    label: "Supabase schema",
    status: "Planned",
  },
  {
    label: "LangGraph workflows",
    status: "Planned",
  },
];

const workspaceSections: WorkspaceSection[] = [
  {
    title: "Candidate Intelligence",
    description:
      "Review candidate context, skills, documents, and source-system history.",
    state: "Waiting for data",
  },
  {
    title: "Job Matching",
    description:
      "Prepare evidence-backed candidate recommendations for open roles.",
    state: "Planned",
  },
  {
    title: "Proposed Actions",
    description:
      "Review draft outreach, CRM updates, and workflow actions before execution.",
    state: "Planned",
  },
  {
    title: "System Status",
    description:
      "Track API health, deployment checks, and backend foundation readiness.",
    state: "Foundation ready",
  },
];

function getStatusClass(status: FoundationItem["status"]): string {
  /**
   * Return the visual style for a foundation status badge.
   *
   * Parameters
   * ----------
   * status : FoundationItem["status"]
   *   Current implementation status.
   *
   * Returns
   * -------
   * string
   *   Tailwind class names used by the badge.
   *
   * Notes
   * -----
   * - This keeps the status-to-colour mapping in one place.
   * - The colours are deliberately restrained so the UI does not imply a noisy
   *   alert dashboard.
   */

  if (status === "Live") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }

  if (status === "Ready") {
    return "border-sky-200 bg-sky-50 text-sky-800";
  }

  return "border-zinc-200 bg-zinc-50 text-zinc-700";
}

function getSectionStateClass(state: WorkspaceSection["state"]): string {
  /**
   * Return the visual style for a workspace section state badge.
   *
   * Parameters
   * ----------
   * state : WorkspaceSection["state"]
   *   Current section state shown in the card.
   *
   * Returns
   * -------
   * string
   *   Tailwind class names used by the badge.
   */

  if (state === "Foundation ready") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }

  if (state === "Waiting for data") {
    return "border-amber-200 bg-amber-50 text-amber-800";
  }

  return "border-zinc-200 bg-zinc-50 text-zinc-700";
}

export default function Home() {
  /**
   * Render the first static dashboard shell.
   *
   * Notes
   * -----
   * - This component does not use `use client`.
   * - It renders on the server by default in the App Router.
   * - It does not need React state yet.
   * - It should stay static until we add a real frontend data boundary.
   *
   * In plain language:
   *
   * - show the product shell
   * - show honest placeholder areas
   * - link to the real API health route
   */

  return (
    <main className="min-h-screen bg-[#f7f7f2] text-zinc-950">
      {/* 
        Page-width wrapper.
        - Keeps the dashboard readable on wide screens.
        - Adds consistent spacing around each major section.
      */}
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-10 px-6 py-8 sm:px-8 lg:px-10">
        {/* 
          Top-level product introduction.
          - This tells the user what the workspace is for.
          - The health link gives a real route they can use immediately.
        */}
        <header className="flex flex-col gap-6 border-b border-zinc-200 pb-8 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold uppercase text-emerald-700">
              James Joseph Associates
            </p>

            <h1 className="mt-3 text-4xl font-semibold leading-tight text-zinc-950 sm:text-5xl">
              Recruitment intelligence workspace
            </h1>

            <p className="mt-5 max-w-2xl text-lg leading-8 text-zinc-700">
              A focused workspace for candidate context, job matching, evidence
              review, and controlled workflow actions.
            </p>
          </div>

          {/* 
            Real backend smoke-check link.
            - This points to the FastAPI health endpoint we already built.
            - It keeps the first UI connected to a genuine backend capability.
          */}
          <a
            href="/api/v1/health"
            className="inline-flex h-11 w-fit items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
          >
            Check API health
          </a>
        </header>

        {/* 
          Main overview row.
          - Left side explains the current platform direction.
          - Right side shows the live API route and current backend status.
        */}
        <section className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white">
            {/* 
              The image gives the first screen a concrete workplace feel without
              pretending to show real candidates, jobs, or client data.
            */}
            <div
              className="min-h-72 bg-cover bg-center"
              style={{
                backgroundImage:
                  "url('https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1400&q=80')",
              }}
              aria-label="Modern office workspace"
            />

            <div className="p-6 sm:p-8">
              <p className="text-sm font-semibold uppercase text-zinc-500">
                Phase 1 foundation
              </p>

              <h2 className="mt-3 text-2xl font-semibold text-zinc-950">
                Backend-first intelligence platform
              </h2>

              <p className="mt-4 max-w-2xl text-base leading-7 text-zinc-700">
                The current foundation keeps the API, data model, workflow
                orchestration, and review experience separated so each part can
                grow without becoming tangled.
              </p>
            </div>
          </div>

          {/* 
            API status card.
            - This is not a deep readiness check yet.
            - It describes the shallow health endpoint that proves the app is routed.
          */}
          <aside className="rounded-lg border border-zinc-200 bg-white p-6 sm:p-8">
            <p className="text-sm font-semibold uppercase text-zinc-500">
              Live route
            </p>

            <h2 className="mt-3 text-2xl font-semibold text-zinc-950">
              API health endpoint
            </h2>

            <p className="mt-4 text-base leading-7 text-zinc-700">
              The backend currently exposes a shallow health check for Vercel
              deployment and route-registration checks.
            </p>

            <div className="mt-6 rounded-md border border-zinc-200 bg-zinc-50 p-4 font-mono text-sm text-zinc-800">
              GET /api/v1/health
            </div>

            <div className="mt-6 flex flex-wrap gap-2">
              <span className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-800">
                FastAPI live
              </span>
              <span className="rounded-md border border-sky-200 bg-sky-50 px-3 py-1 text-sm font-medium text-sky-800">
                Vercel routed
              </span>
            </div>
          </aside>
        </section>

        {/* 
          Future workspace areas.
          - These cards keep the UI honest by showing planned areas as planned.
          - No fake candidates, jobs, or recommendations are shown here.
        */}
        <section>
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
            <div>
              <p className="text-sm font-semibold uppercase text-zinc-500">
                Workspace areas
              </p>

              <h2 className="mt-3 text-3xl font-semibold text-zinc-950">
                Built around recruiter review
              </h2>
            </div>

            <p className="max-w-xl text-base leading-7 text-zinc-700">
              These areas are placeholders for the first product surface. They
              should become real once source data, entity schemas, and matching
              workflows are agreed.
            </p>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {workspaceSections.map((section) => (
              /*
                One planned workspace area.
                - The data comes from `workspaceSections` above.
                - Keeping this as mapped data makes it easy to add or rename
                  sections without duplicating the card layout.
              */
              <article
                key={section.title}
                className="rounded-lg border border-zinc-200 bg-white p-6"
              >
                <div className="flex items-start justify-between gap-4">
                  <h3 className="text-xl font-semibold text-zinc-950">
                    {section.title}
                  </h3>

                  <span
                    className={`shrink-0 rounded-md border px-3 py-1 text-xs font-semibold ${getSectionStateClass(
                      section.state,
                    )}`}
                  >
                    {section.state}
                  </span>
                </div>

                <p className="mt-4 text-base leading-7 text-zinc-700">
                  {section.description}
                </p>
              </article>
            ))}
          </div>
        </section>

        {/* 
          Foundation implementation map.
          - This gives a quick snapshot of what exists now.
          - It separates live foundation pieces from planned future work.
        */}
        <section className="rounded-lg border border-zinc-200 bg-white p-6 sm:p-8">
          <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
            <div>
              <p className="text-sm font-semibold uppercase text-zinc-500">
                Foundation status
              </p>

              <h2 className="mt-3 text-3xl font-semibold text-zinc-950">
                Current implementation map
              </h2>
            </div>

            <p className="max-w-xl text-base leading-7 text-zinc-700">
              The platform is still in the foundation stage. The active work is
              setting up reliable API structure, checks, and documentation
              before real recruitment data is introduced.
            </p>
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {foundationItems.map((item) => (
              /*
                One foundation capability row.
                - The badge colour comes from `getStatusClass`.
                - The text is static for now, not pulled from live monitoring.
              */
              <div
                key={item.label}
                className="flex min-h-20 items-center justify-between gap-4 rounded-md border border-zinc-200 bg-zinc-50 px-4"
              >
                <span className="font-medium text-zinc-900">{item.label}</span>

                <span
                  className={`rounded-md border px-3 py-1 text-xs font-semibold ${getStatusClass(
                    item.status,
                  )}`}
                >
                  {item.status}
                </span>
              </div>
            ))}
          </div>
        </section>
      </section>
    </main>
  );
}
