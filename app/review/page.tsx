import { headers } from "next/headers";

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
   *     GET /api/v1/review/overview?limit=10
   *
   * and returns one compact payload containing counts plus recent rows.
   */

  const baseUrl = await getBaseUrl();
  const response = await fetch(`${baseUrl}/api/v1/review/overview?limit=10`, {
    cache: "no-store",
  });

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
          className="rounded-md border border-zinc-200 bg-zinc-50 p-4"
        >
          <dl className="grid gap-2">
            {Object.entries(row).map(([key, value]) => (
              <div
                key={key}
                className="grid gap-1 sm:grid-cols-[11rem_1fr] sm:gap-4"
              >
                <dt className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
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

  const overview = await getReviewOverview();
  const counts = {
    people: overview.counts.people ?? 0,
    candidates: overview.counts.candidates ?? 0,
    jobs: overview.counts.jobs ?? 0,
    applications: overview.counts.applications ?? 0,
    documents: overview.counts.documents ?? 0,
    source_records: overview.counts.source_records ?? 0,
  };

  const countItems: Array<{ label: string; value: number }> = [
    { label: "People", value: counts.people },
    { label: "Candidates", value: counts.candidates },
    { label: "Jobs", value: counts.jobs },
    { label: "Applications", value: counts.applications },
    { label: "Documents", value: counts.documents },
    { label: "Source records", value: counts.source_records },
  ];

  return (
    <main className="min-h-screen bg-[#f7f7f2] text-zinc-950">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-8 sm:px-8 lg:px-10">
        <header className="flex flex-col gap-5 border-b border-zinc-200 pb-8 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold uppercase text-emerald-700">
              Internal review
            </p>
            <h1 className="mt-3 text-4xl font-semibold leading-tight text-zinc-950 sm:text-5xl">
              Supabase database overview
            </h1>
            <p className="mt-5 max-w-2xl text-lg leading-8 text-zinc-700">
              A compact read-only view of the canonical records, recent
              documents, and source provenance already stored in the system.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <a
              href="/api/v1/review/overview?limit=10"
              className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
            >
              Open raw JSON
            </a>
          </div>
        </header>

        <section>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {countItems.map((item) => (
              <article
                key={item.label}
                className="rounded-lg border border-zinc-200 bg-white p-6"
              >
                <p className="text-sm font-semibold uppercase text-zinc-500">
                  {item.label}
                </p>
                <p className="mt-4 text-4xl font-semibold text-zinc-950">
                  {item.value}
                </p>
              </article>
            ))}
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-2">
          <article className="rounded-lg border border-zinc-200 bg-white p-6">
            <h2 className="text-2xl font-semibold text-zinc-950">
              Recent candidates
            </h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              Most recently changed canonical candidates.
            </p>
            <div className="mt-5">{renderRows(overview.recent_candidates)}</div>
          </article>

          <article className="rounded-lg border border-zinc-200 bg-white p-6">
            <h2 className="text-2xl font-semibold text-zinc-950">Recent jobs</h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              Most recently changed canonical jobs.
            </p>
            <div className="mt-5">{renderRows(overview.recent_jobs)}</div>
          </article>

          <article className="rounded-lg border border-zinc-200 bg-white p-6">
            <h2 className="text-2xl font-semibold text-zinc-950">
              Recent applications
            </h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              Most recently changed canonical applications.
            </p>
            <div className="mt-5">
              {renderRows(overview.recent_applications)}
            </div>
          </article>

          <article className="rounded-lg border border-zinc-200 bg-white p-6">
            <h2 className="text-2xl font-semibold text-zinc-950">
              Recent documents
            </h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              Most recently changed canonical documents.
            </p>
            <div className="mt-5">{renderRows(overview.recent_documents)}</div>
          </article>

          <article className="rounded-lg border border-zinc-200 bg-white p-6">
            <h2 className="text-2xl font-semibold text-zinc-950">
              Document types
            </h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              Grouped counts for the document layer now landing in the
              canonical schema.
            </p>
            <div className="mt-5">
              {renderRows(overview.document_type_counts)}
            </div>
          </article>

          <article className="rounded-lg border border-zinc-200 bg-white p-6">
            <h2 className="text-2xl font-semibold text-zinc-950">
              Reconciliation status
            </h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              Grouped counts for auto-matched, newly created, and unresolved
              reconciliation decisions.
            </p>
            <div className="mt-5">
              {renderRows(overview.reconciliation_status_counts)}
            </div>
          </article>
        </section>

        <section className="grid gap-6 xl:grid-cols-2">
          <article className="rounded-lg border border-zinc-200 bg-white p-6">
            <h2 className="text-2xl font-semibold text-zinc-950">
              Source systems
            </h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              Grouped counts for the provenance rows behind each import source.
            </p>
            <div className="mt-5">
              {renderRows(overview.source_system_counts)}
            </div>
          </article>

          <article className="rounded-lg border border-zinc-200 bg-white p-6">
            <h2 className="text-2xl font-semibold text-zinc-950">
              Quality status
            </h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              Grouped counts for pass, review, and rerun resume outcomes.
            </p>
            <div className="mt-5">
              {renderRows(overview.quality_status_counts)}
            </div>
          </article>

          <article className="rounded-lg border border-zinc-200 bg-white p-6">
            <h2 className="text-2xl font-semibold text-zinc-950">
              Resume models
            </h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              Grouped counts for the final model used by persisted resume
              extractions.
            </p>
            <div className="mt-5">{renderRows(overview.resume_model_counts)}</div>
          </article>

          <article className="rounded-lg border border-zinc-200 bg-white p-6">
            <h2 className="text-2xl font-semibold text-zinc-950">
              Recent source records
            </h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              Provenance rows from Outlook, Dropbox, JobAdder, and future static
              imports.
            </p>
            <div className="mt-5">
              {renderRows(overview.recent_source_records)}
            </div>
          </article>

          <article className="rounded-lg border border-zinc-200 bg-white p-6">
            <h2 className="text-2xl font-semibold text-zinc-950">
              Recent scored resumes
            </h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              Recent canonical resume extractions with visible quality score,
              quality status, and final model metadata.
            </p>
            <div className="mt-5">
              {renderRows(overview.recent_scored_resumes)}
            </div>
          </article>

          <article className="rounded-lg border border-zinc-200 bg-white p-6">
            <h2 className="text-2xl font-semibold text-zinc-950">
              Reconciliation review
            </h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              Most recent reconciliation decisions, with unresolved matches
              pinned first for operator review.
            </p>
            <div className="mt-5">
              {renderRows(overview.recent_reconciliation_decisions)}
            </div>
          </article>
        </section>
      </section>
    </main>
  );
}
