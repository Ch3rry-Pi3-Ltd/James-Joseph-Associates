"use client";

import { ReactNode, useEffect, useMemo, useState } from "react";

type ApiErrorResponse = {
  error: {
    code: string;
    message: string;
    details?: Array<Record<string, unknown>>;
  };
};

type CandidateCompanyDiscoveryResult = {
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
  company_match_source: string;
  company_match_score: number;
  match_excerpt: string | null;
};

type CandidateCompanyDiscoveryResponse = {
  company_name: string;
  limit: number;
  results: CandidateCompanyDiscoveryResult[];
};

type CompanyJobDiscoveryResult = {
  job_id: string;
  title: string | null;
  status: string | null;
  source: string | null;
  owner_name: string | null;
  location: string | null;
  workplace_type: string | null;
  employment_type: string | null;
  updated_from_source_at: string | null;
  company_id: string | null;
  company_name: string | null;
  hiring_manager_contact_id: string | null;
  hiring_manager_person_id: string | null;
  hiring_manager_name: string | null;
  hiring_manager_email: string | null;
  hiring_manager_phone: string | null;
  hiring_manager_role_title: string | null;
  company_match_source: string;
};

type CompanyJobDiscoveryResponse = {
  company_name: string;
  limit: number;
  results: CompanyJobDiscoveryResult[];
};

type CompanyContactDiscoveryResult = {
  contact_id: string;
  person_id: string;
  full_name: string | null;
  primary_email: string | null;
  primary_phone: string | null;
  linkedin_url: string | null;
  location: string | null;
  headline: string | null;
  company_id: string | null;
  company_name: string | null;
  role_title: string | null;
  contact_type: string | null;
  seniority: string | null;
  is_hiring_manager: boolean;
  role_is_current: boolean | null;
  role_start_date: string | null;
  role_end_date: string | null;
  company_match_source: string;
};

type CompanyContactDiscoveryResponse = {
  company_name: string;
  limit: number;
  results: CompanyContactDiscoveryResult[];
};

type CompanyInteractionDiscoveryResult = {
  interaction_id: string;
  interaction_type: string | null;
  occurred_at: string | null;
  subject: string | null;
  summary: string | null;
  body: string | null;
  source_system: string | null;
  person_id: string;
  candidate_id: string | null;
  company_id: string | null;
  company_name: string | null;
  full_name: string | null;
  role_title: string | null;
  candidate_last_contacted_at: string | null;
  matched_entity_type: string;
};

type CompanyInteractionDiscoveryResponse = {
  company_name: string;
  limit: number;
  results: CompanyInteractionDiscoveryResult[];
};

type CompanyDirectoryResponse = {
  count: number;
  companies: string[];
};

const EXAMPLE_COMPANY = "Capgemini UK Plc";

function isApiErrorResponse(
  payload: unknown,
): payload is ApiErrorResponse {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "error" in payload &&
    typeof payload.error === "object" &&
    payload.error !== null
  );
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "-";
  }

  const parsedDate = new Date(value);
  if (Number.isNaN(parsedDate.getTime())) {
    return value;
  }

  return parsedDate.toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function describeCompanyMatch(source: string): string {
  if (source === "current_company_exact") {
    return "Current employer exact match";
  }

  if (source === "current_company_partial") {
    return "Current employer partial match";
  }

  if (source === "resume_text") {
    return "Resume text mention";
  }

  if (source === "company_exact") {
    return "Linked canonical company";
  }

  return source.replaceAll("_", " ");
}

function renderHighlightedExcerpt(excerpt: string | null): ReactNode {
  if (!excerpt || excerpt.trim() === "") {
    return "-";
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
            key={`company-excerpt-${index}`}
            className="rounded bg-emerald-100 px-1 text-zinc-950"
          >
            {part}
          </mark>
        );
      }

      return <span key={`company-excerpt-${index}`}>{part}</span>;
    });
}

export function CompanyDiscoveryWorkspace() {
  const [companyName, setCompanyName] = useState(EXAMPLE_COMPANY);
  const [companyDirectory, setCompanyDirectory] = useState<string[]>([]);
  const [resultLimit, setResultLimit] = useState(5);
  const [isLoading, setIsLoading] = useState(false);
  const [isDirectoryLoading, setIsDirectoryLoading] = useState(false);
  const [isCompanyPickerOpen, setIsCompanyPickerOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submittedCompanyName, setSubmittedCompanyName] = useState<string | null>(
    null,
  );
  const [candidateResults, setCandidateResults] =
    useState<CandidateCompanyDiscoveryResult[]>([]);
  const [jobResults, setJobResults] = useState<CompanyJobDiscoveryResult[]>([]);
  const [contactResults, setContactResults] = useState<
    CompanyContactDiscoveryResult[]
  >([]);
  const [interactionResults, setInteractionResults] = useState<
    CompanyInteractionDiscoveryResult[]
  >([]);

  useEffect(() => {
    let isMounted = true;

    async function loadCompanyDirectory() {
      setIsDirectoryLoading(true);

      try {
        const response = await fetch("/api/v1/candidates/company-directory", {
          method: "GET",
        });
        const payload = (await response.json()) as
          | CompanyDirectoryResponse
          | ApiErrorResponse;

        if (!response.ok || isApiErrorResponse(payload)) {
          return;
        }

        if (isMounted) {
          setCompanyDirectory(payload.companies);
        }
      } finally {
        if (isMounted) {
          setIsDirectoryLoading(false);
        }
      }
    }

    void loadCompanyDirectory();

    return () => {
      isMounted = false;
    };
  }, []);

  const summaryText = useMemo(() => {
    if (!submittedCompanyName) {
      return "Run a company lookup to inspect existing candidates and jobs.";
    }

    return `${candidateResults.length} candidate matches, ${contactResults.length} contacts, ${interactionResults.length} recent interactions, and ${jobResults.length} linked jobs found for ${submittedCompanyName}.`;
  }, [
    candidateResults.length,
    contactResults.length,
    interactionResults.length,
    jobResults.length,
    submittedCompanyName,
  ]);

  const filteredCompanies = useMemo(() => {
    const normalizedQuery = companyName.trim().toLowerCase();
    if (companyDirectory.length === 0) {
      return [];
    }

    if (normalizedQuery === "") {
      return companyDirectory.slice(0, 12);
    }

    return companyDirectory
      .filter((name) => name.toLowerCase().includes(normalizedQuery))
      .slice(0, 12);
  }, [companyDirectory, companyName]);

  async function runLookup() {
    const normalizedCompanyName = companyName.trim();
    if (normalizedCompanyName === "") {
      setErrorMessage("Company name must not be blank.");
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const queryString = new URLSearchParams({
        company_name: normalizedCompanyName,
        limit: String(resultLimit),
      }).toString();

      const [
        candidateResponse,
        contactResponse,
        interactionResponse,
        jobResponse,
      ] = await Promise.all([
        fetch(`/api/v1/candidates/discover-by-company?${queryString}`, {
          method: "GET",
        }),
        fetch(`/api/v1/candidates/discover-contacts-by-company?${queryString}`, {
          method: "GET",
        }),
        fetch(
          `/api/v1/candidates/discover-interactions-by-company?${queryString}`,
          {
            method: "GET",
          },
        ),
        fetch(`/api/v1/candidates/discover-jobs-by-company?${queryString}`, {
          method: "GET",
        }),
      ]);

      const candidatePayload =
        (await candidateResponse.json()) as
          | CandidateCompanyDiscoveryResponse
          | ApiErrorResponse;
      const jobPayload =
        (await jobResponse.json()) as CompanyJobDiscoveryResponse | ApiErrorResponse;
      const contactPayload =
        (await contactResponse.json()) as
          | CompanyContactDiscoveryResponse
          | ApiErrorResponse;
      const interactionPayload =
        (await interactionResponse.json()) as
          | CompanyInteractionDiscoveryResponse
          | ApiErrorResponse;

      if (!candidateResponse.ok) {
        setErrorMessage(
          isApiErrorResponse(candidatePayload)
            ? candidatePayload.error.message
            : `Candidate lookup failed with ${candidateResponse.status}.`,
        );
        setCandidateResults([]);
        setContactResults([]);
        setInteractionResults([]);
        setJobResults([]);
        setSubmittedCompanyName(normalizedCompanyName);
        return;
      }

      if (isApiErrorResponse(candidatePayload)) {
        setErrorMessage(candidatePayload.error.message);
        setCandidateResults([]);
        setContactResults([]);
        setInteractionResults([]);
        setJobResults([]);
        setSubmittedCompanyName(normalizedCompanyName);
        return;
      }

      if (!contactResponse.ok) {
        setErrorMessage(
          isApiErrorResponse(contactPayload)
            ? contactPayload.error.message
            : `Contact lookup failed with ${contactResponse.status}.`,
        );
        setCandidateResults(candidatePayload.results);
        setContactResults([]);
        setInteractionResults([]);
        setJobResults([]);
        setSubmittedCompanyName(normalizedCompanyName);
        return;
      }

      if (isApiErrorResponse(contactPayload)) {
        setErrorMessage(contactPayload.error.message);
        setCandidateResults(candidatePayload.results);
        setContactResults([]);
        setInteractionResults([]);
        setJobResults([]);
        setSubmittedCompanyName(normalizedCompanyName);
        return;
      }

      if (!interactionResponse.ok) {
        setErrorMessage(
          isApiErrorResponse(interactionPayload)
            ? interactionPayload.error.message
            : `Interaction lookup failed with ${interactionResponse.status}.`,
        );
        setCandidateResults(candidatePayload.results);
        setContactResults(contactPayload.results);
        setInteractionResults([]);
        setJobResults([]);
        setSubmittedCompanyName(normalizedCompanyName);
        return;
      }

      if (isApiErrorResponse(interactionPayload)) {
        setErrorMessage(interactionPayload.error.message);
        setCandidateResults(candidatePayload.results);
        setContactResults(contactPayload.results);
        setInteractionResults([]);
        setJobResults([]);
        setSubmittedCompanyName(normalizedCompanyName);
        return;
      }

      if (!jobResponse.ok) {
        setErrorMessage(
          isApiErrorResponse(jobPayload)
            ? jobPayload.error.message
            : `Job lookup failed with ${jobResponse.status}.`,
        );
        setCandidateResults(candidatePayload.results);
        setContactResults(contactPayload.results);
        setInteractionResults(interactionPayload.results);
        setJobResults([]);
        setSubmittedCompanyName(normalizedCompanyName);
        return;
      }

      if (isApiErrorResponse(jobPayload)) {
        setErrorMessage(jobPayload.error.message);
        setCandidateResults(candidatePayload.results);
        setContactResults(contactPayload.results);
        setInteractionResults(interactionPayload.results);
        setJobResults([]);
        setSubmittedCompanyName(normalizedCompanyName);
        return;
      }

      setCandidateResults(candidatePayload.results);
      setContactResults(contactPayload.results);
      setInteractionResults(interactionPayload.results);
      setJobResults(jobPayload.results);
      setSubmittedCompanyName(normalizedCompanyName);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Company lookup failed unexpectedly.",
      );
      setCandidateResults([]);
      setContactResults([]);
      setInteractionResults([]);
      setJobResults([]);
      setSubmittedCompanyName(normalizedCompanyName);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <section className="workspace-section px-6 py-6 sm:px-8">
        <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
              Company lookup
            </p>
            <h2 className="mt-3 text-3xl font-semibold text-zinc-950">
              Find existing candidates and live jobs
            </h2>
            <p className="mt-4 max-w-2xl text-base leading-7 text-zinc-700">
              This is the first narrow recruiter workflow beyond role matching:
              search one company name and see who already appears in the
              canonical estate.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
            <div className="workspace-card-soft p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Candidate signals
              </p>
              <p className="mt-3 text-sm leading-6 text-zinc-800">
                Current employer matches plus CV text mentions.
              </p>
            </div>
            <div className="workspace-card-soft p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Job signals
              </p>
              <p className="mt-3 text-sm leading-6 text-zinc-800">
                Canonical jobs already linked to the same company.
              </p>
            </div>
            <div className="workspace-card-soft p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
                Next slice
              </p>
              <p className="mt-3 text-sm leading-6 text-zinc-800">
                Relationship warmth and prior-contact evidence.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="workspace-section px-6 py-6 sm:px-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500">
              Query
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-zinc-950">
              Which company are we targeting?
            </h2>
          </div>

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => setCompanyName(EXAMPLE_COMPANY)}
              className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
            >
              Use example
            </button>
          </div>
        </div>

        <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_12rem_12rem] lg:items-start">
          <label className="grid gap-2">
            <span className="text-sm font-semibold uppercase text-zinc-500">
              Company name
            </span>
            <div className="relative">
              <input
                type="text"
                value={companyName}
                onChange={(event) => {
                  setCompanyName(event.target.value);
                  setIsCompanyPickerOpen(true);
                }}
                onFocus={() => setIsCompanyPickerOpen(true)}
                onBlur={() => {
                  window.setTimeout(() => {
                    setIsCompanyPickerOpen(false);
                  }, 120);
                }}
                placeholder="Start typing a company name"
                className="workspace-input h-12 px-4 text-base text-zinc-950"
                autoComplete="off"
              />
              {isCompanyPickerOpen && companyDirectory.length > 0 ? (
                <div className="absolute top-[calc(100%+0.25rem)] z-20 max-h-72 w-full overflow-y-auto rounded-md border border-zinc-200 bg-white p-2 shadow-[0_18px_45px_-24px_rgba(15,23,42,0.35)]">
                  <div className="mb-2 flex items-center justify-between px-2 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                    <span>Canonical companies</span>
                    <span>{filteredCompanies.length} shown</span>
                  </div>
                  {filteredCompanies.length === 0 ? (
                    <div className="rounded-md border border-dashed border-zinc-200 px-3 py-3 text-sm text-zinc-500">
                      No matching companies found.
                    </div>
                  ) : (
                    <div className="grid gap-1">
                      {filteredCompanies.map((name) => (
                        <button
                          key={name}
                          type="button"
                          onMouseDown={(event) => {
                            event.preventDefault();
                            setCompanyName(name);
                            setIsCompanyPickerOpen(false);
                          }}
                          className={`rounded-md px-3 py-2 text-left text-sm transition ${
                            name === companyName
                              ? "bg-emerald-50 text-zinc-950"
                              : "text-zinc-700 hover:bg-zinc-50 hover:text-zinc-950"
                          }`}
                        >
                          {name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          </label>

          <label className="grid gap-2">
            <span className="text-sm font-semibold uppercase text-zinc-500">
              Result limit
            </span>
            <select
              value={String(resultLimit)}
              onChange={(event) => setResultLimit(Number(event.target.value))}
              className="workspace-select h-12 px-4 text-base text-zinc-950"
            >
              {[5, 10, 15, 20].map((value) => (
                <option key={value} value={value}>
                  Top {value}
                </option>
              ))}
            </select>
          </label>

          <div className="grid gap-2">
            <span className="text-sm font-semibold uppercase text-zinc-500">
              Run
            </span>
            <button
              type="button"
              onClick={runLookup}
              disabled={isLoading}
              className="inline-flex h-12 items-center justify-center rounded-md border border-zinc-950 bg-zinc-950 px-4 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:border-zinc-400 disabled:bg-zinc-400"
            >
              {isLoading ? "Searching..." : "Search company"}
            </button>
          </div>
        </div>

        <p className="mt-3 text-sm text-zinc-500">
          {isDirectoryLoading
            ? "Loading canonical companies..."
            : `${companyDirectory.length} canonical companies loaded. Start typing to filter, then choose from the list.`}
        </p>

        <div className="workspace-card-soft mt-6 p-4 text-sm text-zinc-800">
          {summaryText}
        </div>

        {errorMessage ? (
          <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            {errorMessage}
          </div>
        ) : null}
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <article className="workspace-section px-6 py-6 sm:px-8">
          <div className="flex items-end justify-between gap-4 border-b border-zinc-200 pb-5">
            <div>
              <p className="text-sm font-semibold uppercase text-zinc-500">
                Candidates
              </p>
              <h2 className="mt-2 text-3xl font-semibold text-zinc-950">
                Who already works there?
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-600">
                Candidates whose current employer or CV evidence already points
                to the target company.
              </p>
            </div>
            <p className="text-sm text-zinc-600">
              {candidateResults.length} matches
            </p>
          </div>

          <div className="mt-5 grid gap-4">
            {candidateResults.length === 0 ? (
              <div className="workspace-empty p-5 text-sm text-zinc-600">
                No candidate matches were found for this company in the current
                canonical CV corpus.
              </div>
            ) : (
              candidateResults.map((result) => (
                <div
                  key={`${result.candidate_id}-${result.document_id}`}
                  className="workspace-card p-5"
                >
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h3 className="text-xl font-semibold text-zinc-950">
                        {result.full_name ?? "Unnamed candidate"}
                      </h3>
                      <p className="mt-2 text-sm leading-6 text-zinc-700">
                        {result.current_title ?? "Title unknown"}
                        {result.current_company_name
                          ? ` at ${result.current_company_name}`
                          : ""}
                      </p>
                    </div>
                    <span className="rounded-md border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-800">
                      {describeCompanyMatch(result.company_match_source)}
                    </span>
                  </div>

                  <dl className="mt-4 grid gap-2 text-sm text-zinc-700">
                    <div className="grid grid-cols-[9rem_1fr] gap-3">
                      <dt className="font-semibold text-zinc-500">Status</dt>
                      <dd>{result.candidate_status ?? "-"}</dd>
                    </div>
                    <div className="grid grid-cols-[9rem_1fr] gap-3">
                      <dt className="font-semibold text-zinc-500">Resume updated</dt>
                      <dd>{formatTimestamp(result.resume_updated_at)}</dd>
                    </div>
                    <div className="grid grid-cols-[9rem_1fr] gap-3">
                      <dt className="font-semibold text-zinc-500">Evidence</dt>
                      <dd>{renderHighlightedExcerpt(result.match_excerpt)}</dd>
                    </div>
                  </dl>

                  <div className="mt-5 flex flex-wrap gap-3">
                    <a
                      href={`/api/v1/candidates/${result.candidate_id}/current-resume`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                    >
                      Open CV
                    </a>
                    <a
                      href={`/api/v1/candidates/${result.candidate_id}/current-resume?download=true`}
                      className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                    >
                      Download CV
                    </a>
                  </div>
                </div>
              ))
            )}
          </div>
        </article>

        <article className="workspace-section px-6 py-6 sm:px-8">
          <div className="flex items-end justify-between gap-4 border-b border-zinc-200 pb-5">
            <div>
              <p className="text-sm font-semibold uppercase text-zinc-500">
                Contacts
              </p>
              <h2 className="mt-2 text-3xl font-semibold text-zinc-950">
                Who do we already know there?
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-600">
                Canonical contact or hiring-manager records already linked to
                the target company.
              </p>
            </div>
            <p className="text-sm text-zinc-600">
              {contactResults.length} contacts
            </p>
          </div>

          <div className="mt-5 grid gap-4">
            {contactResults.length === 0 ? (
              <div className="workspace-empty p-5 text-sm text-zinc-600">
                No canonical contacts or hiring managers are currently linked
                to this company.
              </div>
            ) : (
              contactResults.map((result) => (
                <div
                  key={result.contact_id}
                  className="workspace-card p-5"
                >
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h3 className="text-xl font-semibold text-zinc-950">
                        {result.full_name ?? "Unnamed contact"}
                      </h3>
                      <p className="mt-2 text-sm leading-6 text-zinc-700">
                        {result.role_title ?? "Role unknown"}
                        {result.company_name ? ` at ${result.company_name}` : ""}
                      </p>
                    </div>
                    <span
                      className={`rounded-md border px-3 py-1 text-xs font-semibold ${
                        result.is_hiring_manager
                          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                          : "border-zinc-200 bg-zinc-50 text-zinc-700"
                      }`}
                    >
                      {result.is_hiring_manager
                        ? "Hiring manager"
                        : result.contact_type ?? "Contact"}
                    </span>
                  </div>

                  <dl className="mt-4 grid gap-2 text-sm text-zinc-700">
                    <div className="grid grid-cols-[8rem_1fr] gap-3">
                      <dt className="font-semibold text-zinc-500">Email</dt>
                      <dd>{result.primary_email ?? "-"}</dd>
                    </div>
                    <div className="grid grid-cols-[8rem_1fr] gap-3">
                      <dt className="font-semibold text-zinc-500">Phone</dt>
                      <dd>{result.primary_phone ?? "-"}</dd>
                    </div>
                    <div className="grid grid-cols-[8rem_1fr] gap-3">
                      <dt className="font-semibold text-zinc-500">Current</dt>
                      <dd>
                        {result.role_is_current === null
                          ? "-"
                          : result.role_is_current
                            ? "Yes"
                            : "No"}
                      </dd>
                    </div>
                    <div className="grid grid-cols-[8rem_1fr] gap-3">
                      <dt className="font-semibold text-zinc-500">LinkedIn</dt>
                      <dd className="break-words">
                        {result.linkedin_url ? (
                          <a
                            href={result.linkedin_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-zinc-950 underline"
                          >
                            Open profile
                          </a>
                        ) : (
                          "-"
                        )}
                      </dd>
                    </div>
                  </dl>
                </div>
              ))
            )}
          </div>
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <article className="workspace-section px-6 py-6 sm:px-8">
          <div className="flex items-end justify-between gap-4 border-b border-zinc-200 pb-5">
            <div>
              <p className="text-sm font-semibold uppercase text-zinc-500">
                Interaction evidence
              </p>
              <h2 className="mt-2 text-3xl font-semibold text-zinc-950">
                Who has been spoken to before?
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-600">
                Recent interaction records tied to people or entities already
                linked to the target company.
              </p>
            </div>
            <p className="text-sm text-zinc-600">
              {interactionResults.length} interactions
            </p>
          </div>

          <div className="mt-5 grid gap-4">
            {interactionResults.length === 0 ? (
              <div className="workspace-empty p-5 text-sm text-zinc-600">
                No recent interaction evidence is currently linked to this
                company.
              </div>
            ) : (
              interactionResults.map((result) => (
                <div
                  key={result.interaction_id}
                  className="workspace-card p-5"
                >
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h3 className="text-xl font-semibold text-zinc-950">
                        {result.full_name ?? "Unknown person"}
                      </h3>
                      <p className="mt-2 text-sm leading-6 text-zinc-700">
                        {result.role_title ?? "Role unknown"}
                        {result.company_name ? ` at ${result.company_name}` : ""}
                      </p>
                    </div>
                    <span className="rounded-md border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">
                      {result.source_system ?? "interaction"}
                    </span>
                  </div>

                  <dl className="mt-4 grid gap-2 text-sm text-zinc-700">
                    <div className="grid grid-cols-[8rem_1fr] gap-3">
                      <dt className="font-semibold text-zinc-500">Occurred</dt>
                      <dd>{formatTimestamp(result.occurred_at)}</dd>
                    </div>
                    <div className="grid grid-cols-[8rem_1fr] gap-3">
                      <dt className="font-semibold text-zinc-500">Type</dt>
                      <dd>{result.interaction_type ?? "-"}</dd>
                    </div>
                    <div className="grid grid-cols-[8rem_1fr] gap-3">
                      <dt className="font-semibold text-zinc-500">Subject</dt>
                      <dd>{result.subject ?? "-"}</dd>
                    </div>
                    <div className="grid grid-cols-[8rem_1fr] gap-3">
                      <dt className="font-semibold text-zinc-500">Summary</dt>
                      <dd>{result.summary ?? result.body ?? "-"}</dd>
                    </div>
                  </dl>
                </div>
              ))
            )}
          </div>
        </article>

        <article className="workspace-section px-6 py-6 sm:px-8">
          <div className="flex items-end justify-between gap-4 border-b border-zinc-200 pb-5">
            <div>
              <p className="text-sm font-semibold uppercase text-zinc-500">
                Jobs
              </p>
              <h2 className="mt-2 text-3xl font-semibold text-zinc-950">
                Which roles are already linked?
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-600">
                Open or recent canonical jobs already connected to the target
                company.
              </p>
            </div>
            <p className="text-sm text-zinc-600">{jobResults.length} jobs</p>
          </div>

          <div className="mt-5 grid gap-4">
            {jobResults.length === 0 ? (
              <div className="workspace-empty p-5 text-sm text-zinc-600">
                No canonical jobs are currently linked to this company.
              </div>
            ) : (
              jobResults.map((result) => (
                <div
                  key={result.job_id}
                  className="workspace-card p-5"
                >
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h3 className="text-xl font-semibold text-zinc-950">
                        {result.title ?? "Untitled job"}
                      </h3>
                      <p className="mt-2 text-sm leading-6 text-zinc-700">
                        {result.company_name ?? "Company unknown"}
                      </p>
                    </div>
                    <span className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800">
                      {describeCompanyMatch(result.company_match_source)}
                    </span>
                  </div>

                  <dl className="mt-4 grid gap-2 text-sm text-zinc-700">
                    <div className="grid grid-cols-[9rem_1fr] gap-3">
                      <dt className="font-semibold text-zinc-500">Status</dt>
                      <dd>{result.status ?? "-"}</dd>
                    </div>
                    <div className="grid grid-cols-[9rem_1fr] gap-3">
                      <dt className="font-semibold text-zinc-500">Source</dt>
                      <dd>{result.source ?? "-"}</dd>
                    </div>
                    <div className="grid grid-cols-[9rem_1fr] gap-3">
                      <dt className="font-semibold text-zinc-500">Location</dt>
                      <dd>{result.location ?? "-"}</dd>
                    </div>
                    <div className="grid grid-cols-[9rem_1fr] gap-3">
                      <dt className="font-semibold text-zinc-500">
                        Hiring manager
                      </dt>
                      <dd>
                        {result.hiring_manager_name ?? "Not linked yet"}
                        {result.hiring_manager_role_title
                          ? `, ${result.hiring_manager_role_title}`
                          : ""}
                      </dd>
                    </div>
                  </dl>
                </div>
              ))
            )}
          </div>
        </article>
      </section>
    </div>
  );
}
