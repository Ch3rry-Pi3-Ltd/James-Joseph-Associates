"use client";

import {
  FormEvent,
  ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type RetrievalEvidence = {
  retrieval_sources: string[];
  text_rank: number | null;
  semantic_rank: number | null;
  text_score: number | null;
  semantic_score: number | null;
  semantic_block_type: string | null;
  semantic_block_label: string | null;
};

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
  retrieval_sources: string[];
  text_rank: number | null;
  semantic_rank: number | null;
  text_score: number | null;
  semantic_score: number | null;
  semantic_block_type: string | null;
  semantic_block_label: string | null;
  match_excerpt: string | null;
};

type CandidateResumeSearchResponse = {
  query: string;
  limit: number;
  results: CandidateResumeSearchResult[];
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

type CandidateCompanyLeadDiscoveryResponse = {
  candidate: CandidateProfileCandidate;
  skills: CandidateProfileSkill[];
  skill_names: string[];
  company_name: string;
  candidate_already_at_company: boolean;
  peer_candidates: CandidateCompanyDiscoveryResult[];
  contacts: CompanyContactDiscoveryResult[];
  interactions: CompanyInteractionDiscoveryResult[];
  jobs: CompanyJobDiscoveryResult[];
};

type UploadedResumeSearchResponse = {
  file_name: string | null;
  content_type: string | null;
  extractor: string | null;
  page_count: number | null;
  character_count: number;
  cleaned_text_preview: string;
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
  retrieval_sources: string[];
  text_rank: number | null;
  semantic_rank: number | null;
  text_score: number | null;
  semantic_score: number | null;
  semantic_block_type: string | null;
  semantic_block_label: string | null;
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

type CandidateProfileSkill = {
  candidate_id: string;
  skill_id: string;
  skill_name: string | null;
  canonical_name: string | null;
  skill_type: string | null;
  confidence: number | null;
  evidence_text: string | null;
};

type CandidateProfileCandidate = {
  candidate_id: string;
  person_id: string;
  full_name: string | null;
  first_name: string | null;
  last_name: string | null;
  primary_email: string | null;
  primary_phone: string | null;
  linkedin_url: string | null;
  location: string | null;
  headline: string | null;
  summary: string | null;
  current_title: string | null;
  candidate_status: string | null;
  availability_status: string | null;
  salary_expectation: string | null;
  notice_period: string | null;
  last_contacted_at: string | null;
  resume_updated_at: string | null;
  current_company_id: string | null;
  current_company_name: string | null;
};

type CandidateProfileResponse = {
  candidate: CandidateProfileCandidate;
  skills: CandidateProfileSkill[];
};

type RunMode = "search" | "shortlist" | null;

const DEFAULT_JOB_DESCRIPTION = `Senior data engineer with strong Python, SQL, cloud platform, and ETL experience. Ideally someone who has worked with large datasets, modern data pipelines, and production analytics systems.`;

const RETRIEVAL_STOP_WORDS = new Set([
  "a",
  "about",
  "across",
  "also",
  "an",
  "and",
  "any",
  "are",
  "as",
  "at",
  "be",
  "been",
  "before",
  "between",
  "brief",
  "build",
  "by",
  "can",
  "closer",
  "current",
  "description",
  "do",
  "for",
  "from",
  "has",
  "have",
  "how",
  "i",
  "ideally",
  "in",
  "into",
  "is",
  "it",
  "just",
  "looking",
  "modern",
  "more",
  "most",
  "need",
  "of",
  "on",
  "or",
  "production",
  "role",
  "search",
  "should",
  "show",
  "someone",
  "strong",
  "such",
  "systems",
  "that",
  "the",
  "their",
  "them",
  "there",
  "this",
  "to",
  "use",
  "we",
  "what",
  "when",
  "where",
  "who",
  "with",
  "worked",
  "workflow",
]);

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

function formatRetrievalSourceLabel(source: string): string {
  if (source === "text") {
    return "Full-text";
  }

  if (source === "semantic") {
    return "Semantic";
  }

  return source;
}

function formatSemanticBlockType(value: string | null): string | null {
  if (!value) {
    return null;
  }

  return value.replaceAll("_", " ");
}

function formatCompanyMatchSourceLabel(source: string): string {
  if (source === "current_company_exact") {
    return "Current company exact";
  }

  if (source === "current_company_partial") {
    return "Current company partial";
  }

  if (source === "resume_text") {
    return "CV text mention";
  }

  return source.replaceAll("_", " ");
}

function formatUnderscoredLabel(value: string | null): string {
  if (!value) {
    return "Unknown";
  }

  return value.replaceAll("_", " ");
}

function deriveRetrievalFocusTerms(jobDescription: string): string {
  const normalizedTerms =
    jobDescription.match(/[A-Za-z0-9+#./-]+/g)?.map((term) => term.trim()) ?? [];

  const seenTerms = new Set<string>();
  const selectedTerms: string[] = [];

  for (const originalTerm of normalizedTerms) {
    const canonicalTerm = originalTerm
      .toLowerCase()
      .replace(/^[^a-z0-9+#]+|[^a-z0-9+#]+$/g, "");

    if (canonicalTerm.length < 2) {
      continue;
    }

    if (RETRIEVAL_STOP_WORDS.has(canonicalTerm)) {
      continue;
    }

    if (seenTerms.has(canonicalTerm)) {
      continue;
    }

    seenTerms.add(canonicalTerm);
    selectedTerms.push(canonicalTerm);

    if (selectedTerms.length >= 8) {
      break;
    }
  }

  return selectedTerms.join(" ");
}

function buildLoadingMessage(mode: RunMode): string {
  if (mode === "search") {
    return "Running hybrid retrieval across the CV corpus.";
  }

  if (mode === "shortlist") {
    return "Retrieving the candidate pool, then asking the reasoning model to rerank it.";
  }

  return "";
}

function renderRetrievalDiagnostics(
  result: RetrievalEvidence,
  {
    primaryScoreLabel,
    primaryScoreValue,
  }: {
    primaryScoreLabel: string;
    primaryScoreValue: number;
  },
): ReactNode {
  const semanticBlockType = formatSemanticBlockType(result.semantic_block_type);
  const hasDiagnostics =
    result.retrieval_sources.length > 0 ||
    result.text_rank !== null ||
    result.semantic_rank !== null ||
    result.text_score !== null ||
    result.semantic_score !== null ||
    result.semantic_block_label !== null ||
    semanticBlockType !== null;

  if (!hasDiagnostics) {
    return null;
  }

  return (
    <div className="mt-6 border border-zinc-200 p-4">
      <p className="text-xs font-semibold uppercase text-zinc-500">
        Retrieval diagnostics
      </p>

      <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div>
          <dt className="text-xs font-semibold uppercase text-zinc-500">
            Sources
          </dt>
          <dd className="mt-2 flex flex-wrap gap-2">
            {result.retrieval_sources.length > 0 ? (
              result.retrieval_sources.map((source) => (
                <span
                  key={source}
                  className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700"
                >
                  {formatRetrievalSourceLabel(source)}
                </span>
              ))
            ) : (
              <span className="text-sm leading-6 text-zinc-900">Unknown</span>
            )}
          </dd>
        </div>

        <div>
          <dt className="text-xs font-semibold uppercase text-zinc-500">
            Scores
          </dt>
          <dd className="mt-1 grid gap-1 text-sm leading-6 text-zinc-900">
            <span>
              {primaryScoreLabel}: {primaryScoreValue.toFixed(3)}
            </span>
            {result.text_score !== null ? (
              <span>Full-text: {result.text_score.toFixed(3)}</span>
            ) : null}
            {result.semantic_score !== null ? (
              <span>Semantic: {result.semantic_score.toFixed(3)}</span>
            ) : null}
          </dd>
        </div>

        <div>
          <dt className="text-xs font-semibold uppercase text-zinc-500">
            Ranks
          </dt>
          <dd className="mt-1 grid gap-1 text-sm leading-6 text-zinc-900">
            {result.text_rank !== null ? (
              <span>Full-text rank: {result.text_rank}</span>
            ) : null}
            {result.semantic_rank !== null ? (
              <span>Semantic rank: {result.semantic_rank}</span>
            ) : null}
            {result.text_rank === null && result.semantic_rank === null ? (
              <span>Not available</span>
            ) : null}
          </dd>
        </div>

        <div>
          <dt className="text-xs font-semibold uppercase text-zinc-500">
            Semantic evidence
          </dt>
          <dd className="mt-1 grid gap-1 text-sm leading-6 text-zinc-900">
            {result.semantic_block_label ? (
              <span>{result.semantic_block_label}</span>
            ) : null}
            {semanticBlockType ? <span>Type: {semanticBlockType}</span> : null}
            {!result.semantic_block_label && !semanticBlockType ? (
              <span>Not available</span>
            ) : null}
          </dd>
        </div>
      </div>
    </div>
  );
}

async function encodeFileAsBase64(file: File): Promise<string> {
  const arrayBuffer = await file.arrayBuffer();
  const bytes = new Uint8Array(arrayBuffer);
  let binary = "";

  for (const value of bytes) {
    binary += String.fromCharCode(value);
  }

  return btoa(binary);
}

export function CandidateMatchWorkspace() {
  const shortlistSectionRef = useRef<HTMLElement | null>(null);
  const searchResultsSectionRef = useRef<HTMLElement | null>(null);
  const uploadedResumeInputRef = useRef<HTMLInputElement | null>(null);
  const [jobDescription, setJobDescription] = useState(DEFAULT_JOB_DESCRIPTION);
  const [retrievalFocusTerms, setRetrievalFocusTerms] = useState(() =>
    deriveRetrievalFocusTerms(DEFAULT_JOB_DESCRIPTION),
  );
  const [isFocusTermsAuto, setIsFocusTermsAuto] = useState(true);
  const [searchResultLimit, setSearchResultLimit] = useState("10");
  const [retrievalLimit, setRetrievalLimit] = useState("25");
  const [shortlistLimit, setShortlistLimit] = useState("3");
  const [isSearchLoading, setIsSearchLoading] = useState(false);
  const [isShortlistLoading, setIsShortlistLoading] = useState(false);
  const [activeRunMode, setActiveRunMode] = useState<RunMode>(null);
  const [searchErrorMessage, setSearchErrorMessage] = useState<string | null>(null);
  const [shortlistErrorMessage, setShortlistErrorMessage] = useState<string | null>(
    null,
  );
  const [searchResults, setSearchResults] = useState<CandidateResumeSearchResult[]>(
    [],
  );
  const [shortlistResults, setShortlistResults] = useState<
    CandidateJobDescriptionShortlistItem[]
  >([]);
  const [submittedSearchQuery, setSubmittedSearchQuery] = useState<string | null>(
    null,
  );
  const [submittedJobDescription, setSubmittedJobDescription] = useState<
    string | null
  >(null);
  const [retrievedCandidateCount, setRetrievedCandidateCount] = useState(0);
  const [previewCandidateId, setPreviewCandidateId] = useState<string | null>(null);
  const [previewProfile, setPreviewProfile] = useState<CandidateProfileResponse | null>(
    null,
  );
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewErrorMessage, setPreviewErrorMessage] = useState<string | null>(
    null,
  );
  const [candidateLeadCompanyName, setCandidateLeadCompanyName] = useState("");
  const [candidateLeadLimit, setCandidateLeadLimit] = useState("10");
  const [candidateLeadLoading, setCandidateLeadLoading] = useState(false);
  const [candidateLeadErrorMessage, setCandidateLeadErrorMessage] = useState<
    string | null
  >(null);
  const [candidateLeadResult, setCandidateLeadResult] =
    useState<CandidateCompanyLeadDiscoveryResponse | null>(null);
  const [companyNameQuery, setCompanyNameQuery] = useState("");
  const [companySearchLimit, setCompanySearchLimit] = useState("10");
  const [companyDiscoveryLoading, setCompanyDiscoveryLoading] = useState(false);
  const [companyDiscoveryErrorMessage, setCompanyDiscoveryErrorMessage] = useState<
    string | null
  >(null);
  const [companyDiscoveryResults, setCompanyDiscoveryResults] = useState<
    CandidateCompanyDiscoveryResult[]
  >([]);
  const [companyJobResults, setCompanyJobResults] = useState<
    CompanyJobDiscoveryResult[]
  >([]);
  const [companyJobsErrorMessage, setCompanyJobsErrorMessage] = useState<
    string | null
  >(null);
  const [submittedCompanyName, setSubmittedCompanyName] = useState<string | null>(
    null,
  );
  const [uploadedResumeFile, setUploadedResumeFile] = useState<File | null>(null);
  const [uploadedResumeResult, setUploadedResumeResult] =
    useState<UploadedResumeSearchResponse | null>(null);
  const [searchMode, setSearchMode] = useState<"job_brief" | "uploaded_resume" | null>(
    null,
  );

  useEffect(() => {
    if (!isFocusTermsAuto) {
      return;
    }

    setRetrievalFocusTerms(deriveRetrievalFocusTerms(jobDescription));
  }, [isFocusTermsAuto, jobDescription]);

  const loadingMessage = useMemo(
    () => buildLoadingMessage(activeRunMode),
    [activeRunMode],
  );
  const previewSkillNames = useMemo(() => {
    if (!previewProfile) {
      return [];
    }

    const values = previewProfile.skills
      .map((skill) => skill.canonical_name ?? skill.skill_name)
      .filter((value): value is string => Boolean(value && value.trim()));

    return [...new Set(values)];
  }, [previewProfile]);

  const searchResultCountLabel = useMemo(() => {
    if (submittedSearchQuery && searchResults.length === 0) {
      return "0 search results returned.";
    }

    if (searchResults.length === 0) {
      return "No search results returned yet.";
    }

    if (searchResults.length === 1) {
      return "1 search result returned.";
    }

    return `${searchResults.length} search results returned.`;
  }, [searchResults.length, submittedSearchQuery]);

  const shortlistCountLabel = useMemo(() => {
    if (submittedJobDescription && retrievedCandidateCount === 0) {
      return "0 shortlisted candidates. Retrieval returned no usable CVs.";
    }

    if (
      submittedJobDescription &&
      retrievedCandidateCount > 0 &&
      shortlistResults.length === 0
    ) {
      return "0 shortlisted candidates returned.";
    }

    if (shortlistResults.length === 0) {
      return "No shortlist returned yet.";
    }

    if (shortlistResults.length === 1) {
      return "1 shortlisted candidate.";
    }

    return `${shortlistResults.length} shortlisted candidates.`;
  }, [retrievedCandidateCount, shortlistResults.length, submittedJobDescription]);

  const companyDiscoveryCountLabel = useMemo(() => {
    if (submittedCompanyName && companyDiscoveryResults.length === 0) {
      return "0 company matches returned.";
    }

    if (companyDiscoveryResults.length === 0) {
      return "No company matches returned yet.";
    }

    if (companyDiscoveryResults.length === 1) {
      return "1 company match returned.";
    }

    return `${companyDiscoveryResults.length} company matches returned.`;
  }, [companyDiscoveryResults.length, submittedCompanyName]);

  const companyJobsCountLabel = useMemo(() => {
    if (submittedCompanyName && companyJobResults.length === 0) {
      return "0 jobs returned.";
    }

    if (companyJobResults.length === 0) {
      return "No jobs returned yet.";
    }

    if (companyJobResults.length === 1) {
      return "1 job returned.";
    }

    return `${companyJobResults.length} jobs returned.`;
  }, [companyJobResults.length, submittedCompanyName]);

  async function runSearch(options?: { focusQueryOverride?: string }): Promise<void> {
    const trimmedDescription = jobDescription.trim();
    const trimmedFocusQuery = (
      options?.focusQueryOverride ?? retrievalFocusTerms
    ).trim();

    if (trimmedDescription === "") {
      setSearchErrorMessage("Paste a role brief before running corpus search.");
      setSearchResults([]);
      return;
    }

    const resolvedQuery = trimmedFocusQuery || trimmedDescription;

    setIsSearchLoading(true);
    setActiveRunMode("search");
    setSearchErrorMessage(null);
    setSearchMode("job_brief");
    setUploadedResumeResult(null);

    try {
      const searchParams = new URLSearchParams({
        query: resolvedQuery,
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
        setSubmittedSearchQuery(resolvedQuery);
        setSearchErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Search request failed with ${response.status}.`,
        );
        return;
      }

      const searchResponse = payload as CandidateResumeSearchResponse;
      setSearchResults(searchResponse.results);
      setSubmittedSearchQuery(searchResponse.query);
      searchResultsSectionRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    } catch (error) {
      setSearchResults([]);
      setSubmittedSearchQuery(resolvedQuery);
      setSearchErrorMessage(
        error instanceof Error
          ? error.message
          : "Search request failed unexpectedly.",
      );
    } finally {
      setIsSearchLoading(false);
      setActiveRunMode(null);
    }
  }

  async function runUploadedResumeSearch(): Promise<void> {
    if (!uploadedResumeFile) {
      setSearchErrorMessage("Choose one PDF, DOCX, or DOC CV before searching.");
      setSearchResults([]);
      return;
    }

    setIsSearchLoading(true);
    setActiveRunMode("search");
    setSearchErrorMessage(null);
    setSearchMode("uploaded_resume");

    try {
      const contentBase64 = await encodeFileAsBase64(uploadedResumeFile);

      const response = await fetch(
        "/api/v1/candidates/search-uploaded-resume",
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            file_name: uploadedResumeFile.name,
            content_type: uploadedResumeFile.type || null,
            content_base64: contentBase64,
            limit: Number(searchResultLimit),
          }),
        },
      );

      const payload = (await response.json()) as unknown;

      if (!response.ok) {
        setSearchResults([]);
        setSubmittedSearchQuery(uploadedResumeFile.name);
        setUploadedResumeResult(null);
        setSearchErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Uploaded CV search failed with ${response.status}.`,
        );
        return;
      }

      const uploadResponse = payload as UploadedResumeSearchResponse;
      setSearchResults(uploadResponse.results);
      setSubmittedSearchQuery(uploadResponse.file_name ?? uploadedResumeFile.name);
      setUploadedResumeResult(uploadResponse);
      searchResultsSectionRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    } catch (error) {
      setSearchResults([]);
      setSubmittedSearchQuery(uploadedResumeFile.name);
      setUploadedResumeResult(null);
      setSearchErrorMessage(
        error instanceof Error
          ? error.message
          : "Uploaded CV search failed unexpectedly.",
      );
    } finally {
      setIsSearchLoading(false);
      setActiveRunMode(null);
    }
  }

  async function runShortlist(): Promise<void> {
    const trimmedDescription = jobDescription.trim();
    if (trimmedDescription === "") {
      setShortlistErrorMessage(
        "Paste a role brief before requesting a recruiter shortlist.",
      );
      setShortlistResults([]);
      return;
    }

    setIsShortlistLoading(true);
    setActiveRunMode("shortlist");
    setShortlistErrorMessage(null);

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
        setSubmittedJobDescription(trimmedDescription);
        setShortlistErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Shortlist request failed with ${response.status}.`,
        );
        return;
      }

      const shortlistResponse = payload as CandidateJobDescriptionMatchResponse;
      setShortlistResults(shortlistResponse.shortlisted_candidates);
      setRetrievedCandidateCount(shortlistResponse.retrieved_candidate_count);
      setSubmittedJobDescription(shortlistResponse.job_description);
      shortlistSectionRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    } catch (error) {
      setShortlistResults([]);
      setSubmittedJobDescription(trimmedDescription);
      setShortlistErrorMessage(
        error instanceof Error
          ? error.message
          : "Shortlist request failed unexpectedly.",
      );
    } finally {
      setIsShortlistLoading(false);
      setActiveRunMode(null);
    }
  }

  async function runCompanyDiscovery(): Promise<void> {
    const trimmedCompanyName = companyNameQuery.trim();
    if (trimmedCompanyName === "") {
      setCompanyDiscoveryErrorMessage("Enter a company name before searching.");
      setCompanyDiscoveryResults([]);
      return;
    }

    setCompanyDiscoveryLoading(true);
    setCompanyDiscoveryErrorMessage(null);
    setCompanyJobsErrorMessage(null);

    try {
      const searchParams = new URLSearchParams({
        company_name: trimmedCompanyName,
        limit: companySearchLimit,
      });

      const response = await fetch(
        `/api/v1/candidates/discover-by-company?${searchParams.toString()}`,
        {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
        },
      );

      const payload = (await response.json()) as unknown;

      if (!response.ok) {
        setCompanyDiscoveryResults([]);
        setSubmittedCompanyName(trimmedCompanyName);
        setCompanyDiscoveryErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Company discovery request failed with ${response.status}.`,
        );
        return;
      }

      const companyDiscoveryResponse = payload as CandidateCompanyDiscoveryResponse;
      setCompanyDiscoveryResults(companyDiscoveryResponse.results);
      setSubmittedCompanyName(companyDiscoveryResponse.company_name);

      const jobsResponse = await fetch(
        `/api/v1/candidates/discover-jobs-by-company?${searchParams.toString()}`,
        {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
        },
      );

      const jobsPayload = (await jobsResponse.json()) as unknown;

      if (!jobsResponse.ok) {
        setCompanyJobResults([]);
        setCompanyJobsErrorMessage(
          (isApiErrorResponse(jobsPayload) ? jobsPayload.error?.message : undefined) ??
            `Company jobs request failed with ${jobsResponse.status}.`,
        );
        return;
      }

      const companyJobsResponse = jobsPayload as CompanyJobDiscoveryResponse;
      setCompanyJobResults(companyJobsResponse.results);
    } catch (error) {
      setCompanyDiscoveryResults([]);
      setCompanyJobResults([]);
      setSubmittedCompanyName(trimmedCompanyName);
      setCompanyDiscoveryErrorMessage(
        error instanceof Error
          ? error.message
          : "Company discovery request failed unexpectedly.",
      );
    } finally {
      setCompanyDiscoveryLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runSearch();
  }

  function resetToExampleBrief(): void {
    setJobDescription(DEFAULT_JOB_DESCRIPTION);
    setIsFocusTermsAuto(true);
    setRetrievalFocusTerms(deriveRetrievalFocusTerms(DEFAULT_JOB_DESCRIPTION));
  }

  function clearWorkspace(): void {
    setJobDescription("");
    setRetrievalFocusTerms("");
    setIsFocusTermsAuto(true);
    setSearchResults([]);
    setShortlistResults([]);
    setSearchErrorMessage(null);
    setShortlistErrorMessage(null);
    setSubmittedSearchQuery(null);
    setSubmittedJobDescription(null);
    setRetrievedCandidateCount(0);
    setPreviewCandidateId(null);
    setPreviewProfile(null);
    setPreviewErrorMessage(null);
    setCandidateLeadCompanyName("");
    setCandidateLeadErrorMessage(null);
    setCandidateLeadResult(null);
    setCompanyNameQuery("");
    setCompanyDiscoveryResults([]);
    setCompanyDiscoveryErrorMessage(null);
    setCompanyJobResults([]);
    setCompanyJobsErrorMessage(null);
    setSubmittedCompanyName(null);
    setUploadedResumeFile(null);
    setUploadedResumeResult(null);
    setSearchMode(null);
    if (uploadedResumeInputRef.current) {
      uploadedResumeInputRef.current.value = "";
    }
  }

  async function openCandidatePreview(candidateId: string): Promise<void> {
    setPreviewCandidateId(candidateId);
    setPreviewLoading(true);
    setPreviewErrorMessage(null);
    setCandidateLeadErrorMessage(null);
    setCandidateLeadResult(null);

    try {
      const response = await fetch(`/api/v1/candidates/${candidateId}/profile`, {
        method: "GET",
        headers: {
          Accept: "application/json",
        },
      });

      const payload = (await response.json()) as unknown;

      if (!response.ok) {
        setPreviewProfile(null);
        setPreviewErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Candidate preview request failed with ${response.status}.`,
        );
        return;
      }

      setPreviewProfile(payload as CandidateProfileResponse);
    } catch (error) {
      setPreviewProfile(null);
      setPreviewErrorMessage(
        error instanceof Error
          ? error.message
          : "Candidate preview request failed unexpectedly.",
      );
    } finally {
      setPreviewLoading(false);
    }
  }

  async function runCandidateLeadDiscovery(): Promise<void> {
    if (!previewProfile) {
      setCandidateLeadErrorMessage(
        "Open a candidate preview before running company lead discovery.",
      );
      setCandidateLeadResult(null);
      return;
    }

    const trimmedCompanyName = candidateLeadCompanyName.trim();
    if (trimmedCompanyName === "") {
      setCandidateLeadErrorMessage("Enter a target company before running lead discovery.");
      setCandidateLeadResult(null);
      return;
    }

    setCandidateLeadLoading(true);
    setCandidateLeadErrorMessage(null);

    try {
      const searchParams = new URLSearchParams({
        company_name: trimmedCompanyName,
        limit: candidateLeadLimit,
      });

      const response = await fetch(
        `/api/v1/candidates/${previewProfile.candidate.candidate_id}/discover-company-leads?${searchParams.toString()}`,
        {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
        },
      );

      const payload = (await response.json()) as unknown;

      if (!response.ok) {
        setCandidateLeadResult(null);
        setCandidateLeadErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Candidate lead discovery request failed with ${response.status}.`,
        );
        return;
      }

      setCandidateLeadResult(payload as CandidateCompanyLeadDiscoveryResponse);
    } catch (error) {
      setCandidateLeadResult(null);
      setCandidateLeadErrorMessage(
        error instanceof Error
          ? error.message
          : "Candidate lead discovery request failed unexpectedly.",
      );
    } finally {
      setCandidateLeadLoading(false);
    }
  }

  return (
    <div className="grid gap-8">
      <section className="grid gap-4 border border-zinc-200 bg-white p-6 sm:p-8">
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="border border-zinc-200 p-4">
            <p className="text-xs font-semibold uppercase text-zinc-500">
              Stage 1
            </p>
            <p className="mt-2 text-lg font-semibold text-zinc-950">
              Hybrid retrieval
            </p>
            <p className="mt-2 text-sm leading-6 text-zinc-700">
              Search uses compact retrieval terms against the current CV corpus.
            </p>
          </div>

          <div className="border border-zinc-200 p-4">
            <p className="text-xs font-semibold uppercase text-zinc-500">
              Stage 2
            </p>
            <p className="mt-2 text-lg font-semibold text-zinc-950">
              LLM reranking
            </p>
            <p className="mt-2 text-sm leading-6 text-zinc-700">
              Shortlisting keeps the full role brief, then asks the reasoning
              model to rank the strongest retrieved candidates.
            </p>
          </div>

          <div className="border border-zinc-200 p-4">
            <p className="text-xs font-semibold uppercase text-zinc-500">
              Current goal
            </p>
            <p className="mt-2 text-lg font-semibold text-zinc-950">
              Recruiter-usable demo
            </p>
            <p className="mt-2 text-sm leading-6 text-zinc-700">
              The page should make the retrieval engine legible, not just return
              a black-box shortlist after a long wait.
            </p>
          </div>
        </div>

        <div className="border border-emerald-200 bg-emerald-50 p-4 text-sm leading-6 text-emerald-950">
          <p className="font-semibold">Recommended flow</p>
          <ol className="mt-2 grid gap-1 pl-5 list-decimal">
            <li>Paste the full role brief.</li>
            <li>Click <span className="font-semibold">Search corpus</span> to inspect the candidate pool.</li>
            <li>Open any candidate preview to sanity-check the retrieval.</li>
            <li>Click <span className="font-semibold">Shortlist top {shortlistLimit}</span> when the search pool looks sensible.</li>
          </ol>
        </div>
      </section>

      <section className="border border-zinc-200 bg-white p-6 sm:p-8">
        <form className="grid gap-6" onSubmit={handleSubmit}>
          <div className="grid gap-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <label
                className="text-sm font-semibold uppercase text-zinc-500"
                htmlFor="job-description"
              >
                Role brief
              </label>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={resetToExampleBrief}
                  className="inline-flex h-9 items-center justify-center rounded-md border border-zinc-300 bg-white px-3 text-sm font-semibold text-zinc-900 transition hover:border-zinc-500"
                >
                  Use example
                </button>
                <button
                  type="button"
                  onClick={clearWorkspace}
                  className="inline-flex h-9 items-center justify-center rounded-md border border-zinc-300 bg-white px-3 text-sm font-semibold text-zinc-900 transition hover:border-zinc-500"
                >
                  Clear
                </button>
              </div>
            </div>

            <textarea
              id="job-description"
              value={jobDescription}
              onChange={(event) => setJobDescription(event.target.value)}
              className="min-h-72 rounded-md border border-zinc-300 bg-white px-4 py-3 text-base leading-7 text-zinc-950 outline-none transition focus:border-zinc-500"
              placeholder="Paste the role brief here."
            />
            <p className="text-sm leading-6 text-zinc-600">
              Keep the full brief here. The shortlist step uses this full text
              for reranking.
            </p>
          </div>

          <div className="grid gap-3 border border-zinc-200 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <label
                  className="text-sm font-semibold uppercase text-zinc-500"
                  htmlFor="uploaded-resume"
                >
                  Reference CV upload
                </label>
                <p className="mt-2 text-sm leading-6 text-zinc-600">
                  Upload one CV to extract its text and use it as a transient
                  semantic query against the stored corpus. This first pass does
                  not persist the uploaded file.
                </p>
              </div>

              <button
                type="button"
                disabled={isSearchLoading || isShortlistLoading || !uploadedResumeFile}
                onClick={() => {
                  void runUploadedResumeSearch();
                }}
                className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-5 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500 disabled:cursor-not-allowed disabled:border-zinc-300 disabled:bg-zinc-200"
              >
                {isSearchLoading && searchMode === "uploaded_resume"
                  ? "Searching from CV..."
                  : "Search from uploaded CV"}
              </button>
            </div>

            <input
              id="uploaded-resume"
              ref={uploadedResumeInputRef}
              type="file"
              accept=".pdf,.docx,.doc,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(event) => {
                const selectedFile = event.target.files?.[0] ?? null;
                setUploadedResumeFile(selectedFile);
                setUploadedResumeResult(null);
              }}
              className="block w-full text-sm text-zinc-900 file:mr-4 file:rounded-md file:border file:border-zinc-300 file:bg-white file:px-4 file:py-2 file:text-sm file:font-semibold file:text-zinc-950 hover:file:border-zinc-500"
            />

            <p className="text-sm leading-6 text-zinc-600">
              {uploadedResumeFile
                ? `Selected file: ${uploadedResumeFile.name}`
                : "Supported formats: PDF, DOCX, DOC."}
            </p>
          </div>

          <div className="grid gap-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <label
                className="text-sm font-semibold uppercase text-zinc-500"
                htmlFor="retrieval-focus-terms"
              >
                Retrieval focus terms
              </label>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setIsFocusTermsAuto(true);
                    setRetrievalFocusTerms(deriveRetrievalFocusTerms(jobDescription));
                  }}
                  className="inline-flex h-9 items-center justify-center rounded-md border border-zinc-300 bg-white px-3 text-sm font-semibold text-zinc-900 transition hover:border-zinc-500"
                >
                  Regenerate terms
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsFocusTermsAuto(false);
                    setRetrievalFocusTerms(jobDescription.trim());
                  }}
                  className="inline-flex h-9 items-center justify-center rounded-md border border-zinc-300 bg-white px-3 text-sm font-semibold text-zinc-900 transition hover:border-zinc-500"
                >
                  Use full brief
                </button>
              </div>
            </div>

            <textarea
              id="retrieval-focus-terms"
              value={retrievalFocusTerms}
              onChange={(event) => {
                setIsFocusTermsAuto(false);
                setRetrievalFocusTerms(event.target.value);
              }}
              className="min-h-24 rounded-md border border-zinc-300 bg-white px-4 py-3 text-base leading-7 text-zinc-950 outline-none transition focus:border-zinc-500"
              placeholder="python sql aws data engineer etl"
            />
            <p className="text-sm leading-6 text-zinc-600">
              Corpus search starts with a short keyword query. If needed, the
              backend automatically retries broader fallbacks before giving up.
            </p>
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

      {loadingMessage ? (
        <section className="border border-sky-200 bg-sky-50 p-4 text-sm leading-6 text-sky-900">
          {loadingMessage}
        </section>
      ) : null}

      <section className="grid gap-4 border border-zinc-200 bg-white p-6 sm:p-8">
        <div className="flex flex-col gap-3 border-b border-zinc-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-3xl font-semibold text-zinc-950">
              Candidate preview
            </h2>
            <p className="mt-2 max-w-3xl text-base leading-7 text-zinc-700">
              Inspect the selected candidate in-page instead of jumping straight
              to raw JSON.
            </p>
          </div>

          <div className="text-sm text-zinc-600">
            {previewCandidateId
              ? `Selected: ${previewCandidateId}`
              : "Choose a candidate from search or shortlist."}
          </div>
        </div>

        {previewLoading ? (
          <div className="border border-sky-200 bg-sky-50 p-4 text-sm leading-6 text-sky-900">
            Loading candidate profile preview.
          </div>
        ) : null}

        {previewErrorMessage ? (
          <div className="border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
            {previewErrorMessage}
          </div>
        ) : null}

        {!previewLoading && !previewProfile && !previewErrorMessage ? (
          <div className="border border-dashed border-zinc-300 p-6 text-sm leading-7 text-zinc-600">
            Use any result card to preview the candidate profile, skills, and
            contact details here.
          </div>
        ) : null}

        {previewProfile ? (
          <article className="grid gap-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="max-w-3xl">
                <h3 className="text-2xl font-semibold text-zinc-950">
                  {previewProfile.candidate.full_name ?? "Unnamed candidate"}
                </h3>
                <p className="mt-2 text-base leading-7 text-zinc-700">
                  {previewProfile.candidate.current_title ?? "Title not available"}
                  {previewProfile.candidate.current_company_name
                    ? ` at ${previewProfile.candidate.current_company_name}`
                    : ""}
                </p>
                {previewProfile.candidate.headline ? (
                  <p className="mt-3 text-sm leading-6 text-zinc-900">
                    {previewProfile.candidate.headline}
                  </p>
                ) : null}
              </div>

              <a
                href={`/api/v1/candidates/${previewProfile.candidate.candidate_id}/profile`}
                className="inline-flex h-11 w-fit items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
              >
                Open profile JSON
              </a>
            </div>

            <dl className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <div>
                <dt className="text-xs font-semibold uppercase text-zinc-500">
                  Candidate status
                </dt>
                <dd className="mt-1 text-sm leading-6 text-zinc-900">
                  {previewProfile.candidate.candidate_status ?? "Unknown"}
                </dd>
              </div>

              <div>
                <dt className="text-xs font-semibold uppercase text-zinc-500">
                  Availability
                </dt>
                <dd className="mt-1 text-sm leading-6 text-zinc-900">
                  {previewProfile.candidate.availability_status ?? "Unknown"}
                </dd>
              </div>

              <div>
                <dt className="text-xs font-semibold uppercase text-zinc-500">
                  Resume updated
                </dt>
                <dd className="mt-1 text-sm leading-6 text-zinc-900">
                  {formatTimestamp(previewProfile.candidate.resume_updated_at)}
                </dd>
              </div>

              <div>
                <dt className="text-xs font-semibold uppercase text-zinc-500">
                  Last contacted
                </dt>
                <dd className="mt-1 text-sm leading-6 text-zinc-900">
                  {formatTimestamp(previewProfile.candidate.last_contacted_at)}
                </dd>
              </div>

              <div>
                <dt className="text-xs font-semibold uppercase text-zinc-500">
                  Email
                </dt>
                <dd className="mt-1 break-words text-sm leading-6 text-zinc-900">
                  {previewProfile.candidate.primary_email ?? "Not available"}
                </dd>
              </div>

              <div>
                <dt className="text-xs font-semibold uppercase text-zinc-500">
                  Phone
                </dt>
                <dd className="mt-1 break-words text-sm leading-6 text-zinc-900">
                  {previewProfile.candidate.primary_phone ?? "Not available"}
                </dd>
              </div>

              <div>
                <dt className="text-xs font-semibold uppercase text-zinc-500">
                  LinkedIn
                </dt>
                <dd className="mt-1 break-words text-sm leading-6 text-zinc-900">
                  {previewProfile.candidate.linkedin_url ? (
                    <a
                      href={previewProfile.candidate.linkedin_url}
                      target="_blank"
                      rel="noreferrer"
                      className="underline decoration-zinc-400 underline-offset-2"
                    >
                      {previewProfile.candidate.linkedin_url}
                    </a>
                  ) : (
                    "Not available"
                  )}
                </dd>
              </div>

              <div>
                <dt className="text-xs font-semibold uppercase text-zinc-500">
                  Location
                </dt>
                <dd className="mt-1 text-sm leading-6 text-zinc-900">
                  {previewProfile.candidate.location ?? "Unknown"}
                </dd>
              </div>
            </dl>

            {previewSkillNames.length > 0 ? (
              <div className="border border-zinc-200 p-4">
                <p className="text-xs font-semibold uppercase text-zinc-500">
                  Skills
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {previewSkillNames.map((skillName) => (
                    <span
                      key={skillName}
                      className="rounded-md border border-zinc-200 px-3 py-1 text-sm text-zinc-900"
                    >
                      {skillName}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            {previewProfile.candidate.summary ? (
              <div className="border border-zinc-200 p-4">
                <p className="text-xs font-semibold uppercase text-zinc-500">
                  Summary
                </p>
                <p className="mt-3 text-sm leading-7 text-zinc-900">
                  {previewProfile.candidate.summary}
                </p>
              </div>
            ) : null}
          </article>
        ) : null}

        {previewProfile ? (
          <div className="grid gap-6 border-t border-zinc-200 pt-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h3 className="text-2xl font-semibold text-zinc-950">
                  Candidate to company lead discovery
                </h3>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-700">
                  Use the selected candidate plus one target company to see who
                  we know there, what jobs already exist there, and what prior
                  interaction evidence is already in the database.
                </p>
              </div>

              {candidateLeadResult ? (
                <div className="text-sm text-zinc-600">
                  Target:{" "}
                  <span className="font-medium text-zinc-900">
                    {candidateLeadResult.company_name}
                  </span>
                </div>
              ) : null}
            </div>

            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_120px_auto] lg:items-end">
              <div className="grid gap-2">
                <label
                  className="text-sm font-semibold uppercase text-zinc-500"
                  htmlFor="candidate-lead-company-name"
                >
                  Target company
                </label>
                <input
                  id="candidate-lead-company-name"
                  type="text"
                  value={candidateLeadCompanyName}
                  onChange={(event) =>
                    setCandidateLeadCompanyName(event.target.value)
                  }
                  placeholder="Goldman Sachs"
                  className="h-12 rounded-md border border-zinc-300 bg-white px-4 text-base text-zinc-950 outline-none transition focus:border-zinc-500"
                />
              </div>

              <div className="grid gap-2">
                <label
                  className="text-sm font-semibold uppercase text-zinc-500"
                  htmlFor="candidate-lead-limit"
                >
                  Results
                </label>
                <select
                  id="candidate-lead-limit"
                  value={candidateLeadLimit}
                  onChange={(event) => setCandidateLeadLimit(event.target.value)}
                  className="h-12 rounded-md border border-zinc-300 bg-white px-4 text-base text-zinc-950 outline-none transition focus:border-zinc-500"
                >
                  <option value="5">Top 5</option>
                  <option value="10">Top 10</option>
                  <option value="20">Top 20</option>
                </select>
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => {
                    void runCandidateLeadDiscovery();
                  }}
                  disabled={candidateLeadLoading}
                  className="inline-flex h-12 items-center justify-center rounded-md bg-zinc-950 px-5 text-sm font-semibold text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400"
                >
                  {candidateLeadLoading ? "Searching..." : "Find company leads"}
                </button>

                {previewProfile.candidate.current_company_name ? (
                  <button
                    type="button"
                    onClick={() =>
                      setCandidateLeadCompanyName(
                        previewProfile.candidate.current_company_name ?? "",
                      )
                    }
                    className="inline-flex h-12 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                  >
                    Use current company
                  </button>
                ) : null}
              </div>
            </div>

            {candidateLeadErrorMessage ? (
              <div className="border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
                {candidateLeadErrorMessage}
              </div>
            ) : null}

            {candidateLeadResult ? (
              <div className="grid gap-6">
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  <div className="border border-zinc-200 p-4">
                    <p className="text-xs font-semibold uppercase text-zinc-500">
                      Selected candidate
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950">
                      {candidateLeadResult.candidate.full_name ?? "Unnamed candidate"}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-zinc-700">
                      {candidateLeadResult.candidate.current_title ??
                        "Title not available"}
                    </p>
                  </div>

                  <div className="border border-zinc-200 p-4">
                    <p className="text-xs font-semibold uppercase text-zinc-500">
                      Other candidates there
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950">
                      {candidateLeadResult.peer_candidates.length}
                    </p>
                  </div>

                  <div className="border border-zinc-200 p-4">
                    <p className="text-xs font-semibold uppercase text-zinc-500">
                      Known contacts
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950">
                      {candidateLeadResult.contacts.length}
                    </p>
                  </div>

                  <div className="border border-zinc-200 p-4">
                    <p className="text-xs font-semibold uppercase text-zinc-500">
                      Interaction evidence
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950">
                      {candidateLeadResult.interactions.length}
                    </p>
                  </div>
                </div>

                <div className="border border-zinc-200 p-4">
                  <p className="text-xs font-semibold uppercase text-zinc-500">
                    Candidate skills
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {candidateLeadResult.skill_names.length > 0 ? (
                      candidateLeadResult.skill_names.map((skillName) => (
                        <span
                          key={`lead-skill-${skillName}`}
                          className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-sm text-zinc-800"
                        >
                          {skillName}
                        </span>
                      ))
                    ) : (
                      <span className="text-sm leading-6 text-zinc-700">
                        No structured skills are linked to this candidate yet.
                      </span>
                    )}
                  </div>
                </div>

                {candidateLeadResult.candidate_already_at_company ? (
                  <div className="border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
                    This candidate is already marked as currently working at{" "}
                    {candidateLeadResult.company_name}.
                  </div>
                ) : null}

                <div className="grid gap-6 xl:grid-cols-2">
                  <div className="grid gap-4">
                    <div>
                      <h4 className="text-xl font-semibold text-zinc-950">
                        Contacts and hiring managers
                      </h4>
                      <p className="mt-2 text-sm leading-6 text-zinc-700">
                        People already linked to the target company.
                      </p>
                    </div>

                    {candidateLeadResult.contacts.length === 0 ? (
                      <div className="border border-zinc-200 bg-zinc-50 p-4 text-sm leading-6 text-zinc-700">
                        No contacts are linked to this company yet.
                      </div>
                    ) : (
                      candidateLeadResult.contacts.map((contact) => (
                        <article
                          key={contact.contact_id}
                          className="border border-zinc-200 p-4"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            {contact.is_hiring_manager ? (
                              <span className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800">
                                Hiring manager
                              </span>
                            ) : null}
                            <span className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700">
                              {formatCompanyMatchSourceLabel(
                                contact.company_match_source,
                              )}
                            </span>
                          </div>
                          <h5 className="mt-3 text-lg font-semibold text-zinc-950">
                            {contact.full_name ?? "Unnamed contact"}
                          </h5>
                          <p className="mt-1 text-sm leading-6 text-zinc-700">
                            {contact.role_title ?? contact.headline ?? "Role not available"}
                          </p>
                          <dl className="mt-4 grid gap-2 text-sm leading-6 text-zinc-800">
                            <div>
                              <dt className="inline font-semibold">Email:</dt>{" "}
                              <dd className="inline">
                                {contact.primary_email ?? "Not available"}
                              </dd>
                            </div>
                            <div>
                              <dt className="inline font-semibold">Phone:</dt>{" "}
                              <dd className="inline">
                                {contact.primary_phone ?? "Not available"}
                              </dd>
                            </div>
                            <div>
                              <dt className="inline font-semibold">LinkedIn:</dt>{" "}
                              <dd className="inline break-all">
                                {contact.linkedin_url ?? "Not available"}
                              </dd>
                            </div>
                          </dl>
                        </article>
                      ))
                    )}
                  </div>

                  <div className="grid gap-4">
                    <div>
                      <h4 className="text-xl font-semibold text-zinc-950">
                        Prior interaction evidence
                      </h4>
                      <p className="mt-2 text-sm leading-6 text-zinc-700">
                        Notes, emails, or other interaction rows tied to that company.
                      </p>
                    </div>

                    {candidateLeadResult.interactions.length === 0 ? (
                      <div className="border border-zinc-200 bg-zinc-50 p-4 text-sm leading-6 text-zinc-700">
                        No recent interaction evidence was returned.
                      </div>
                    ) : (
                      candidateLeadResult.interactions.map((interaction) => (
                        <article
                          key={interaction.interaction_id}
                          className="border border-zinc-200 p-4"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700">
                              {formatUnderscoredLabel(interaction.interaction_type)}
                            </span>
                            <span className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700">
                              {formatUnderscoredLabel(interaction.matched_entity_type)}
                            </span>
                          </div>
                          <h5 className="mt-3 text-lg font-semibold text-zinc-950">
                            {interaction.full_name ?? interaction.subject ?? "Interaction"}
                          </h5>
                          <p className="mt-1 text-sm leading-6 text-zinc-700">
                            {interaction.role_title ?? interaction.company_name ?? "No role title"}
                          </p>
                          <p className="mt-3 text-sm leading-6 text-zinc-900">
                            {interaction.summary ??
                              interaction.subject ??
                              interaction.body ??
                              "No interaction summary available."}
                          </p>
                          <p className="mt-3 text-xs uppercase text-zinc-500">
                            {formatTimestamp(interaction.occurred_at)} |{" "}
                            {interaction.source_system ?? "Unknown source"}
                          </p>
                        </article>
                      ))
                    )}
                  </div>
                </div>

                <div className="grid gap-6 xl:grid-cols-2">
                  <div className="grid gap-4">
                    <div>
                      <h4 className="text-xl font-semibold text-zinc-950">
                        Known jobs at this company
                      </h4>
                      <p className="mt-2 text-sm leading-6 text-zinc-700">
                        Existing jobs already linked to the same target company.
                      </p>
                    </div>

                    {candidateLeadResult.jobs.length === 0 ? (
                      <div className="border border-zinc-200 bg-zinc-50 p-4 text-sm leading-6 text-zinc-700">
                        No canonical jobs are linked to this company yet.
                      </div>
                    ) : (
                      candidateLeadResult.jobs.map((job) => (
                        <article key={job.job_id} className="border border-zinc-200 p-4">
                          <h5 className="text-lg font-semibold text-zinc-950">
                            {job.title ?? "Untitled job"}
                          </h5>
                          <p className="mt-1 text-sm leading-6 text-zinc-700">
                            {job.location ?? "Location not available"}
                          </p>
                          <p className="mt-3 text-sm leading-6 text-zinc-900">
                            Hiring manager:{" "}
                            {job.hiring_manager_name ?? "Not linked yet"}
                          </p>
                          <p className="mt-2 text-xs uppercase text-zinc-500">
                            {job.status ?? "Unknown status"} |{" "}
                            {formatTimestamp(job.updated_from_source_at)}
                          </p>
                        </article>
                      ))
                    )}
                  </div>

                  <div className="grid gap-4">
                    <div>
                      <h4 className="text-xl font-semibold text-zinc-950">
                        Other candidates already there
                      </h4>
                      <p className="mt-2 text-sm leading-6 text-zinc-700">
                        Existing candidate records already tied to the target company.
                      </p>
                    </div>

                    {candidateLeadResult.peer_candidates.length === 0 ? (
                      <div className="border border-zinc-200 bg-zinc-50 p-4 text-sm leading-6 text-zinc-700">
                        No other linked candidates were returned for this company.
                      </div>
                    ) : (
                      candidateLeadResult.peer_candidates.map((peer) => (
                        <article
                          key={`${peer.candidate_id}-${peer.document_id}-peer`}
                          className="border border-zinc-200 p-4"
                        >
                          <h5 className="text-lg font-semibold text-zinc-950">
                            {peer.full_name ?? "Unnamed candidate"}
                          </h5>
                          <p className="mt-1 text-sm leading-6 text-zinc-700">
                            {peer.current_title ?? "Title not available"}
                          </p>
                          <p className="mt-3 text-sm leading-6 text-zinc-900">
                            {renderHighlightedExcerpt(peer.match_excerpt)}
                          </p>
                        </article>
                      ))
                    )}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="grid gap-6 border-t border-zinc-200 pt-8">
        <div className="flex flex-col gap-3 border-b border-zinc-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-3xl font-semibold text-zinc-950">
              Company discovery
            </h2>
            <p className="mt-2 max-w-3xl text-base leading-7 text-zinc-700">
              Find candidates already linked to a company, then inspect the CV
              evidence before outreach.
            </p>
          </div>

          <div className="text-sm text-zinc-600">
            {submittedCompanyName
              ? companyDiscoveryCountLabel
              : "Search a company to find linked candidates."}
          </div>
        </div>

        <div className="border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
          This is the company-first view. If you already have one candidate in
          mind, use the candidate preview section above to run the more direct
          company lead workflow for that person.
        </div>

        <div className="grid gap-6 border border-zinc-200 bg-white p-6">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_120px_auto] lg:items-end">
            <div className="grid gap-2">
              <label
                className="text-sm font-semibold uppercase text-zinc-500"
                htmlFor="company-name-query"
              >
                Company name
              </label>
              <input
                id="company-name-query"
                type="text"
                value={companyNameQuery}
                onChange={(event) => setCompanyNameQuery(event.target.value)}
                placeholder="Goldman Sachs"
                className="h-12 rounded-md border border-zinc-300 bg-white px-4 text-base text-zinc-950 outline-none transition focus:border-zinc-500"
              />
            </div>

            <div className="grid gap-2">
              <label
                className="text-sm font-semibold uppercase text-zinc-500"
                htmlFor="company-search-limit"
              >
                Results
              </label>
              <select
                id="company-search-limit"
                value={companySearchLimit}
                onChange={(event) => setCompanySearchLimit(event.target.value)}
                className="h-12 rounded-md border border-zinc-300 bg-white px-4 text-base text-zinc-950 outline-none transition focus:border-zinc-500"
              >
                <option value="5">Top 5</option>
                <option value="10">Top 10</option>
                <option value="20">Top 20</option>
                <option value="25">Top 25</option>
              </select>
            </div>

            <button
              type="button"
              onClick={() => {
                void runCompanyDiscovery();
              }}
              disabled={companyDiscoveryLoading}
              className="inline-flex h-12 items-center justify-center rounded-md bg-zinc-950 px-5 text-sm font-semibold text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400"
            >
              {companyDiscoveryLoading ? "Searching..." : "Search company"}
            </button>
          </div>

          {submittedCompanyName ? (
            <p className="text-sm leading-6 text-zinc-600">
              Company query:{" "}
              <span className="font-medium text-zinc-900">
                {submittedCompanyName}
              </span>
            </p>
          ) : null}

          {companyDiscoveryErrorMessage ? (
            <div className="border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
              {companyDiscoveryErrorMessage}
            </div>
          ) : null}

          {submittedCompanyName &&
          companyDiscoveryResults.length === 0 &&
          !companyDiscoveryErrorMessage ? (
            <div className="border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
              No linked candidates were returned for that company query.
            </div>
          ) : null}

          {companyDiscoveryResults.length === 0 && !companyDiscoveryErrorMessage ? (
            <div className="border border-dashed border-zinc-300 p-6 text-sm leading-7 text-zinc-600">
              Use this when you know the target company first and want to see
              who in the canonical CV corpus is already there.
            </div>
          ) : null}

          <div className="grid gap-5">
            {companyDiscoveryResults.map((result, index) => (
              <article
                key={`${result.candidate_id}-${result.document_id}-company`}
                className="border border-zinc-200 bg-white p-6"
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="max-w-3xl">
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800">
                        Rank {index + 1}
                      </span>
                      <span className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700">
                        Evidence {result.company_match_score.toFixed(3)}
                      </span>
                      <span className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700">
                        {formatCompanyMatchSourceLabel(result.company_match_source)}
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

                  <div className="flex flex-wrap gap-3">
                    <a
                      href={`/api/v1/candidates/${result.candidate_id}/current-resume`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                    >
                      Open CV
                    </a>

                    <button
                      type="button"
                      onClick={() => {
                        void openCandidatePreview(result.candidate_id);
                      }}
                      className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                    >
                      Preview candidate
                    </button>

                    <a
                      href={`/api/v1/candidates/${result.candidate_id}/profile`}
                      className="inline-flex h-11 w-fit items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                    >
                      Open JSON
                    </a>
                  </div>
                </div>

                <dl className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <div>
                    <dt className="text-xs font-semibold uppercase text-zinc-500">
                      Match source
                    </dt>
                    <dd className="mt-1 text-sm leading-6 text-zinc-900">
                      {formatCompanyMatchSourceLabel(result.company_match_source)}
                    </dd>
                  </div>

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
                </dl>

                <div className="mt-6 border border-zinc-200 p-4">
                  <p className="text-xs font-semibold uppercase text-zinc-500">
                    Evidence
                  </p>
                  <p className="mt-3 text-sm leading-7 text-zinc-900">
                    {renderHighlightedExcerpt(result.match_excerpt)}
                  </p>
                </div>
              </article>
            ))}
          </div>

          <div className="grid gap-4 border-t border-zinc-200 pt-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h3 className="text-2xl font-semibold text-zinc-950">
                  Known jobs at this company
                </h3>
                <p className="mt-2 text-sm leading-6 text-zinc-700">
                  Canonical jobs already linked to the same company.
                </p>
              </div>

              <div className="text-sm text-zinc-600">{companyJobsCountLabel}</div>
            </div>

            {companyJobsErrorMessage ? (
              <div className="border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
                {companyJobsErrorMessage}
              </div>
            ) : null}

            {submittedCompanyName &&
            companyJobResults.length === 0 &&
            !companyJobsErrorMessage ? (
              <div className="border border-zinc-200 bg-zinc-50 p-4 text-sm leading-6 text-zinc-700">
                No canonical jobs are linked to that company query yet.
              </div>
            ) : null}

            <div className="grid gap-5">
              {companyJobResults.map((result, index) => (
                <article
                  key={result.job_id}
                  className="border border-zinc-200 bg-white p-6"
                >
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="max-w-3xl">
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800">
                          Job {index + 1}
                        </span>
                        <span className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700">
                          {result.status ?? "Unknown status"}
                        </span>
                        <span className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700">
                          {result.source ?? "Unknown source"}
                        </span>
                      </div>

                      <h4 className="mt-4 text-2xl font-semibold text-zinc-950">
                        {result.title ?? "Untitled job"}
                      </h4>

                      <p className="mt-2 text-base leading-7 text-zinc-700">
                        {result.company_name ?? "Unknown company"}
                        {result.location ? ` | ${result.location}` : ""}
                      </p>
                    </div>
                  </div>

                  <dl className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    <div>
                      <dt className="text-xs font-semibold uppercase text-zinc-500">
                        Owner
                      </dt>
                      <dd className="mt-1 text-sm leading-6 text-zinc-900">
                        {result.owner_name ?? "Unknown"}
                      </dd>
                    </div>

                    <div>
                      <dt className="text-xs font-semibold uppercase text-zinc-500">
                        Workplace
                      </dt>
                      <dd className="mt-1 text-sm leading-6 text-zinc-900">
                        {result.workplace_type ?? "Unknown"}
                      </dd>
                    </div>

                    <div>
                      <dt className="text-xs font-semibold uppercase text-zinc-500">
                        Employment
                      </dt>
                      <dd className="mt-1 text-sm leading-6 text-zinc-900">
                        {result.employment_type ?? "Unknown"}
                      </dd>
                    </div>

                    <div>
                      <dt className="text-xs font-semibold uppercase text-zinc-500">
                        Source updated
                      </dt>
                      <dd className="mt-1 text-sm leading-6 text-zinc-900">
                        {formatTimestamp(result.updated_from_source_at)}
                      </dd>
                    </div>
                  </dl>

                  <div className="mt-6 border border-zinc-200 p-4">
                    <p className="text-xs font-semibold uppercase text-zinc-500">
                      Hiring-manager contact
                    </p>
                    <p className="mt-3 text-sm leading-7 text-zinc-900">
                      {result.hiring_manager_name
                        ? `${result.hiring_manager_name}${result.hiring_manager_role_title ? ` | ${result.hiring_manager_role_title}` : ""}`
                        : "No hiring-manager contact is linked on this canonical job yet."}
                    </p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section ref={shortlistSectionRef} className="grid gap-6">
        <div className="flex flex-col gap-3 border-b border-zinc-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-3xl font-semibold text-zinc-950">
              Recruiter shortlist
            </h2>
            <p className="mt-2 max-w-3xl text-base leading-7 text-zinc-700">
              Full role brief plus LLM reranking over the retrieved candidate
              pool.
            </p>
          </div>

          <div className="text-sm text-zinc-600">
            {submittedJobDescription
              ? shortlistCountLabel
              : "Run shortlist to see the top fit."}
          </div>
        </div>

        {submittedJobDescription && retrievedCandidateCount > 0 ? (
          <p className="text-sm leading-6 text-zinc-600">
            Candidate pool sent to reranking:{" "}
            <span className="font-medium text-zinc-900">
              {retrievedCandidateCount}
            </span>
          </p>
        ) : null}

        {submittedJobDescription && retrievedCandidateCount === 0 && !shortlistErrorMessage ? (
          <div className="border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
            Retrieval did not find a useful candidate pool for that brief. Try
            running corpus search first with tighter focus terms, then shortlist
            again.
          </div>
        ) : null}

        {shortlistErrorMessage ? (
          <div className="border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
            {shortlistErrorMessage}
          </div>
        ) : null}

        {shortlistResults.length === 0 && !shortlistErrorMessage ? (
          <div className="border border-dashed border-zinc-300 p-6 text-sm leading-7 text-zinc-600">
            Use the shortlist action when you want the reasoning model to turn
            retrieval output into a recruiter-style top list with strengths,
            gaps, and fit summaries.
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
                    {result.retrieval_sources.map((source) => (
                      <span
                        key={`${result.candidate_id}-${source}`}
                        className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700"
                      >
                        {formatRetrievalSourceLabel(source)}
                      </span>
                    ))}
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

                <div className="flex flex-wrap gap-3">
                  <a
                    href={`/api/v1/candidates/${result.candidate_id}/current-resume`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                  >
                    Open CV
                  </a>

                  <button
                    type="button"
                    onClick={() => {
                      void openCandidatePreview(result.candidate_id);
                    }}
                    className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                  >
                    Preview candidate
                  </button>

                  <a
                    href={`/api/v1/candidates/${result.candidate_id}/profile`}
                    className="inline-flex h-11 w-fit items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                  >
                    Open JSON
                  </a>
                </div>
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
                <div className="border border-zinc-200 p-4">
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

                <div className="border border-zinc-200 p-4">
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

              {renderRetrievalDiagnostics(result, {
                primaryScoreLabel: "Fused retrieval",
                primaryScoreValue: result.retrieval_score,
              })}

              <div className="mt-6 border border-zinc-200 p-4">
                <p className="text-xs font-semibold uppercase text-zinc-500">
                  Resume evidence
                </p>
                <p className="mt-3 text-sm leading-7 text-zinc-900">
                  {renderHighlightedExcerpt(result.match_excerpt)}
                </p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section ref={searchResultsSectionRef} className="grid gap-6">
        <div className="flex flex-col gap-3 border-b border-zinc-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-3xl font-semibold text-zinc-950">
              Corpus search
            </h2>
            <p className="mt-2 max-w-3xl text-base leading-7 text-zinc-700">
              Hybrid retrieval results from the canonical current-resume corpus.
            </p>
          </div>

          <div className="text-sm text-zinc-600">
            {submittedSearchQuery
              ? searchResultCountLabel
              : "Run corpus search to inspect the candidate pool."}
          </div>
        </div>

        {submittedSearchQuery ? (
          <div className="grid gap-1 text-sm leading-6 text-zinc-600">
            <p>
              {searchMode === "uploaded_resume" ? "Uploaded CV query: " : "Retrieval terms: "}
              <span className="font-medium text-zinc-900">
                {submittedSearchQuery}
              </span>
            </p>
            {uploadedResumeResult ? (
              <>
                <p>
                  Extractor:{" "}
                  <span className="font-medium text-zinc-900">
                    {uploadedResumeResult.extractor ?? "Unknown"}
                  </span>
                  {uploadedResumeResult.page_count
                    ? `, pages: ${uploadedResumeResult.page_count}`
                    : ""}
                  {`, cleaned characters: ${uploadedResumeResult.character_count}`}
                </p>
                <p>
                  Extracted preview:{" "}
                  <span className="font-medium text-zinc-900">
                    {uploadedResumeResult.cleaned_text_preview}
                  </span>
                </p>
              </>
            ) : null}
            {submittedJobDescription ? (
              <p>Shortlist reasoning still uses the full brief above.</p>
            ) : null}
          </div>
        ) : null}

        {submittedSearchQuery && searchResults.length === 0 && !searchErrorMessage ? (
          <div className="grid gap-3 border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
            <p>
              Corpus search returned no CV matches for that retrieval query.
            </p>
            {searchMode !== "uploaded_resume" &&
            jobDescription.trim() !== retrievalFocusTerms.trim() ? (
              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setIsFocusTermsAuto(false);
                    setRetrievalFocusTerms(jobDescription.trim());
                    void runSearch({
                      focusQueryOverride: jobDescription.trim(),
                    });
                  }}
                  className="inline-flex h-10 items-center justify-center rounded-md border border-amber-300 bg-white px-4 text-sm font-semibold text-amber-950 transition hover:border-amber-500"
                >
                  Retry with full brief
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsFocusTermsAuto(true);
                    const regeneratedTerms = deriveRetrievalFocusTerms(
                      jobDescription,
                    );
                    setRetrievalFocusTerms(regeneratedTerms);
                    void runSearch({
                      focusQueryOverride: regeneratedTerms,
                    });
                  }}
                  className="inline-flex h-10 items-center justify-center rounded-md border border-amber-300 bg-white px-4 text-sm font-semibold text-amber-950 transition hover:border-amber-500"
                >
                  Retry with regenerated terms
                </button>
              </div>
            ) : null}
          </div>
        ) : null}

        {searchErrorMessage ? (
          <div className="border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
            {searchErrorMessage}
          </div>
        ) : null}

        {searchResults.length === 0 && !searchErrorMessage ? (
          <div className="border border-dashed border-zinc-300 p-6 text-sm leading-7 text-zinc-600">
            Start here when you want to inspect the raw candidate pool before
            running the LLM shortlist. This helps you sanity-check whether the
            retrieval layer is seeing the right CVs.
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
                    {result.retrieval_sources.map((source) => (
                      <span
                        key={`${result.candidate_id}-${source}`}
                        className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700"
                      >
                        {formatRetrievalSourceLabel(source)}
                      </span>
                    ))}
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

                <div className="flex flex-wrap gap-3">
                  <a
                    href={`/api/v1/candidates/${result.candidate_id}/current-resume`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                  >
                    Open CV
                  </a>

                  <button
                    type="button"
                    onClick={() => {
                      void openCandidatePreview(result.candidate_id);
                    }}
                    className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                  >
                    Preview candidate
                  </button>

                  <a
                    href={`/api/v1/candidates/${result.candidate_id}/profile`}
                    className="inline-flex h-11 w-fit items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                  >
                    Open JSON
                  </a>
                </div>
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

              {renderRetrievalDiagnostics(result, {
                primaryScoreLabel: "Fused retrieval",
                primaryScoreValue: result.match_score,
              })}

              <div className="mt-6 border border-zinc-200 p-4">
                <p className="text-xs font-semibold uppercase text-zinc-500">
                  Resume evidence
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
