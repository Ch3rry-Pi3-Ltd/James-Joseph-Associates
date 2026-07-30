"use client";

import { useEffect, useState } from "react";

type SharedCandidate = {
  candidate_id: string;
  full_name: string | null;
  current_title: string | null;
  current_company_name: string | null;
  candidate_status: string | null;
  resume_updated_at: string | null;
  document_title: string | null;
  retrieval_score: number;
  retrieval_sources: string[];
  source_category: string;
  graph_context_score: number | null;
  fit_score: number;
  fit_summary: string;
  strengths: string[];
  gaps: string[];
  graph_evidence: {
    skill_names?: string[];
    contacts_count?: number;
    interactions_count?: number;
    jobs_count?: number;
    opportunities_count?: number;
  } | null;
};

type SharedShortlist = {
  share_id: string;
  match_run_id: string;
  role_title: string | null;
  job_description: string;
  shortlisted_candidates: SharedCandidate[];
  created_by_email: string | null;
  created_at: string;
  updated_at: string;
  expires_at: string;
  revoked_at: string | null;
  can_revoke: boolean;
};

type ApiErrorResponse = {
  error?: {
    message?: string;
  };
};

function formatDate(value: string | null): string {
  if (!value) {
    return "Not recorded";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatScore(value: number): string {
  return value.toFixed(3);
}

export function SharedShortlistWorkspace({ shareId }: { shareId: string }) {
  const [share, setShare] = useState<SharedShortlist | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRevoking, setIsRevoking] = useState(false);

  useEffect(() => {
    let isActive = true;

    async function loadShare(): Promise<void> {
      setIsLoading(true);
      setErrorMessage(null);

      try {
        const response = await fetch(
          `/api/v1/candidates/shortlist-shares/${encodeURIComponent(shareId)}`,
          {
            headers: { Accept: "application/json" },
            cache: "no-store",
          },
        );
        const payload = (await response.json()) as SharedShortlist | ApiErrorResponse;

        if (!response.ok) {
          throw new Error(
            "error" in payload
              ? payload.error?.message ?? "The shortlist could not be loaded."
              : "The shortlist could not be loaded.",
          );
        }

        if (isActive) {
          setShare(payload as SharedShortlist);
        }
      } catch (error) {
        if (isActive) {
          setErrorMessage(
            error instanceof Error
              ? error.message
              : "The shortlist could not be loaded.",
          );
        }
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadShare();
    return () => {
      isActive = false;
    };
  }, [shareId]);

  async function revokeShare(): Promise<void> {
    if (!share?.can_revoke || isRevoking) {
      return;
    }

    setIsRevoking(true);
    setErrorMessage(null);

    try {
      const response = await fetch(
        `/api/v1/candidates/shortlist-shares/${encodeURIComponent(shareId)}`,
        {
          method: "DELETE",
          headers: { Accept: "application/json" },
        },
      );
      const payload = (await response.json()) as SharedShortlist | ApiErrorResponse;
      if (!response.ok) {
        throw new Error(
          "error" in payload
            ? payload.error?.message ?? "The shortlist link could not be revoked."
            : "The shortlist link could not be revoked.",
        );
      }
      setShare(payload as SharedShortlist);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "The shortlist link could not be revoked.",
      );
    } finally {
      setIsRevoking(false);
    }
  }

  if (isLoading) {
    return (
      <section className="workspace-section p-8">
        <p className="text-sm font-semibold text-zinc-700">
          Loading secure shortlist...
        </p>
      </section>
    );
  }

  if (!share || errorMessage) {
    return (
      <section className="rounded-md border border-rose-200 bg-rose-50 p-8">
        <p className="text-sm font-semibold uppercase tracking-[0.14em] text-rose-700">
          Link unavailable
        </p>
        <h2 className="mt-3 text-2xl font-semibold text-zinc-950">
          This shortlist cannot be opened
        </h2>
        <p className="mt-3 text-base leading-7 text-zinc-700">
          {errorMessage ?? "The share is unavailable."}
        </p>
      </section>
    );
  }

  if (share.revoked_at) {
    return (
      <section className="rounded-md border border-amber-200 bg-amber-50 p-8">
        <p className="text-sm font-semibold uppercase tracking-[0.14em] text-amber-800">
          Link revoked
        </p>
        <h2 className="mt-3 text-2xl font-semibold text-zinc-950">
          This shortlist is no longer shared
        </h2>
      </section>
    );
  }

  return (
    <>
      <section className="workspace-section grid gap-6 p-6 sm:p-8">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">
              Role
            </p>
            <h2 className="mt-3 text-3xl font-semibold text-zinc-950">
              {share.role_title || "Saved recruiter shortlist"}
            </h2>
            <p className="mt-3 text-base leading-7 text-zinc-700">
              {share.shortlisted_candidates.length} ranked candidates. Created{" "}
              {formatDate(share.created_at)}. Expires{" "}
              {formatDate(share.expires_at)}.
            </p>
          </div>

          {share.can_revoke ? (
            <button
              type="button"
              onClick={() => void revokeShare()}
              disabled={isRevoking}
              className="inline-flex h-10 items-center justify-center rounded-md border border-rose-300 bg-white px-4 text-sm font-semibold text-rose-800 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isRevoking ? "Revoking..." : "Revoke link"}
            </button>
          ) : null}
        </div>

        <details className="rounded-md border border-zinc-200 bg-white p-4">
          <summary className="cursor-pointer text-sm font-semibold text-zinc-950">
            View full role brief
          </summary>
          <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-zinc-700">
            {share.job_description}
          </p>
        </details>
      </section>

      <section className="grid gap-5">
        {share.shortlisted_candidates.map((candidate, index) => (
          <article
            key={candidate.candidate_id}
            className="workspace-card grid gap-6 p-6 sm:p-8"
          >
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_auto]">
              <div>
                <div className="flex flex-wrap gap-2">
                  <span className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800">
                    Rank {index + 1}
                  </span>
                  <span className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700">
                    Fit {candidate.fit_score}/100
                  </span>
                  <span className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700">
                    Retrieval {formatScore(candidate.retrieval_score)}
                  </span>
                  <span className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700">
                    {candidate.source_category.replaceAll("_", " ")}
                  </span>
                </div>

                <h3 className="mt-4 text-2xl font-semibold text-zinc-950">
                  {candidate.full_name || "Candidate name unavailable"}
                </h3>
                <p className="mt-2 text-base text-zinc-700">
                  {[candidate.current_title, candidate.current_company_name]
                    .filter(Boolean)
                    .join(" at ") || "Current role not recorded"}
                </p>
                <p className="mt-4 max-w-4xl text-sm leading-7 text-zinc-700">
                  {candidate.fit_summary}
                </p>
              </div>

              <div className="flex flex-col gap-2">
                <a
                  href={`/api/v1/candidates/${candidate.candidate_id}/current-resume`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex h-10 items-center justify-center rounded-md bg-zinc-950 px-5 text-sm font-semibold text-white transition hover:bg-emerald-900"
                >
                  Open CV
                </a>
                <a
                  href={`/api/v1/candidates/${candidate.candidate_id}/current-resume?download=true`}
                  className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-5 text-sm font-semibold text-zinc-950 transition hover:border-emerald-500"
                >
                  Download CV
                </a>
              </div>
            </div>

            <dl className="grid gap-4 text-sm sm:grid-cols-3">
              <div>
                <dt className="font-semibold uppercase text-zinc-500">
                  Resume document
                </dt>
                <dd className="mt-1 text-zinc-800">
                  {candidate.document_title || "Not recorded"}
                </dd>
              </div>
              <div>
                <dt className="font-semibold uppercase text-zinc-500">
                  Resume updated
                </dt>
                <dd className="mt-1 text-zinc-800">
                  {formatDate(candidate.resume_updated_at)}
                </dd>
              </div>
              <div>
                <dt className="font-semibold uppercase text-zinc-500">
                  Retrieval evidence
                </dt>
                <dd className="mt-1 capitalize text-zinc-800">
                  {candidate.retrieval_sources.join(", ") || "Not recorded"}
                </dd>
              </div>
            </dl>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-md border border-emerald-100 bg-emerald-50/40 p-5">
                <h4 className="font-semibold text-zinc-950">Strengths</h4>
                <ul className="mt-3 grid gap-2 text-sm leading-6 text-zinc-700">
                  {candidate.strengths.map((strength) => (
                    <li key={strength}>- {strength}</li>
                  ))}
                </ul>
              </div>
              <div className="rounded-md border border-rose-100 bg-rose-50/40 p-5">
                <h4 className="font-semibold text-zinc-950">Gaps</h4>
                <ul className="mt-3 grid gap-2 text-sm leading-6 text-zinc-700">
                  {candidate.gaps.length > 0 ? (
                    candidate.gaps.map((gap) => <li key={gap}>- {gap}</li>)
                  ) : (
                    <li>No material gaps recorded.</li>
                  )}
                </ul>
              </div>
            </div>

            {candidate.graph_evidence ? (
              <div className="rounded-md border border-sky-100 bg-sky-50/40 p-5">
                <h4 className="font-semibold text-zinc-950">Linked evidence</h4>
                <p className="mt-2 text-sm leading-6 text-zinc-700">
                  {(candidate.graph_evidence.skill_names ?? []).length} skills,{" "}
                  {candidate.graph_evidence.contacts_count ?? 0} contacts,{" "}
                  {candidate.graph_evidence.interactions_count ?? 0} interactions,{" "}
                  {candidate.graph_evidence.jobs_count ?? 0} jobs, and{" "}
                  {candidate.graph_evidence.opportunities_count ?? 0} opportunities.
                </p>
              </div>
            ) : null}
          </article>
        ))}
      </section>
    </>
  );
}
