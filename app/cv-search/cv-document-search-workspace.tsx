"use client";

import { FormEvent, useState } from "react";

type SourceDetail = {
  source_system: string;
  latest_record_received_at: string | null;
};

type DocumentSearchCoverage = {
  total_candidates: number;
  eligible_document_count: number;
  searchable_document_count: number;
  searched_document_count: number;
  excluded_missing_text_count: number;
  candidates_without_current_resume_count: number;
  matched_document_count: number;
  matched_candidate_count: number;
  coverage_status: "complete" | "complete_with_exclusions";
  is_exhaustive: boolean;
};

type DocumentSearchResult = {
  candidate_id: string;
  person_id: string;
  full_name: string | null;
  current_title: string | null;
  candidate_status: string | null;
  current_company_name: string | null;
  resume_updated_at: string | null;
  document_id: string;
  document_title: string | null;
  document_source_uri: string | null;
  match_score: number;
  match_excerpt: string | null;
  source_systems: string[];
  source_details: SourceDetail[];
  source_category: string;
  download_url: string;
};

type DocumentSearchResponse = {
  query: string;
  scope: "current_resume";
  page_size: number;
  returned_result_count: number;
  has_more: boolean;
  next_cursor: string | null;
  coverage: DocumentSearchCoverage;
  results: DocumentSearchResult[];
};

type ApiErrorPayload = {
  error?: {
    message?: string;
  };
};

const PAGE_SIZE = 50;
const HIGHLIGHT_PATTERN = /(<mark>.*?<\/mark>)/gi;
const MARK_TAG_PATTERN = /<\/?mark>/gi;

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "Not recorded";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      }).format(parsed);
}

function HighlightedExcerpt({ value }: { value: string | null }) {
  if (!value) {
    return <span>No evidence excerpt was returned.</span>;
  }
  return (
    <>
      {value.split(HIGHLIGHT_PATTERN).map((part, index) => {
        const isHighlighted = /^<mark>/i.test(part);
        const text = part.replace(MARK_TAG_PATTERN, "");
        return isHighlighted ? (
          <mark
            key={`${index}-${text}`}
            className="rounded bg-amber-200 px-1 text-amber-950"
          >
            {text}
          </mark>
        ) : (
          <span key={`${index}-${text}`}>{text}</span>
        );
      })}
    </>
  );
}

export function CvDocumentSearchWorkspace() {
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [response, setResponse] = useState<DocumentSearchResponse | null>(null);
  const [cursorHistory, setCursorHistory] = useState<(string | null)[]>([null]);
  const [pageIndex, setPageIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function loadPage(
    searchQuery: string,
    cursor: string | null,
    nextPageIndex: number,
    nextHistory: (string | null)[],
  ) {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const params = new URLSearchParams({
        query: searchQuery,
        page_size: String(PAGE_SIZE),
      });
      if (cursor) {
        params.set("cursor", cursor);
      }
      const apiResponse = await fetch(
        `/api/v1/candidates/search-documents?${params.toString()}`,
        { cache: "no-store" },
      );
      const payload = (await apiResponse.json()) as
        | DocumentSearchResponse
        | ApiErrorPayload;
      if (!apiResponse.ok) {
        throw new Error(
          "error" in payload
            ? payload.error?.message ?? "The CV search could not complete."
            : "The CV search could not complete.",
        );
      }
      setResponse(payload as DocumentSearchResponse);
      setActiveQuery(searchQuery);
      setPageIndex(nextPageIndex);
      setCursorHistory(nextHistory);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "The CV search could not complete.",
      );
    } finally {
      setIsLoading(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedQuery = query.trim();
    if (!normalizedQuery) {
      setErrorMessage("Enter at least one keyword or phrase.");
      return;
    }
    void loadPage(normalizedQuery, null, 0, [null]);
  }

  function loadNextPage() {
    if (!response?.next_cursor) {
      return;
    }
    const nextHistory = [
      ...cursorHistory.slice(0, pageIndex + 1),
      response.next_cursor,
    ];
    void loadPage(
      activeQuery,
      response.next_cursor,
      pageIndex + 1,
      nextHistory,
    );
  }

  function loadPreviousPage() {
    if (pageIndex === 0) {
      return;
    }
    const previousPageIndex = pageIndex - 1;
    void loadPage(
      activeQuery,
      cursorHistory[previousPageIndex] ?? null,
      previousPageIndex,
      cursorHistory,
    );
  }

  const exportHref = activeQuery
    ? `/api/v1/candidates/search-documents/export?${new URLSearchParams({
        query: activeQuery,
      }).toString()}`
    : null;

  return (
    <section className="grid gap-6" aria-labelledby="cv-search-title">
      <div className="workspace-card grid gap-6 p-6 sm:p-8">
        <div className="max-w-4xl">
          <p className="text-xs font-bold uppercase tracking-[0.17em] text-[#0d6b6d]">
            Deterministic database search
          </p>
          <h2
            id="cv-search-title"
            className="mt-3 text-3xl font-semibold tracking-[-0.035em] text-[#071b2a]"
          >
            Search inside every current CV
          </h2>
          <p className="mt-4 text-base leading-7 text-slate-600">
            This searches the complete extracted text of every searchable current
            CV. It does not use an LLM, hide matches behind a top-five ranking, or
            charge per document.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="grid gap-4">
          <label htmlFor="cv-document-query" className="text-sm font-bold text-slate-800">
            Keywords, phrase, or Boolean search
          </label>
          <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
            <input
              id="cv-document-query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={'Example: "securities lending" OR SFTR OR repo'}
              className="min-h-12 rounded-xl border border-slate-300 bg-white px-4 text-base text-slate-950 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-[#2859e8] focus:ring-4 focus:ring-blue-100"
              maxLength={4000}
              autoComplete="off"
            />
            <button
              type="submit"
              className="app-primary-action min-h-12 px-6 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={isLoading}
            >
              {isLoading ? "Searching all CVs…" : "Search all current CVs"}
            </button>
          </div>
          <p className="text-sm leading-6 text-slate-500">
            Use quotation marks for an exact phrase, uppercase <strong>OR</strong>{" "}
            for alternatives, and a minus sign to exclude a term—for example:{" "}
            <code className="rounded bg-slate-100 px-1.5 py-1 text-xs text-slate-800">
              &quot;securities lending&quot; OR SFTR -intern
            </code>
          </p>
        </form>

        <div aria-live="polite">
          {errorMessage ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-900">
              {errorMessage}
            </div>
          ) : null}
        </div>
      </div>

      {response ? (
        <>
          <section className="workspace-card grid gap-5 p-6 sm:p-8" aria-label="Search coverage">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0d6b6d]">
                  Coverage report
                </p>
                <h3 className="mt-2 text-2xl font-semibold text-[#071b2a]">
                  {response.coverage.matched_candidate_count.toLocaleString("en-GB")} matching candidates
                </h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Across {response.coverage.matched_document_count.toLocaleString("en-GB")} matching CV documents. Query:{" "}
                  <span className="font-semibold text-slate-900">{response.query}</span>
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <span
                  className={`inline-flex min-h-10 items-center rounded-full px-4 text-xs font-bold uppercase tracking-[0.1em] ${
                    response.coverage.is_exhaustive
                      ? "bg-emerald-100 text-emerald-900"
                      : "bg-amber-100 text-amber-950"
                  }`}
                >
                  {response.coverage.is_exhaustive
                    ? "Exhaustive coverage"
                    : "Complete with exclusions"}
                </span>
                {exportHref ? (
                  <a href={exportHref} className="app-secondary-action min-h-10 px-4">
                    Export every match as CSV
                  </a>
                ) : null}
              </div>
            </div>

            <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
              {[
                ["Current CVs", response.coverage.eligible_document_count],
                ["Searched", response.coverage.searched_document_count],
                ["Matching candidates", response.coverage.matched_candidate_count],
                ["Matching CVs", response.coverage.matched_document_count],
                ["Missing text", response.coverage.excluded_missing_text_count],
                ["Profiles without CV", response.coverage.candidates_without_current_resume_count],
              ].map(([label, value]) => (
                <div key={String(label)} className="workspace-kpi p-4">
                  <dt className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">
                    {label}
                  </dt>
                  <dd className="mt-2 text-2xl font-semibold text-[#071b2a]">
                    {Number(value).toLocaleString("en-GB")}
                  </dd>
                </div>
              ))}
            </dl>

            {!response.coverage.is_exhaustive ? (
              <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
                Every current-CV record has been accounted for, but{" "}
                {response.coverage.excluded_missing_text_count.toLocaleString("en-GB")} document(s)
                could not be searched because extracted text is missing. The result is not labelled
                exhaustive until that gap is repaired.
              </p>
            ) : null}
          </section>

          <section className="grid gap-4" aria-label="Matching CVs">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm font-semibold text-slate-700">
                Page {pageIndex + 1} · showing {response.returned_result_count} result(s)
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={loadPreviousPage}
                  disabled={pageIndex === 0 || isLoading}
                  className="app-secondary-action min-h-10 px-4 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Previous
                </button>
                <button
                  type="button"
                  onClick={loadNextPage}
                  disabled={!response.has_more || isLoading}
                  className="app-secondary-action min-h-10 px-4 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>

            {response.results.length > 0 ? (
              <div className="grid gap-4">
                {response.results.map((result) => (
                  <article key={result.document_id} className="workspace-card p-5 sm:p-6">
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <p className="text-xs font-bold uppercase tracking-[0.13em] text-[#0d6b6d]">
                          Full-text match · score {result.match_score.toFixed(4)}
                        </p>
                        <h3 className="mt-2 text-xl font-semibold text-[#071b2a]">
                          {result.full_name ?? "Unnamed candidate"}
                        </h3>
                        <p className="mt-1 text-sm leading-6 text-slate-600">
                          {result.current_title ?? "Title unavailable"}
                          {result.current_company_name
                            ? ` at ${result.current_company_name}`
                            : ""}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <a href={result.download_url} className="app-primary-action min-h-10 px-4">
                          Open current CV
                        </a>
                        <a
                          href={`/api/v1/candidates/${result.candidate_id}/profile`}
                          className="app-secondary-action min-h-10 px-4"
                        >
                          Open profile
                        </a>
                      </div>
                    </div>

                    <blockquote className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm leading-7 text-slate-800">
                      <HighlightedExcerpt value={result.match_excerpt} />
                    </blockquote>

                    <dl className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      <div>
                        <dt className="text-xs font-bold uppercase tracking-[0.1em] text-slate-400">
                          Original filename
                        </dt>
                        <dd className="mt-1 break-words text-sm text-slate-800">
                          {result.document_title ?? "Not recorded"}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs font-bold uppercase tracking-[0.1em] text-slate-400">
                          CV updated
                        </dt>
                        <dd className="mt-1 text-sm text-slate-800">
                          {formatTimestamp(result.resume_updated_at)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs font-bold uppercase tracking-[0.1em] text-slate-400">
                          Provenance
                        </dt>
                        <dd className="mt-1 text-sm text-slate-800">
                          {result.source_systems.length > 0
                            ? result.source_systems.join(", ")
                            : "CV-backed source"}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs font-bold uppercase tracking-[0.1em] text-slate-400">
                          Candidate ID
                        </dt>
                        <dd className="mt-1 break-all font-mono text-xs text-slate-700">
                          {result.candidate_id}
                        </dd>
                      </div>
                    </dl>
                  </article>
                ))}
              </div>
            ) : (
              <div className="workspace-empty p-8 text-center text-sm leading-7 text-slate-600">
                No current CV contains every required term in this query. Try using uppercase OR
                between alternatives or remove an exclusion.
              </div>
            )}
          </section>
        </>
      ) : null}
    </section>
  );
}
