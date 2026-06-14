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

type ApiErrorResponse = {
  error?: {
    code?: string;
    message?: string;
    details?: Array<Record<string, unknown>>;
  };
};

const DEFAULT_JOB_DESCRIPTION = `Senior data engineer with strong Python, SQL, cloud platform, and ETL experience. Ideally someone who has worked with large datasets, modern data pipelines, and production analytics systems.`;

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
  const [resultLimit, setResultLimit] = useState("3");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [results, setResults] = useState<CandidateResumeSearchResult[]>([]);
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);

  const resultCountLabel = useMemo(() => {
    if (results.length === 0) {
      return "No candidates returned yet.";
    }

    if (results.length === 1) {
      return "1 candidate returned.";
    }

    return `${results.length} candidates returned.`;
  }, [results.length]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedDescription = jobDescription.trim();
    if (trimmedDescription === "") {
      setErrorMessage("Paste a job description before running the search.");
      setResults([]);
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const searchParams = new URLSearchParams({
        query: trimmedDescription,
        limit: resultLimit,
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

      const payload = (await response.json()) as
        | CandidateResumeSearchResponse
        | ApiErrorResponse;

      if (!response.ok) {
        setResults([]);
        setSubmittedQuery(trimmedDescription);
        setErrorMessage(
          payload.error?.message ??
            `Search request failed with ${response.status}.`,
        );
        return;
      }

      setResults(payload.results);
      setSubmittedQuery(payload.query);
    } catch (error) {
      setResults([]);
      setSubmittedQuery(trimmedDescription);
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Search request failed unexpectedly.",
      );
    } finally {
      setIsLoading(false);
    }
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

          <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
            <div className="grid gap-3">
              <label
                className="text-sm font-semibold uppercase text-zinc-500"
                htmlFor="result-limit"
              >
                Advanced options
              </label>

              <div className="flex flex-wrap items-center gap-3">
                <label
                  className="text-sm font-medium text-zinc-700"
                  htmlFor="result-limit"
                >
                  Candidates returned
                </label>
                <select
                  id="result-limit"
                  value={resultLimit}
                  onChange={(event) => setResultLimit(event.target.value)}
                  className="h-11 rounded-md border border-zinc-300 bg-white px-3 text-sm text-zinc-950 outline-none transition focus:border-zinc-500"
                >
                  <option value="3">Top 3</option>
                  <option value="5">Top 5</option>
                  <option value="10">Top 10</option>
                </select>
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-950 bg-zinc-950 px-5 text-sm font-semibold text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:border-zinc-300 disabled:bg-zinc-300"
            >
              {isLoading ? "Searching..." : "Find candidates"}
            </button>
          </div>
        </form>
      </section>

      <section className="grid gap-6">
        <div className="flex flex-col gap-3 border-b border-zinc-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-3xl font-semibold text-zinc-950">
              Candidate matches
            </h2>
            <p className="mt-2 max-w-3xl text-base leading-7 text-zinc-700">
              Strongest current-resume matches already stored in the canonical
              database.
            </p>
          </div>

          <div className="text-sm text-zinc-600">
            {submittedQuery ? resultCountLabel : "Run a search to see matches."}
          </div>
        </div>

        {submittedQuery ? (
          <p className="text-sm leading-6 text-zinc-600">
            Query: <span className="font-medium text-zinc-900">{submittedQuery}</span>
          </p>
        ) : null}

        {errorMessage ? (
          <div className="border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
            {errorMessage}
          </div>
        ) : null}

        {results.length === 0 && !errorMessage ? (
          <div className="border border-dashed border-zinc-300 p-6 text-sm leading-7 text-zinc-600">
            Paste a role brief, run the search, and this page will return the
            strongest current-resume matches.
          </div>
        ) : null}

        <div className="grid gap-5">
          {results.map((result, index) => (
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
