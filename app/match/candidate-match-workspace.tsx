"use client";

import { FormEvent, ReactNode, useMemo, useState } from "react";

type CandidateResumeSearchResult = {
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
};

type CandidateResumeSearchResponse = {
  query: string;
  limit: number;
  results: CandidateResumeSearchResult[];
};

type CandidateJobDescriptionShortlistItem = {
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
  retrieval_score: number;
  fit_score: number;
  fit_summary: string;
  strengths: string[];
  gaps: string[];
  match_excerpt: string | null;
};

type CandidateJobDescriptionMatchResponse = {
  job_description: string;
  retrieval_limit: number;
  shortlist_limit: number;
  retrieved_candidate_count: number;
  shortlisted_candidates: CandidateJobDescriptionShortlistItem[];
};

type ApiErrorResponse = {
  error?: {
    code?: string;
    message?: string;
    details?: Array<Record<string, unknown>>;
  };
};

const DEFAULT_JOB_DESCRIPTION = `Senior data engineer with strong Python, SQL, cloud platform, and ETL experience. Ideally someone who has worked with large datasets, modern data pipelines, and production analytics systems.`;

function isApiErrorResponse(payload: unknown): payload is ApiErrorResponse {
  if (typeof payload !== "object" || payload === null) {
    return false;
  }

  return "error" in payload;
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "Unknown";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderHighlightedExcerpt(excerpt: string | null): ReactNode {
  if (!excerpt || excerpt.trim() === "") {
    return "No excerpt available.";
  }

  const parts = excerpt.split(/(<mark>|<\/mark>)/);
  let isHighlighted = false;

  return parts
    .filter((part) => part !== "")
    .map((part, index) => {
      if (part === "<mark>") {
        isHighlighted = true;
        return null;
      }

      if (part === "</mark>") {
        isHighlighted = false;
        return null;
      }

      if (isHighlighted) {
        return (
          <mark
            key={`excerpt-${index}`}
            className="rounded bg-emerald-100 px-1 text-zinc-950"
          >
            {part}
          </mark>
        );
      }

      return <span key={`excerpt-${index}`}>{part}</span>;
    });
}

export function CandidateMatchWorkspace() {
  const [jobDescription, setJobDescription] = useState(DEFAULT_JOB_DESCRIPTION);
  const [searchResultLimit, setSearchResultLimit] = useState("10");
  const [retrievalLimit, setRetrievalLimit] = useState("25");
  const [shortlistLimit, setShortlistLimit] = useState("3");
  const [isSearchLoading, setIsSearchLoading] = useState(false);
  const [isShortlistLoading, setIsShortlistLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<CandidateResumeSearchResult[]>(
    [],
  );
  const [shortlistResults, setShortlistResults] = useState<
    CandidateJobDescriptionShortlistItem[]
  >([]);
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);
  const [retrievedCandidateCount, setRetrievedCandidateCount] = useState(0);

  const searchResultCountLabel = useMemo(() => {
    if (searchResults.length === 0) {
      return "No candidates returned yet.";
    }

    if (searchResults.length === 1) {
      return "1 search result returned.";
    }

    return `${searchResults.length} search results returned.`;
  }, [searchResults.length]);

  const shortlistCountLabel = useMemo(() => {
    if (shortlistResults.length === 0) {
      return "No shortlist returned yet.";
    }

    if (shortlistResults.length === 1) {
      return "1 shortlisted candidate.";
    }

    return `${shortlistResults.length} shortlisted candidates.`;
  }, [shortlistResults.length]);

  async function runSearch(): Promise<void> {
    const trimmedDescription = jobDescription.trim();
    if (trimmedDescription === "") {
      setErrorMessage("Paste a job description before running the search.");
      setSearchResults([]);
      setShortlistResults([]);
      return;
    }

    setIsSearchLoading(true);
    setErrorMessage(null);

    try {
      const searchParams = new URLSearchParams({
        query: trimmedDescription,
        limit: searchResultLimit,
      });

      const response = await fetch(
        `/api/v1/candidates/search-resumes?${searchParams.toString()}`,
        {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
        },
      );

      const payload = (await response.json()) as unknown;

      if (!response.ok) {
        setSearchResults([]);
        setSubmittedQuery(trimmedDescription);
        setErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Search request failed with ${response.status}.`,
        );
        return;
      }

      const searchResponse = payload as CandidateResumeSearchResponse;
      setSearchResults(searchResponse.results);
      setSubmittedQuery(searchResponse.query);
    } catch (error) {
      setSearchResults([]);
      setSubmittedQuery(trimmedDescription);
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Search request failed unexpectedly.",
      );
    } finally {
      setIsSearchLoading(false);
    }
  }

  async function runShortlist(): Promise<void> {
    const trimmedDescription = jobDescription.trim();
    if (trimmedDescription === "") {
      setErrorMessage("Paste a job description before requesting a shortlist.");
      setShortlistResults([]);
      return;
    }

    setIsShortlistLoading(true);
    setErrorMessage(null);

    try {
      const response = await fetch("/api/v1/candidates/match-job-description", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          job_description: trimmedDescription,
          retrieval_limit: Number(retrievalLimit),
          shortlist_limit: Number(shortlistLimit),
        }),
      });

      const payload = (await response.json()) as unknown;

      if (!response.ok) {
        setShortlistResults([]);
        setSubmittedQuery(trimmedDescription);
        setErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Shortlist request failed with ${response.status}.`,
        );
        return;
      }

      const shortlistResponse = payload as CandidateJobDescriptionMatchResponse;
      setShortlistResults(shortlistResponse.shortlisted_candidates);
      setRetrievedCandidateCount(shortlistResponse.retrieved_candidate_count);
      setSubmittedQuery(shortlistResponse.job_description);
    } catch (error) {
      setShortlistResults([]);
      setSubmittedQuery(trimmedDescription);
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Shortlist request failed unexpectedly.",
      );
    } finally {
      setIsShortlistLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runSearch();
  }

  return (
    <div className="grid gap-8">
      <section className="border border-zinc-200 bg-white p-6 sm:p-8">
        <form className="grid gap-6" onSubmit={handleSubmit}>
          <div className="grid gap-3">
            <label
              className="text-sm font-semibold uppercase text-zinc-500"
              htmlFor="job-description"
            >
              Job description
            </label>

            <textarea
              id="job-description"
              value={jobDescription}
              onChange={(event) => setJobDescription(event.target.value)}
              className="min-h-72 rounded-md border border-zinc-300 bg-white px-4 py-3 text-base leading-7 text-zinc-950 outline-none transition focus:border-zinc-500"
              placeholder="Paste the role brief here."
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-[1fr_auto] xl:items-end">
            <div className="grid gap-4 md:grid-cols-3">
              <div className="grid gap-3">
                <label
                  className="text-sm font-semibold uppercase text-zinc-500"
                  htmlFor="search-result-limit"
                >
                  Search mode
                </label>
                <div className="flex items-center gap-3">
                  <label
                    className="text-sm font-medium text-zinc-700"
                    htmlFor="search-result-limit"
                  >
                    Results
                  </label>
                  <select
                    id="search-result-limit"
                    value={searchResultLimit}
                    onChange={(event) => setSearchResultLimit(event.target.value)}
                    className="h-11 rounded-md border border-zinc-300 bg-white px-3 text-sm text-zinc-950 outline-none transition focus:border-zinc-500"
                  >
                    <option value="5">Top 5</option>
                    <option value="10">Top 10</option>
                    <option value="20">Top 20</option>
                  </select>
                </div>
              </div>

              <div className="grid gap-3">
                <label
                  className="text-sm font-semibold uppercase text-zinc-500"
                  htmlFor="retrieval-limit"
                >
                  Shortlist mode
                </label>
                <div className="flex items-center gap-3">
                  <label
                    className="text-sm font-medium text-zinc-700"
                    htmlFor="retrieval-limit"
                  >
                    Candidate pool
                  </label>
                  <select
                    id="retrieval-limit"
                    value={retrievalLimit}
                    onChange={(event) => setRetrievalLimit(event.target.value)}
                    className="h-11 rounded-md border border-zinc-300 bg-white px-3 text-sm text-zinc-950 outline-none transition focus:border-zinc-500"
                  >
                    <option value="10">Top 10</option>
                    <option value="25">Top 25</option>
                    <option value="50">Top 50</option>
                  </select>
                </div>
              </div>

              <div className="grid gap-3">
                <label
                  className="text-sm font-semibold uppercase text-zinc-500"
                  htmlFor="shortlist-limit"
                >
                  Final shortlist
                </label>
                <div className="flex items-center gap-3">
                  <label
                    className="text-sm font-medium text-zinc-700"
                    htmlFor="shortlist-limit"
                  >
                    Candidates
                  </label>
                  <select
                    id="shortlist-limit"
                    value={shortlistLimit}
                    onChange={(event) => setShortlistLimit(event.target.value)}
                    className="h-11 rounded-md border border-zinc-300 bg-white px-3 text-sm text-zinc-950 outline-none transition focus:border-zinc-500"
                  >
                    <option value="3">Top 3</option>
                    <option value="5">Top 5</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                type="submit"
                disabled={isSearchLoading || isShortlistLoading}
                className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-5 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500 disabled:cursor-not-allowed disabled:border-zinc-300 disabled:bg-zinc-200"
              >
                {isSearchLoading ? "Searching..." : "Search corpus"}
              </button>

              <button
                type="button"
                disabled={isSearchLoading || isShortlistLoading}
                onClick={() => {
                  void runShortlist();
                }}
                className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-950 bg-zinc-950 px-5 text-sm font-semibold text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:border-zinc-300 disabled:bg-zinc-300"
              >
                {isShortlistLoading
                  ? "Shortlisting..."
                  : `Shortlist top ${shortlistLimit}`}
              </button>
            </div>
          </div>
        </form>
      </section>

      <section className="grid gap-6">
        <div className="flex flex-col gap-3 border-b border-zinc-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-3xl font-semibold text-zinc-950">
              Recruiter shortlist
            </h2>
            <p className="mt-2 max-w-3xl text-base leading-7 text-zinc-700">
              Top candidates selected after retrieval plus LLM reranking against
              the supplied role brief.
            </p>
          </div>

          <div className="text-sm text-zinc-600">
            {submittedQuery ? shortlistCountLabel : "Run shortlist to see the top fit."}
          </div>
        </div>

        {submittedQuery && retrievedCandidateCount > 0 ? (
          <p className="text-sm leading-6 text-zinc-600">
            Retrieved {retrievedCandidateCount} candidates for reranking.
          </p>
        ) : null}

        {errorMessage ? (
          <div className="border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
            {errorMessage}
          </div>
        ) : null}

        {shortlistResults.length === 0 && !errorMessage ? (
          <div className="border border-dashed border-zinc-300 p-6 text-sm leading-7 text-zinc-600">
            Paste a role brief and use the shortlist action to produce the top
            candidates, not just raw search results.
          </div>
        ) : null}

        <div className="grid gap-5">
          {shortlistResults.map((result, index) => (
            <article
              key={`${result.candidate_id}-${result.document_id}`}
              className="border border-zinc-200 bg-white p-6"
            >
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-3xl">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800">
                      Rank {index + 1}
                    </span>
                    <span className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700">
                      Fit {result.fit_score}/100
                    </span>
                    <span className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700">
                      Retrieval {result.retrieval_score.toFixed(3)}
                    </span>
                  </div>

                  <h3 className="mt-4 text-2xl font-semibold text-zinc-950">
                    {result.full_name ?? "Unnamed candidate"}
                  </h3>

                  <p className="mt-2 text-base leading-7 text-zinc-700">
                    {result.current_title ?? "Title not available"}
                    {result.current_company_name
                      ? ` at ${result.current_company_name}`
                      : ""}
                  </p>

                  <p className="mt-4 text-base leading-7 text-zinc-900">
                    {result.fit_summary}
                  </p>
                </div>

                <a
                  href={`/api/v1/candidates/${result.candidate_id}/profile`}
                  className="inline-flex h-11 w-fit items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                >
                  Open profile JSON
                </a>
              </div>

              <dl className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <div>
                  <dt className="text-xs font-semibold uppercase text-zinc-500">
                    Candidate status
                  </dt>
                  <dd className="mt-1 text-sm leading-6 text-zinc-900">
                    {result.candidate_status ?? "Unknown"}
                  </dd>
                </div>

                <div>
                  <dt className="text-xs font-semibold uppercase text-zinc-500">
                    Resume updated
                  </dt>
                  <dd className="mt-1 text-sm leading-6 text-zinc-900">
                    {formatTimestamp(result.resume_updated_at)}
                  </dd>
                </div>

                <div>
                  <dt className="text-xs font-semibold uppercase text-zinc-500">
                    Resume document
                  </dt>
                  <dd className="mt-1 break-words text-sm leading-6 text-zinc-900">
                    {result.document_title ?? result.document_id}
                  </dd>
                </div>

                <div>
                  <dt className="text-xs font-semibold uppercase text-zinc-500">
                    Canonical candidate ID
                  </dt>
                  <dd className="mt-1 break-words font-mono text-sm leading-6 text-zinc-900">
                    {result.candidate_id}
                  </dd>
                </div>
              </dl>

              <div className="mt-6 grid gap-4 lg:grid-cols-2">
                <div className="border border-zinc-200 bg-zinc-50 p-4">
                  <p className="text-xs font-semibold uppercase text-zinc-500">
                    Strengths
                  </p>
                  <ul className="mt-3 grid gap-2 text-sm leading-6 text-zinc-900">
                    {result.strengths.length > 0 ? (
                      result.strengths.map((strength) => (
                        <li key={strength}>- {strength}</li>
                      ))
                    ) : (
                      <li>No specific strengths returned.</li>
                    )}
                  </ul>
                </div>

                <div className="border border-zinc-200 bg-zinc-50 p-4">
                  <p className="text-xs font-semibold uppercase text-zinc-500">
                    Gaps
                  </p>
                  <ul className="mt-3 grid gap-2 text-sm leading-6 text-zinc-900">
                    {result.gaps.length > 0 ? (
                      result.gaps.map((gap) => <li key={gap}>- {gap}</li>)
                    ) : (
                      <li>No obvious gaps returned.</li>
                    )}
                  </ul>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="grid gap-6">
        <div className="flex flex-col gap-3 border-b border-zinc-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-3xl font-semibold text-zinc-950">
              Search results
            </h2>
            <p className="mt-2 max-w-3xl text-base leading-7 text-zinc-700">
              Direct retrieval results from the canonical current-resume corpus.
            </p>
          </div>

          <div className="text-sm text-zinc-600">
            {submittedQuery ? searchResultCountLabel : "Run a search to see matches."}
          </div>
        </div>

        {submittedQuery ? (
          <p className="text-sm leading-6 text-zinc-600">
            Query: <span className="font-medium text-zinc-900">{submittedQuery}</span>
          </p>
        ) : null}

        {searchResults.length === 0 && !errorMessage ? (
          <div className="border border-dashed border-zinc-300 p-6 text-sm leading-7 text-zinc-600">
            Paste a role brief, run the search, and this page will return the
            strongest current-resume matches.
          </div>
        ) : null}

        <div className="grid gap-5">
          {searchResults.map((result, index) => (
            <article
              key={`${result.candidate_id}-${result.document_id}`}
              className="border border-zinc-200 bg-white p-6"
            >
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-3xl">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800">
                      Rank {index + 1}
                    </span>
                    <span className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700">
                      Score {result.match_score.toFixed(3)}
                    </span>
                  </div>

                  <h3 className="mt-4 text-2xl font-semibold text-zinc-950">
                    {result.full_name ?? "Unnamed candidate"}
                  </h3>

                  <p className="mt-2 text-base leading-7 text-zinc-700">
                    {result.current_title ?? "Title not available"}
                    {result.current_company_name
                      ? ` at ${result.current_company_name}`
                      : ""}
                  </p>
                </div>

                <a
                  href={`/api/v1/candidates/${result.candidate_id}/profile`}
                  className="inline-flex h-11 w-fit items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                >
                  Open profile JSON
                </a>
              </div>

              <dl className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <div>
                  <dt className="text-xs font-semibold uppercase text-zinc-500">
                    Candidate status
                  </dt>
                  <dd className="mt-1 text-sm leading-6 text-zinc-900">
                    {result.candidate_status ?? "Unknown"}
                  </dd>
                </div>

                <div>
                  <dt className="text-xs font-semibold uppercase text-zinc-500">
                    Resume updated
                  </dt>
                  <dd className="mt-1 text-sm leading-6 text-zinc-900">
                    {formatTimestamp(result.resume_updated_at)}
                  </dd>
                </div>

                <div>
                  <dt className="text-xs font-semibold uppercase text-zinc-500">
                    Resume document
                  </dt>
                  <dd className="mt-1 break-words text-sm leading-6 text-zinc-900">
                    {result.document_title ?? result.document_id}
                  </dd>
                </div>

                <div>
                  <dt className="text-xs font-semibold uppercase text-zinc-500">
                    Canonical candidate ID
                  </dt>
                  <dd className="mt-1 break-words font-mono text-sm leading-6 text-zinc-900">
                    {result.candidate_id}
                  </dd>
                </div>
              </dl>

              <div className="mt-6 border border-zinc-200 bg-zinc-50 p-4">
                <p className="text-xs font-semibold uppercase text-zinc-500">
                  Resume match excerpt
                </p>
                <p className="mt-3 text-sm leading-7 text-zinc-900">
                  {renderHighlightedExcerpt(result.match_excerpt)}
                </p>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
