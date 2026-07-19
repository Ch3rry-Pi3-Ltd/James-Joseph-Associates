import { headers } from "next/headers";
import { requireAuthorizedUser } from "@/lib/auth";

const REVIEW_OVERVIEW_LIMIT = 3;

type ReviewCounts = {
  people: number;
  candidates: number;
  jobs: number;
  applications: number;
  documents: number;
  source_records: number;
};

type ReviewOverview = {
  counts: Partial<ReviewCounts>;
  recent_candidates: Array<Record<string, unknown>>;
  recent_jobs: Array<Record<string, unknown>>;
  recent_applications: Array<Record<string, unknown>>;
  recent_documents: Array<Record<string, unknown>>;
  recent_source_records: Array<Record<string, unknown>>;
  recent_reconciliation_decisions: Array<Record<string, unknown>>;
  recent_scored_resumes: Array<Record<string, unknown>>;
  document_type_counts: Array<Record<string, unknown>>;
  source_system_counts: Array<Record<string, unknown>>;
  quality_status_counts: Array<Record<string, unknown>>;
  resume_model_counts: Array<Record<string, unknown>>;
  reconciliation_status_counts: Array<Record<string, unknown>>;
};

type CountItem = {
  label: string;
  value: number;
  accentClassName: string;
};

type ReviewSection = {
  eyebrow: string;
  title: string;
  description: string;
  rows: Array<Record<string, unknown>>;
};

function formatValue(value: unknown): string {
  /*
    Keep the first review page readable without pretending we already have
    polished field-specific formatting for every canonical table.

    The first operator need is simple:
    - show nulls clearly
    - avoid "[object Object]"
    - keep timestamps, IDs, and URIs visible as plain strings
  */
  if (value === null || value === undefined) {
    return "-";
  }

  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }

  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }

  return JSON.stringify(value);
}

async function getBaseUrl(): Promise<string> {
  /**
   * Build the current request origin for same-deployment API reads.
   *
   * Returns
   * -------
   * str
   *     Base URL for the current request, such as the local dev server origin
   *     or the deployed Vercel origin.
   *
   * Notes
   * -----
   * - The review page is a Server Component, so it can read incoming headers.
   * - We use those headers to fetch the Python backend route on the same
   *   deployment rather than hardcoding one environment-specific base URL.
   * - This keeps local dev and Vercel production aligned.
   *
   * Example
   * -------
   * On production, this should return something like:
   *
   *     https://james-joseph-associates.vercel.app
   */

  const requestHeaders = await headers();
  const host =
    requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host");

  if (!host) {
    return "http://localhost:3000";
  }

  const forwardedProto = requestHeaders.get("x-forwarded-proto");

  if (forwardedProto === "http" || forwardedProto === "https") {
    return `${forwardedProto}://${host}`;
  }

  const protocol =
    host.startsWith("localhost") || host.startsWith("127.0.0.1")
      ? "http"
      : "https";

  return `${protocol}://${host}`;
}

async function getReviewOverview(): Promise<ReviewOverview> {
  /**
   * Read the compact review payload from the backend API.
   *
   * Returns
   * -------
   * ReviewOverview
   *     Compact operator-facing payload containing counts plus recent rows from
   *     the canonical tables.
   *
   * Notes
   * -----
   * - The page deliberately uses the public backend route instead of embedding
   *   direct database logic in the Next.js app.
   * - `cache: "no-store"` keeps this page honest while we are still using it
   *   as an operator review surface during active ingestion work.
   *
   * Example
   * -------
   * A successful request reads:
   *
   *     GET /api/v1/review/overview?limit=3
   *
   * and returns one compact payload containing counts plus recent rows.
   */

  const baseUrl = await getBaseUrl();
  const requestHeaders = await headers();
  const forwardedHeaders = new Headers();

  const cookieHeader = requestHeaders.get("cookie");
  const authorizationHeader = requestHeaders.get("authorization");

  if (cookieHeader) {
    forwardedHeaders.set("cookie", cookieHeader);
  }

  if (authorizationHeader) {
    forwardedHeaders.set("authorization", authorizationHeader);
  }

  const response = await fetch(
    `${baseUrl}/api/v1/review/overview?limit=${REVIEW_OVERVIEW_LIMIT}`,
    {
    cache: "no-store",
    headers: forwardedHeaders,
    },
  );

  if (!response.ok) {
    throw new Error(`Review overview request failed with ${response.status}.`);
  }

  return (await response.json()) as ReviewOverview;
}

function renderRows(rows: Array<Record<string, unknown>>) {
  /*
    The review page is intentionally generic for the first pass.

    That means each section can render a row dictionary without needing custom
    components for jobs, candidates, documents, and source records yet.

    This is deliberate:
    - it lets us inspect real data quickly
    - it avoids inventing per-entity UI assumptions too early
    - it keeps the first review surface useful while the import model is still
      moving
  */
  const nonEmptyRows = rows.filter((row) => Object.keys(row).length > 0);

  if (nonEmptyRows.length === 0) {
    return <p className="text-sm leading-6 text-zinc-600">No rows yet.</p>;
  }

  return (
    <div className="grid gap-3">
      {nonEmptyRows.map((row, index) => (
        <div
          key={`${index}-${Object.values(row).join("-")}`}
          className="rounded-md border border-zinc-200/80 bg-[linear-gradient(180deg,#ffffff_0%,#f7f8f7_100%)] p-4 shadow-[0_12px_30px_rgba(15,23,42,0.05)]"
        >
          <dl className="grid gap-2">
            {Object.entries(row).map(([key, value]) => (
              <div
                key={key}
                className="grid gap-1 sm:grid-cols-[11rem_1fr] sm:gap-4"
              >
                <dt className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-500">
                  {key.replaceAll("_", " ")}
                </dt>
                <dd className="break-words text-sm leading-6 text-zinc-900">
                  {formatValue(value)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}

function renderSection(section: ReviewSection) {
  return (
    <article className="grid gap-5 rounded-md border border-zinc-200/80 bg-white p-6 shadow-[0_18px_45px_rgba(15,23,42,0.06)]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-zinc-200/80 pb-4">
        <div className="max-w-2xl">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700">
            {section.eyebrow}
          </p>
          <h2 className="mt-2 text-2xl font-semibold leading-tight text-zinc-950">
            {section.title}
          </h2>
          <p className="mt-2 text-sm leading-6 text-zinc-600">
            {section.description}
          </p>
        </div>
        <div className="rounded-md border border-emerald-300/50 bg-emerald-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-emerald-800">
          Top {REVIEW_OVERVIEW_LIMIT}
        </div>
      </div>

      {renderRows(section.rows)}
    </article>
  );
}

export default async function ReviewPage() {
  /**
   * Render the first operator-facing Supabase review page.
   *
   * Notes
   * -----
   * - This is a Server Component.
   * - It reads the review payload on the server before rendering.
   * - The page stays read-only on purpose; it is an inspection surface, not an
   *   admin console yet.
   *
   * Example
   * -------
   * Visiting `/review` should show:
   *
 * - headline canonical counts
 * - recent candidates
 * - recent jobs
 * - recent applications
 * - recent documents
   * - recent source provenance rows
   * - grouped document-type counts
   * - recent scored resumes with quality/model metadata
   * - grouped source-system counts
   * - grouped quality-status counts
   * - grouped model-name counts
   * - recent reconciliation decisions
   * - grouped reconciliation-status counts
   *
   * In plain language:
   *
   * - show what is currently in the canonical database
   * - keep it read-only
   * - make it useful before we build a fuller ingestion console
   */

  await requireAuthorizedUser();

  const overview = await getReviewOverview();
  const counts = {
    people: overview.counts.people ?? 0,
    candidates: overview.counts.candidates ?? 0,
    jobs: overview.counts.jobs ?? 0,
    applications: overview.counts.applications ?? 0,
    documents: overview.counts.documents ?? 0,
    source_records: overview.counts.source_records ?? 0,
  };

  const countItems: CountItem[] = [
    {
      label: "People",
      value: counts.people,
      accentClassName: "from-emerald-400 via-cyan-400 to-sky-500",
    },
    {
      label: "Candidates",
      value: counts.candidates,
      accentClassName: "from-teal-400 via-emerald-400 to-lime-400",
    },
    {
      label: "Jobs",
      value: counts.jobs,
      accentClassName: "from-sky-400 via-cyan-400 to-blue-500",
    },
    {
      label: "Applications",
      value: counts.applications,
      accentClassName: "from-amber-400 via-orange-400 to-rose-400",
    },
    {
      label: "Documents",
      value: counts.documents,
      accentClassName: "from-violet-400 via-fuchsia-400 to-pink-400",
    },
    {
      label: "Source records",
      value: counts.source_records,
      accentClassName: "from-zinc-500 via-zinc-400 to-zinc-300",
    },
  ];

  const coreSections: ReviewSection[] = [
    {
      eyebrow: "Candidates",
      title: "Recent candidates",
      description: "Most recently changed canonical candidates.",
      rows: overview.recent_candidates,
    },
    {
      eyebrow: "Jobs",
      title: "Recent jobs",
      description: "Most recently changed canonical jobs.",
      rows: overview.recent_jobs,
    },
    {
      eyebrow: "Applications",
      title: "Recent applications",
      description: "Most recently changed canonical applications.",
      rows: overview.recent_applications,
    },
    {
      eyebrow: "Documents",
      title: "Recent documents",
      description: "Most recently changed canonical documents.",
      rows: overview.recent_documents,
    },
  ];

  const qualitySections: ReviewSection[] = [
    {
      eyebrow: "Types",
      title: "Document types",
      description: "Grouped counts for the document layer now landing in the canonical schema.",
      rows: overview.document_type_counts,
    },
    {
      eyebrow: "Sources",
      title: "Source systems",
      description: "Grouped counts for the provenance rows behind each import source.",
      rows: overview.source_system_counts,
    },
    {
      eyebrow: "Quality",
      title: "Quality status",
      description: "Grouped counts for pass, review, and rerun resume outcomes.",
      rows: overview.quality_status_counts,
    },
    {
      eyebrow: "Models",
      title: "Resume models",
      description: "Grouped counts for the final model used by persisted resume extractions.",
      rows: overview.resume_model_counts,
    },
  ];

  const opsSections: ReviewSection[] = [
    {
      eyebrow: "Provenance",
      title: "Recent source records",
      description: "Recent Outlook, Dropbox, JobAdder, Recruitly, and static import provenance rows.",
      rows: overview.recent_source_records,
    },
    {
      eyebrow: "Scored",
      title: "Recent scored resumes",
      description: "Recent canonical resume extractions with visible quality score, quality status, and model metadata.",
      rows: overview.recent_scored_resumes,
    },
    {
      eyebrow: "Reconciliation",
      title: "Reconciliation review",
      description: "Most recent reconciliation decisions, with unresolved matches surfaced first.",
      rows: overview.recent_reconciliation_decisions,
    },
    {
      eyebrow: "Status",
      title: "Reconciliation status",
      description: "Grouped counts for auto-matched, newly created, and unresolved reconciliation decisions.",
      rows: overview.reconciliation_status_counts,
    },
  ];

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#eef1ec_0%,#f6f6f1_40%,#fbfbf8_100%)] text-zinc-950">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-10 px-6 py-8 sm:px-8 lg:px-10">
        <header className="grid gap-6 rounded-md border border-zinc-900 bg-[#101714] px-6 py-8 text-white shadow-[0_24px_60px_rgba(15,23,42,0.18)] sm:px-8 lg:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)] lg:px-10 lg:py-10">
          <div className="max-w-4xl">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-emerald-300">
              Internal review
            </p>
            <h1 className="mt-4 text-4xl font-semibold leading-tight text-white sm:text-5xl">
              Canonical data control room
            </h1>
            <p className="mt-5 max-w-3xl text-lg leading-8 text-zinc-200">
              Inspect what has landed, check recent movement across the canonical
              layer, and verify provenance without dropping into raw tables.
            </p>
          </div>

          <div className="grid content-start gap-4 rounded-md border border-white/10 bg-white/6 p-5">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-300">
                Operator surface
              </p>
              <p className="mt-2 text-2xl font-semibold text-white">
                Read-only inspection
              </p>
            </div>
            <div className="grid gap-3 rounded-md border border-white/10 bg-black/15 p-4">
              <div className="flex items-center justify-between gap-4 text-sm text-zinc-200">
                <span>Initial slice size</span>
                <span className="font-semibold text-white">
                  {REVIEW_OVERVIEW_LIMIT} rows
                </span>
              </div>
              <div className="flex items-center justify-between gap-4 text-sm text-zinc-200">
                <span>Page mode</span>
                <span className="font-semibold text-white">Live snapshot</span>
              </div>
              <div className="flex items-center justify-between gap-4 text-sm text-zinc-200">
                <span>Data source</span>
                <span className="font-semibold text-white">Canonical DB</span>
              </div>
            </div>
            <a
              href={`/api/v1/review/overview?limit=${REVIEW_OVERVIEW_LIMIT}`}
              className="inline-flex h-11 items-center justify-center rounded-md border border-white/20 px-4 text-sm font-semibold text-white transition hover:bg-white/8"
            >
              Open raw JSON
            </a>
          </div>
        </header>

        <section className="grid gap-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Snapshot
              </p>
              <h2 className="mt-2 text-3xl font-semibold leading-tight text-zinc-950">
                Current canonical footprint
              </h2>
            </div>
            <p className="max-w-2xl text-sm leading-6 text-zinc-600">
              The review tab should answer two questions quickly: what is in the
              system now, and what changed most recently.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {countItems.map((item) => (
              <article
                key={item.label}
                className="relative overflow-hidden rounded-md border border-zinc-200/80 bg-white p-6 shadow-[0_18px_45px_rgba(15,23,42,0.06)]"
              >
                <div
                  className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${item.accentClassName}`}
                />
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                  {item.label}
                </p>
                <p className="mt-4 text-4xl font-semibold tracking-tight text-zinc-950">
                  {item.value}
                </p>
              </article>
            ))}
          </div>
        </section>

        <section className="grid gap-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Recent movement
              </p>
              <h2 className="mt-2 text-3xl font-semibold leading-tight text-zinc-950">
                Core entity activity
              </h2>
            </div>
            <p className="max-w-2xl text-sm leading-6 text-zinc-600">
              The most recent rows across candidates, jobs, applications, and
              documents.
            </p>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            {coreSections.map((section) => renderSection(section))}
          </div>
        </section>

        <section className="grid gap-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Quality and provenance
              </p>
              <h2 className="mt-2 text-3xl font-semibold leading-tight text-zinc-950">
                Source and extraction health
              </h2>
            </div>
            <p className="max-w-2xl text-sm leading-6 text-zinc-600">
              Counts and grouped views that show what kinds of records are
              landing, which sources are driving them, and how cleanly resumes
              are extracting.
            </p>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            {qualitySections.map((section) => renderSection(section))}
          </div>
        </section>

        <section className="grid gap-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Operations
              </p>
              <h2 className="mt-2 text-3xl font-semibold leading-tight text-zinc-950">
                Reconciliation and traceability
              </h2>
            </div>
            <p className="max-w-2xl text-sm leading-6 text-zinc-600">
              Provenance rows, scored resumes, and reconciliation signals for
              operator follow-up.
            </p>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            {opsSections.map((section) => renderSection(section))}
          </div>
        </section>
      </section>
    </main>
  );
}
