"use client";

import {
  FormEvent,
  ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { CandidateComparison } from "./candidate-comparison";

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
  document_id: string | null;
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
  source_systems: string[];
  source_category: string;
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
  person_id: string | null;
  candidate_id: string | null;
  company_id: string | null;
  company_name: string | null;
  full_name: string | null;
  role_title: string | null;
  contact_id: string | null;
  job_id: string | null;
  job_title: string | null;
  candidate_last_contacted_at: string | null;
  matched_entity_type: string;
};

type CompanyInteractionDiscoveryResponse = {
  company_name: string;
  limit: number;
  results: CompanyInteractionDiscoveryResult[];
};

type CompanyOpportunityDiscoveryResult = {
  opportunity_id: string;
  title: string | null;
  smart_summary: string | null;
  stage: string | null;
  last_contact_at: string | null;
  next_task_at: string | null;
  value: number | null;
  company_id: string | null;
  company_name: string | null;
  contact_id: string | null;
  contact_person_id: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  contact_role_title: string | null;
  company_match_source: string;
};

type CompanyOpportunityDiscoveryResponse = {
  company_name: string;
  limit: number;
  results: CompanyOpportunityDiscoveryResult[];
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
  opportunities: CompanyOpportunityDiscoveryResult[];
};

type UploadedJobDescriptionExtractResponse = {
  file_name: string | null;
  content_type: string | null;
  extractor: string | null;
  page_count: number | null;
  character_count: number;
  cleaned_text_preview: string;
  job_description_text: string;
};

type CandidateJobDescriptionShortlistItem = {
  candidate_id: string;
  person_id: string;
  full_name: string | null;
  current_title: string | null;
  candidate_status: string | null;
  current_company_name: string | null;
  resume_updated_at: string | null;
  document_id: string | null;
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
  source_systems: string[];
  source_category: string;
  graph_context_score: number | null;
  ranking_input_score: number | null;
  fit_score: number;
  fit_summary: string;
  strengths: string[];
  gaps: string[];
  match_excerpt: string | null;
  graph_evidence: {
    candidate_id: string;
    current_company_name: string | null;
    skill_names: string[];
    recent_employment?: CandidateEmploymentRole[];
    contacts_count: number;
    interactions_count: number;
    jobs_count: number;
    opportunities_count: number;
    contacts: CompanyContactDiscoveryResult[];
    interactions: CompanyInteractionDiscoveryResult[];
    jobs: CompanyJobDiscoveryResult[];
    opportunities: CompanyOpportunityDiscoveryResult[];
  } | null;
};

type CandidateJobDescriptionMatchResponse = {
  match_run_id: string;
  job_description: string;
  retrieval_limit: number;
  shortlist_limit: number;
  retrieved_candidate_count: number;
  shortlisted_candidates: CandidateJobDescriptionShortlistItem[];
};

type CandidateMatchFeedbackValue = "good_match" | "not_suitable";

type CandidateMatchFeedbackState = {
  value: CandidateMatchFeedbackValue | null;
  reason: string;
  status: "idle" | "saving" | "saved" | "error";
  message: string | null;
};

type CandidateMatchFeedbackResponse = {
  feedback_id: string;
  match_run_id: string;
  candidate_id: string;
  feedback_value: CandidateMatchFeedbackValue;
  feedback_reason: string | null;
  updated_at: string;
};

type CandidateShortlistShareResponse = {
  share_id: string;
  match_run_id: string;
  role_title: string | null;
  job_description: string;
  shortlisted_candidates: CandidateJobDescriptionShortlistItem[];
  created_by_email: string | null;
  created_at: string;
  updated_at: string;
  expires_at: string;
  revoked_at: string | null;
  can_revoke: boolean;
};

type CandidateSavedBriefSummary = {
  saved_brief_id: string;
  title: string;
  target_company_name: string | null;
  job_description_preview: string;
  last_match_run_id: string | null;
  retrieved_candidate_count: number;
  search_result_count: number;
  shortlist_count: number;
  created_at: string;
  updated_at: string;
};

type CandidateSavedBriefListResponse = {
  saved_briefs: CandidateSavedBriefSummary[];
  count: number;
};

type CandidateSavedBriefResponse = {
  saved_brief_id: string;
  title: string;
  job_description: string;
  target_company_name: string | null;
  retrieval_focus_terms: string;
  search_result_limit: number;
  retrieval_limit: number;
  shortlist_limit: number;
  last_match_run_id: string | null;
  retrieved_candidate_count: number;
  search_results: CandidateResumeSearchResult[];
  shortlisted_candidates: CandidateJobDescriptionShortlistItem[];
  created_at: string;
  updated_at: string;
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

type CandidateEmploymentRole = {
  employment_role_id?: string | null;
  company_id?: string | null;
  company_name: string | null;
  role_title: string | null;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
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
  recent_employment: CandidateEmploymentRole[];
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
  "essential",
  "experience",
  "for",
  "from",
  "grade",
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
  "key",
  "large",
  "location",
  "looking",
  "modern",
  "more",
  "most",
  "need",
  "of",
  "on",
  "or",
  "production",
  "qualification",
  "qualifications",
  "reporting",
  "requirements",
  "role",
  "search",
  "salary",
  "senior",
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
  "title",
  "to",
  "use",
  "we",
  "week",
  "what",
  "when",
  "where",
  "who",
  "with",
  "worked",
  "workflow",
]);

const RETRIEVAL_BOOSTED_TERMS = new Set([
  "analyst",
  "analytics",
  "aws",
  "c#",
  "c++",
  "cloud",
  "cognos",
  "data",
  "developer",
  "docker",
  "etl",
  "finance",
  "financial",
  "hft",
  "ibm",
  "java",
  "kdb",
  "kubernetes",
  "otc",
  "planning",
  "pricing",
  "python",
  "quant",
  "quantitative",
  "q/kdb+",
  "rust",
  "sql",
  "tm1",
  "trading",
  "turbointegrator",
]);

const RETRIEVAL_LOW_SIGNAL_TERMS = new Set([
  "business",
  "company",
  "customer",
  "customers",
  "delivery",
  "global",
  "group",
  "industry",
  "information",
  "lead",
  "management",
  "manager",
  "market",
  "markets",
  "office",
  "partner",
  "project",
  "projects",
  "support",
  "team",
  "working",
]);

function isApiErrorResponse(payload: unknown): payload is ApiErrorResponse {
  if (typeof payload !== "object" || payload === null) {
    return false;
  }

  return "error" in payload;
}

async function readJsonResponse(response: Response): Promise<unknown> {
  const responseText = await response.text();
  if (responseText.trim() === "") {
    return null;
  }

  try {
    return JSON.parse(responseText) as unknown;
  } catch {
    return responseText;
  }
}

function getAttachmentFileName(
  contentDisposition: string | null,
  fallback: string,
): string {
  if (!contentDisposition) {
    return fallback;
  }

  const encodedMatch = contentDisposition.match(
    /filename\*=UTF-8''([^;]+)/i,
  );
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1]);
    } catch {
      return fallback;
    }
  }

  const quotedMatch = contentDisposition.match(/filename="([^"]+)"/i);
  return quotedMatch?.[1] || fallback;
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

function formatEmploymentPeriod(role: CandidateEmploymentRole): string {
  const formatDate = (value: string | null): string | null => {
    if (!value) {
      return null;
    }

    const parsed = new Date(`${value.slice(0, 10)}T00:00:00Z`);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }

    return new Intl.DateTimeFormat("en-GB", {
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    }).format(parsed);
  };

  const start = formatDate(role.start_date);
  const end = role.is_current ? "Present" : formatDate(role.end_date);

  if (start && end) {
    return `${start} – ${end}`;
  }
  if (start) {
    return `From ${start}`;
  }
  if (end) {
    return role.is_current ? "Current role" : `Until ${end}`;
  }
  return role.is_current ? "Current role" : "Dates unavailable";
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

function formatCandidateSourceCategory(sourceCategory: string): string {
  if (sourceCategory === "cross_source") {
    return "Cross-source";
  }

  if (sourceCategory === "linkedin_helper_only") {
    return "Linked Helper only";
  }

  if (sourceCategory === "cv_backed") {
    return "CV-backed";
  }

  return "Source unconfirmed";
}

function candidateSourceCategoryClassName(sourceCategory: string): string {
  if (sourceCategory === "cross_source") {
    return "border-teal-200 bg-teal-50 text-teal-800";
  }

  if (sourceCategory === "linkedin_helper_only") {
    return "border-sky-200 bg-sky-50 text-sky-800";
  }

  if (sourceCategory === "cv_backed") {
    return "border-zinc-200 bg-zinc-50 text-zinc-700";
  }

  return "border-amber-200 bg-amber-50 text-amber-800";
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

function formatCurrencyValue(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "Unknown";
  }

  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    maximumFractionDigits: 0,
  }).format(value);
}

function deriveRetrievalFocusTerms(jobDescription: string): string {
  const normalizedTerms =
    jobDescription.match(/[A-Za-z0-9+#./-]+/g)?.map((term) => term.trim()) ?? [];

  const seenTerms = new Set<string>();
  const scoredTerms: Array<{
    canonicalTerm: string;
    index: number;
    score: number;
  }> = [];

  for (const [index, originalTerm] of normalizedTerms.entries()) {
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
    let score = 0;

    if (RETRIEVAL_BOOSTED_TERMS.has(canonicalTerm)) {
      score += 8;
    }
    if (RETRIEVAL_LOW_SIGNAL_TERMS.has(canonicalTerm)) {
      score -= 4;
    }
    if (/\d/.test(canonicalTerm)) {
      score += 5;
    }
    if (/[+#./]/.test(canonicalTerm)) {
      score += 4;
    }
    if (originalTerm === originalTerm.toUpperCase() && originalTerm.length >= 2) {
      score += 2;
    }
    if (canonicalTerm.length >= 12) {
      score += 3;
    } else if (canonicalTerm.length >= 8) {
      score += 2;
    } else if (canonicalTerm.length >= 5) {
      score += 1;
    }

    scoredTerms.push({
      canonicalTerm,
      index,
      score,
    });
  }

  const selectedTerms = scoredTerms
    .sort((left, right) => {
      if (right.score !== left.score) {
        return right.score - left.score;
      }
      return left.index - right.index;
    })
    .slice(0, 9)
    .sort((left, right) => left.index - right.index)
    .map((term) => term.canonicalTerm);

  return selectedTerms.join(" ");
}

function deriveCompanyNameFromUploadedFileName(fileName: string | null): string | null {
  if (!fileName) {
    return null;
  }

  const normalizedName = fileName
    .replace(/\.[^.]+$/, "")
    .replace(/\[[^\]]+\]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  if (normalizedName === "") {
    return null;
  }

  const segments = normalizedName
    .split(/\s+-\s+/)
    .map((segment) => segment.trim())
    .filter((segment) => segment !== "");

  return segments[0] ?? null;
}

function deriveCompanyNameFromJobDescription(jobDescription: string): string | null {
  const compactText = jobDescription.replace(/\s+/g, " ").trim();
  if (compactText === "") {
    return null;
  }

  const aboutUsMatch = compactText.match(
    /about\s+us\s*:\s*([A-Z][A-Za-z0-9&.,'()\/+\-\s]{1,80}?)\s+is\b/i,
  );
  if (aboutUsMatch?.[1]) {
    return aboutUsMatch[1].trim().replace(/[.,;:]+$/, "");
  }

  const titlePrefixMatch = compactText.match(
    /^([A-Z][A-Za-z0-9&.'()\/+\-]+(?:\s+[A-Z][A-Za-z0-9&.'()\/+\-]+){0,5})\s+-/,
  );
  if (titlePrefixMatch?.[1]) {
    return titlePrefixMatch[1].trim();
  }

  return null;
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
  const uploadedJobDescriptionInputRef = useRef<HTMLInputElement | null>(null);
  const [jobDescription, setJobDescription] = useState(DEFAULT_JOB_DESCRIPTION);
  const [retrievalFocusTerms, setRetrievalFocusTerms] = useState(() =>
    deriveRetrievalFocusTerms(DEFAULT_JOB_DESCRIPTION),
  );
  const [isFocusTermsAuto, setIsFocusTermsAuto] = useState(true);
  const [searchResultLimit, setSearchResultLimit] = useState("5");
  const [retrievalLimit, setRetrievalLimit] = useState("25");
  const [shortlistLimit, setShortlistLimit] = useState("3");
  const [isSearchLoading, setIsSearchLoading] = useState(false);
  const [isShortlistLoading, setIsShortlistLoading] = useState(false);
  const [isShortlistExportLoading, setIsShortlistExportLoading] = useState(false);
  const [isShortlistShareLoading, setIsShortlistShareLoading] = useState(false);
  const [shortlistExportMessage, setShortlistExportMessage] = useState<
    string | null
  >(null);
  const [shortlistExportErrorMessage, setShortlistExportErrorMessage] = useState<
    string | null
  >(null);
  const [shortlistShareUrl, setShortlistShareUrl] = useState<string | null>(null);
  const [shortlistShareMessage, setShortlistShareMessage] = useState<string | null>(
    null,
  );
  const [shortlistShareErrorMessage, setShortlistShareErrorMessage] = useState<
    string | null
  >(null);
  const [shortlistShareExpiryDays, setShortlistShareExpiryDays] = useState("14");
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
  const [matchRunId, setMatchRunId] = useState<string | null>(null);
  const [feedbackByCandidateId, setFeedbackByCandidateId] = useState<
    Record<string, CandidateMatchFeedbackState>
  >({});
  const [isSearchResultsExpanded, setIsSearchResultsExpanded] = useState(false);
  const [isSearchQueryDetailsExpanded, setIsSearchQueryDetailsExpanded] =
    useState(false);
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
  const [companyContactResults, setCompanyContactResults] = useState<
    CompanyContactDiscoveryResult[]
  >([]);
  const [companyInteractionResults, setCompanyInteractionResults] = useState<
    CompanyInteractionDiscoveryResult[]
  >([]);
  const [companyJobResults, setCompanyJobResults] = useState<
    CompanyJobDiscoveryResult[]
  >([]);
  const [companyOpportunityResults, setCompanyOpportunityResults] = useState<
    CompanyOpportunityDiscoveryResult[]
  >([]);
  const [companyContactsErrorMessage, setCompanyContactsErrorMessage] = useState<
    string | null
  >(null);
  const [companyInteractionsErrorMessage, setCompanyInteractionsErrorMessage] =
    useState<string | null>(null);
  const [companyJobsErrorMessage, setCompanyJobsErrorMessage] = useState<
    string | null
  >(null);
  const [companyOpportunitiesErrorMessage, setCompanyOpportunitiesErrorMessage] =
    useState<string | null>(null);
  const [submittedCompanyName, setSubmittedCompanyName] = useState<string | null>(
    null,
  );
  const [uploadedJobDescriptionFile, setUploadedJobDescriptionFile] =
    useState<File | null>(null);
  const [uploadedJobDescriptionResult, setUploadedJobDescriptionResult] =
    useState<UploadedJobDescriptionExtractResponse | null>(null);
  const [uploadedJobDescriptionErrorMessage, setUploadedJobDescriptionErrorMessage] =
    useState<string | null>(null);
  const [detectedTargetCompanyName, setDetectedTargetCompanyName] = useState<
    string | null
  >(null);
  const [savedBriefs, setSavedBriefs] = useState<CandidateSavedBriefSummary[]>([]);
  const [activeSavedBriefId, setActiveSavedBriefId] = useState<string | null>(null);
  const [savedBriefTitle, setSavedBriefTitle] = useState("");
  const [isSavedBriefLibraryLoading, setIsSavedBriefLibraryLoading] =
    useState(true);
  const [isSavedBriefLoading, setIsSavedBriefLoading] = useState(false);
  const [isSavedBriefSaving, setIsSavedBriefSaving] = useState(false);
  const [isSavedBriefDeleting, setIsSavedBriefDeleting] = useState(false);
  const [isSavedBriefDeleteConfirming, setIsSavedBriefDeleteConfirming] =
    useState(false);
  const [savedBriefMessage, setSavedBriefMessage] = useState<string | null>(null);
  const [savedBriefErrorMessage, setSavedBriefErrorMessage] = useState<
    string | null
  >(null);

  useEffect(() => {
    if (!isFocusTermsAuto) {
      return;
    }

    setRetrievalFocusTerms(deriveRetrievalFocusTerms(jobDescription));
  }, [isFocusTermsAuto, jobDescription]);

  useEffect(() => {
    const derivedCompanyName =
      deriveCompanyNameFromUploadedFileName(
        uploadedJobDescriptionResult?.file_name ?? null,
      ) ?? deriveCompanyNameFromJobDescription(jobDescription);

    setDetectedTargetCompanyName(derivedCompanyName);

    if (derivedCompanyName && companyNameQuery.trim() === "") {
      setCompanyNameQuery(derivedCompanyName);
    }
  }, [companyNameQuery, jobDescription, uploadedJobDescriptionResult]);

  useEffect(() => {
    void refreshSavedBriefs();
  }, []);

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

  const activeCompanyContextName = detectedTargetCompanyName;

  const activeSavedBrief = useMemo(
    () =>
      savedBriefs.find(
        (savedBrief) => savedBrief.saved_brief_id === activeSavedBriefId,
      ) ?? null,
    [activeSavedBriefId, savedBriefs],
  );

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

  const companyContactsCountLabel = useMemo(() => {
    if (submittedCompanyName && companyContactResults.length === 0) {
      return "0 contacts returned.";
    }

    if (companyContactResults.length === 0) {
      return "No contacts returned yet.";
    }

    if (companyContactResults.length === 1) {
      return "1 contact returned.";
    }

    return `${companyContactResults.length} contacts returned.`;
  }, [companyContactResults.length, submittedCompanyName]);

  const companyInteractionsCountLabel = useMemo(() => {
    if (submittedCompanyName && companyInteractionResults.length === 0) {
      return "0 interactions returned.";
    }

    if (companyInteractionResults.length === 0) {
      return "No interactions returned yet.";
    }

    if (companyInteractionResults.length === 1) {
      return "1 interaction returned.";
    }

    return `${companyInteractionResults.length} interactions returned.`;
  }, [companyInteractionResults.length, submittedCompanyName]);

  const companyOpportunitiesCountLabel = useMemo(() => {
    if (submittedCompanyName && companyOpportunityResults.length === 0) {
      return "0 opportunities returned.";
    }

    if (companyOpportunityResults.length === 0) {
      return "No opportunities returned yet.";
    }

    if (companyOpportunityResults.length === 1) {
      return "1 opportunity returned.";
    }

    return `${companyOpportunityResults.length} opportunities returned.`;
  }, [companyOpportunityResults.length, submittedCompanyName]);

  const primaryCompanyContact = useMemo(() => {
    if (companyContactResults.length === 0) {
      return null;
    }

    return (
      companyContactResults.find(
        (contact) => contact.is_hiring_manager || contact.role_is_current,
      ) ?? companyContactResults[0]
    );
  }, [companyContactResults]);

  const primaryCompanyInteraction = useMemo(() => {
    if (companyInteractionResults.length === 0) {
      return null;
    }

    return companyInteractionResults[0];
  }, [companyInteractionResults]);

  async function refreshSavedBriefs(): Promise<void> {
    setIsSavedBriefLibraryLoading(true);

    try {
      const response = await fetch("/api/v1/candidates/saved-briefs?limit=50", {
        method: "GET",
        headers: {
          Accept: "application/json",
        },
        cache: "no-store",
      });
      const payload = await readJsonResponse(response);

      if (!response.ok) {
        setSavedBriefs([]);
        setSavedBriefErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Saved role briefs could not be loaded (${response.status}).`,
        );
        return;
      }

      const savedBriefList = payload as CandidateSavedBriefListResponse;
      setSavedBriefs(savedBriefList.saved_briefs);
    } catch (error) {
      setSavedBriefs([]);
      setSavedBriefErrorMessage(
        error instanceof Error
          ? error.message
          : "Saved role briefs could not be loaded.",
      );
    } finally {
      setIsSavedBriefLibraryLoading(false);
    }
  }

  async function loadSavedBrief(savedBriefId: string): Promise<void> {
    if (savedBriefId === "") {
      setActiveSavedBriefId(null);
      setSavedBriefTitle("");
      setIsSavedBriefDeleteConfirming(false);
      return;
    }

    setIsSavedBriefLoading(true);
    setSavedBriefMessage(null);
    setSavedBriefErrorMessage(null);
    setIsSavedBriefDeleteConfirming(false);

    try {
      const response = await fetch(
        `/api/v1/candidates/saved-briefs/${savedBriefId}`,
        {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
          cache: "no-store",
        },
      );
      const payload = await readJsonResponse(response);

      if (!response.ok) {
        setSavedBriefErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Saved role brief could not be opened (${response.status}).`,
        );
        return;
      }

      const savedBrief = payload as CandidateSavedBriefResponse;
      const hasSearchSnapshot = savedBrief.search_results.length > 0;
      const hasShortlistSnapshot = savedBrief.shortlisted_candidates.length > 0;

      setActiveSavedBriefId(savedBrief.saved_brief_id);
      setSavedBriefTitle(savedBrief.title);
      setJobDescription(savedBrief.job_description);
      setRetrievalFocusTerms(savedBrief.retrieval_focus_terms);
      setIsFocusTermsAuto(false);
      setSearchResultLimit(String(savedBrief.search_result_limit));
      setRetrievalLimit(String(savedBrief.retrieval_limit));
      setShortlistLimit(String(savedBrief.shortlist_limit));
      setMatchRunId(savedBrief.last_match_run_id);
      setRetrievedCandidateCount(savedBrief.retrieved_candidate_count);
      setSearchResults(savedBrief.search_results);
      setShortlistResults(savedBrief.shortlisted_candidates);
      setSubmittedSearchQuery(
        hasSearchSnapshot ? savedBrief.retrieval_focus_terms : null,
      );
      setSubmittedJobDescription(
        savedBrief.last_match_run_id || hasShortlistSnapshot
          ? savedBrief.job_description
          : null,
      );
      setIsSearchResultsExpanded(hasSearchSnapshot);
      setIsSearchQueryDetailsExpanded(false);
      setCompanyNameQuery(savedBrief.target_company_name ?? "");
      setFeedbackByCandidateId({});
      setSearchErrorMessage(null);
      setShortlistErrorMessage(null);
      setShortlistExportMessage(null);
      setShortlistExportErrorMessage(null);
      setShortlistShareUrl(null);
      setShortlistShareMessage(null);
      setShortlistShareErrorMessage(null);
      setPreviewCandidateId(null);
      setPreviewProfile(null);
      setUploadedJobDescriptionFile(null);
      setUploadedJobDescriptionResult(null);
      setUploadedJobDescriptionErrorMessage(null);
      if (uploadedJobDescriptionInputRef.current) {
        uploadedJobDescriptionInputRef.current.value = "";
      }
      setSavedBriefMessage(`Opened "${savedBrief.title}".`);
    } catch (error) {
      setSavedBriefErrorMessage(
        error instanceof Error
          ? error.message
          : "Saved role brief could not be opened.",
      );
    } finally {
      setIsSavedBriefLoading(false);
    }
  }

  async function saveCurrentBrief(forceCreate = false): Promise<void> {
    const trimmedTitle = savedBriefTitle.trim();
    const trimmedDescription = jobDescription.trim();
    const trimmedFocusTerms = retrievalFocusTerms.trim() || trimmedDescription;

    if (trimmedTitle === "") {
      setSavedBriefErrorMessage("Add a short title before saving this role.");
      return;
    }
    if (trimmedDescription === "") {
      setSavedBriefErrorMessage("Add a role brief before saving.");
      return;
    }

    const savedBriefId = forceCreate ? null : activeSavedBriefId;
    setIsSavedBriefSaving(true);
    setSavedBriefMessage(null);
    setSavedBriefErrorMessage(null);
    setIsSavedBriefDeleteConfirming(false);

    try {
      const response = await fetch(
        savedBriefId
          ? `/api/v1/candidates/saved-briefs/${savedBriefId}`
          : "/api/v1/candidates/saved-briefs",
        {
          method: savedBriefId ? "PUT" : "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            title: trimmedTitle,
            job_description: trimmedDescription,
            target_company_name: detectedTargetCompanyName,
            retrieval_focus_terms: trimmedFocusTerms,
            search_result_limit: Number(searchResultLimit),
            retrieval_limit: Number(retrievalLimit),
            shortlist_limit: Number(shortlistLimit),
            last_match_run_id: matchRunId,
            retrieved_candidate_count: retrievedCandidateCount,
            search_results: searchResults,
            shortlisted_candidates: shortlistResults,
          }),
        },
      );
      const payload = await readJsonResponse(response);

      if (!response.ok) {
        setSavedBriefErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Role brief could not be saved (${response.status}).`,
        );
        return;
      }

      const savedBrief = payload as CandidateSavedBriefResponse;
      setActiveSavedBriefId(savedBrief.saved_brief_id);
      setSavedBriefTitle(savedBrief.title);
      setSavedBriefMessage(
        savedBriefId
          ? `"${savedBrief.title}" was updated.`
          : `"${savedBrief.title}" was saved.`,
      );
      await refreshSavedBriefs();
    } catch (error) {
      setSavedBriefErrorMessage(
        error instanceof Error ? error.message : "Role brief could not be saved.",
      );
    } finally {
      setIsSavedBriefSaving(false);
    }
  }

  async function deleteActiveSavedBrief(): Promise<void> {
    if (!activeSavedBriefId) {
      return;
    }
    if (!isSavedBriefDeleteConfirming) {
      setIsSavedBriefDeleteConfirming(true);
      setSavedBriefMessage("Select delete again to confirm.");
      return;
    }

    setIsSavedBriefDeleting(true);
    setSavedBriefMessage(null);
    setSavedBriefErrorMessage(null);

    try {
      const response = await fetch(
        `/api/v1/candidates/saved-briefs/${activeSavedBriefId}`,
        {
          method: "DELETE",
          headers: {
            Accept: "application/json",
          },
        },
      );
      const payload = await readJsonResponse(response);

      if (!response.ok) {
        setSavedBriefErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Saved role brief could not be deleted (${response.status}).`,
        );
        return;
      }

      const deletedTitle = savedBriefTitle;
      setActiveSavedBriefId(null);
      setSavedBriefTitle("");
      setIsSavedBriefDeleteConfirming(false);
      setSavedBriefMessage(`"${deletedTitle}" was deleted.`);
      await refreshSavedBriefs();
    } catch (error) {
      setSavedBriefErrorMessage(
        error instanceof Error
          ? error.message
          : "Saved role brief could not be deleted.",
      );
    } finally {
      setIsSavedBriefDeleting(false);
    }
  }

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

      const payload = await readJsonResponse(response);

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
      setIsSearchResultsExpanded(true);
      setIsSearchQueryDetailsExpanded(false);
      if (detectedTargetCompanyName) {
        setCompanyNameQuery(detectedTargetCompanyName);
        void fetchCompanyContext(detectedTargetCompanyName);
      }
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

  async function loadUploadedJobDescription(): Promise<void> {
    if (!uploadedJobDescriptionFile) {
      setUploadedJobDescriptionErrorMessage(
        "Choose one PDF, DOCX, or DOC file before loading a job description.",
      );
      return;
    }

    setIsSearchLoading(true);
    setActiveRunMode("search");
    setUploadedJobDescriptionErrorMessage(null);
    const currentScrollY = window.scrollY;

    try {
      const contentBase64 = await encodeFileAsBase64(uploadedJobDescriptionFile);

      const response = await fetch(
        "/api/v1/candidates/extract-uploaded-job-description",
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            file_name: uploadedJobDescriptionFile.name,
            content_type: uploadedJobDescriptionFile.type || null,
            content_base64: contentBase64,
          }),
        },
      );

      const payload = await readJsonResponse(response);

      if (!response.ok) {
        setUploadedJobDescriptionResult(null);
        setUploadedJobDescriptionErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Job description upload failed with ${response.status}.`,
        );
        return;
      }

      const uploadResponse = payload as UploadedJobDescriptionExtractResponse;
      setJobDescription(uploadResponse.job_description_text);
      setIsFocusTermsAuto(true);
      setUploadedJobDescriptionResult(uploadResponse);
      if (!activeSavedBriefId && savedBriefTitle.trim() === "") {
        setSavedBriefTitle(
          (uploadResponse.file_name ?? "Uploaded role brief").replace(
            /\.[^.]+$/,
            "",
          ),
        );
      }
      setSearchResults([]);
      setShortlistResults([]);
      setMatchRunId(null);
      setFeedbackByCandidateId({});
      setSearchErrorMessage(null);
      setShortlistErrorMessage(null);
      setShortlistExportMessage(null);
      setShortlistExportErrorMessage(null);
      setShortlistShareUrl(null);
      setShortlistShareMessage(null);
      setShortlistShareErrorMessage(null);
      setSubmittedSearchQuery(null);
      setSubmittedJobDescription(null);
      setIsSearchResultsExpanded(false);
      setIsSearchQueryDetailsExpanded(false);
      window.requestAnimationFrame(() => {
        window.scrollTo({
          top: currentScrollY,
          behavior: "auto",
        });
      });
    } catch (error) {
      setUploadedJobDescriptionResult(null);
      setUploadedJobDescriptionErrorMessage(
        error instanceof Error
          ? error.message
          : "Job description upload failed unexpectedly.",
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
    setShortlistExportMessage(null);
    setShortlistExportErrorMessage(null);
    setShortlistShareUrl(null);
    setShortlistShareMessage(null);
    setShortlistShareErrorMessage(null);

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

      const payload = await readJsonResponse(response);

      if (!response.ok) {
        setShortlistResults([]);
        setMatchRunId(null);
        setFeedbackByCandidateId({});
        setSubmittedJobDescription(trimmedDescription);
        setShortlistErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            (typeof payload === "string" ? payload : undefined) ??
            `Shortlist request failed with ${response.status}.`,
        );
        return;
      }

      const shortlistResponse = payload as CandidateJobDescriptionMatchResponse;
      setShortlistResults(shortlistResponse.shortlisted_candidates);
      setMatchRunId(shortlistResponse.match_run_id);
      setFeedbackByCandidateId({});
      setRetrievedCandidateCount(shortlistResponse.retrieved_candidate_count);
      setSubmittedJobDescription(shortlistResponse.job_description);

      if (detectedTargetCompanyName) {
        setCompanyNameQuery(detectedTargetCompanyName);
        void fetchCompanyContext(detectedTargetCompanyName);
      }

      shortlistSectionRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    } catch (error) {
      setShortlistResults([]);
      setMatchRunId(null);
      setFeedbackByCandidateId({});
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

  async function exportShortlistPackage(): Promise<void> {
    const activeJobDescription =
      submittedJobDescription?.trim() || jobDescription.trim();

    if (
      !matchRunId ||
      activeJobDescription === "" ||
      shortlistResults.length === 0
    ) {
      setShortlistExportErrorMessage(
        "Run the recruiter shortlist before downloading an export package.",
      );
      return;
    }

    setIsShortlistExportLoading(true);
    setShortlistExportMessage(null);
    setShortlistExportErrorMessage(null);

    try {
      const response = await fetch("/api/v1/candidates/export-shortlist", {
        method: "POST",
        headers: {
          Accept: "application/zip, application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          match_run_id: matchRunId,
          role_title: uploadedJobDescriptionResult?.file_name ?? null,
          job_description: activeJobDescription,
          shortlisted_candidates: shortlistResults,
        }),
      });

      if (!response.ok) {
        const payload = await readJsonResponse(response);
        setShortlistExportErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Shortlist export failed with ${response.status}.`,
        );
        return;
      }

      const packageBlob = await response.blob();
      const packageUrl = window.URL.createObjectURL(packageBlob);
      const downloadLink = document.createElement("a");
      downloadLink.href = packageUrl;
      downloadLink.download = getAttachmentFileName(
        response.headers.get("Content-Disposition"),
        "recruiter-shortlist-package.zip",
      );
      document.body.appendChild(downloadLink);
      downloadLink.click();
      downloadLink.remove();
      window.URL.revokeObjectURL(packageUrl);

      const exportedCvCount =
        response.headers.get("X-Exported-CV-Count") ?? "0";
      const unavailableCvCount =
        response.headers.get("X-Unavailable-CV-Count") ?? "0";
      setShortlistExportMessage(
        unavailableCvCount === "0"
          ? `Export downloaded with the Word shortlist and ${exportedCvCount} CVs.`
          : `Export downloaded with ${exportedCvCount} CVs; ${unavailableCvCount} unavailable CVs are recorded in the manifest.`,
      );
    } catch (error) {
      setShortlistExportErrorMessage(
        error instanceof Error
          ? error.message
          : "Shortlist export failed unexpectedly.",
      );
    } finally {
      setIsShortlistExportLoading(false);
    }
  }

  async function createShortlistShare(): Promise<void> {
    const activeJobDescription =
      submittedJobDescription?.trim() || jobDescription.trim();

    if (
      !matchRunId ||
      activeJobDescription === "" ||
      shortlistResults.length === 0
    ) {
      setShortlistShareErrorMessage(
        "Run the recruiter shortlist before creating a secure link.",
      );
      return;
    }

    setIsShortlistShareLoading(true);
    setShortlistShareMessage(null);
    setShortlistShareErrorMessage(null);

    try {
      const response = await fetch("/api/v1/candidates/shortlist-shares", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          match_run_id: matchRunId,
          role_title: uploadedJobDescriptionResult?.file_name ?? null,
          job_description: activeJobDescription,
          shortlisted_candidates: shortlistResults,
          expires_in_days: Number(shortlistShareExpiryDays),
        }),
      });
      const payload = await readJsonResponse(response);

      if (!response.ok) {
        setShortlistShareErrorMessage(
          (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Secure link creation failed with ${response.status}.`,
        );
        return;
      }

      const share = payload as CandidateShortlistShareResponse;
      const shareUrl = `${window.location.origin}/shortlists/${share.share_id}`;
      setShortlistShareUrl(shareUrl);
      setShortlistShareMessage(
        `Secure link created. It expires ${formatTimestamp(share.expires_at)}.`,
      );

      try {
        await navigator.clipboard.writeText(shareUrl);
        setShortlistShareMessage(
          `Secure link copied. It expires ${formatTimestamp(share.expires_at)}.`,
        );
      } catch {
        // The visible link remains available when browser clipboard access is blocked.
      }
    } catch (error) {
      setShortlistShareErrorMessage(
        error instanceof Error
          ? error.message
          : "Secure link creation failed unexpectedly.",
      );
    } finally {
      setIsShortlistShareLoading(false);
    }
  }

  async function copyShortlistShareUrl(): Promise<void> {
    if (!shortlistShareUrl) {
      return;
    }

    try {
      await navigator.clipboard.writeText(shortlistShareUrl);
      setShortlistShareMessage("Secure shortlist link copied.");
      setShortlistShareErrorMessage(null);
    } catch {
      setShortlistShareErrorMessage(
        "Clipboard access was blocked. Select and copy the link manually.",
      );
    }
  }

  function updateCandidateFeedback(
    candidateId: string,
    update: Partial<CandidateMatchFeedbackState>,
  ): void {
    setFeedbackByCandidateId((current) => {
      const previous = current[candidateId] ?? {
        value: null,
        reason: "",
        status: "idle",
        message: null,
      };

      return {
        ...current,
        [candidateId]: {
          ...previous,
          ...update,
        },
      };
    });
  }

  async function submitCandidateFeedback(
    result: CandidateJobDescriptionShortlistItem,
    shortlistRank: number,
  ): Promise<void> {
    const feedback = feedbackByCandidateId[result.candidate_id];
    const activeJobDescription =
      submittedJobDescription?.trim() || jobDescription.trim();

    if (!matchRunId || activeJobDescription === "") {
      updateCandidateFeedback(result.candidate_id, {
        status: "error",
        message: "Run the shortlist again before saving feedback.",
      });
      return;
    }

    if (!feedback?.value) {
      updateCandidateFeedback(result.candidate_id, {
        status: "error",
        message: "Choose Good match or Not suitable first.",
      });
      return;
    }

    updateCandidateFeedback(result.candidate_id, {
      status: "saving",
      message: null,
    });

    try {
      const response = await fetch("/api/v1/candidates/match-feedback", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          match_run_id: matchRunId,
          candidate_id: result.candidate_id,
          document_id: result.document_id,
          feedback_value: feedback.value,
          feedback_reason: feedback.reason.trim() || null,
          job_description: activeJobDescription,
          shortlist_rank: shortlistRank,
          fit_score: result.fit_score,
          retrieval_score: result.retrieval_score,
          graph_context_score: result.graph_context_score,
          ranking_input_score: result.ranking_input_score,
          source_category: result.source_category,
        }),
      });
      const payload = await readJsonResponse(response);

      if (!response.ok) {
        updateCandidateFeedback(result.candidate_id, {
          status: "error",
          message:
            (isApiErrorResponse(payload) ? payload.error?.message : undefined) ??
            `Feedback could not be saved (${response.status}).`,
        });
        return;
      }

      const savedFeedback = payload as CandidateMatchFeedbackResponse;
      updateCandidateFeedback(result.candidate_id, {
        value: savedFeedback.feedback_value,
        reason: savedFeedback.feedback_reason ?? "",
        status: "saved",
        message: "Feedback saved.",
      });
    } catch (error) {
      updateCandidateFeedback(result.candidate_id, {
        status: "error",
        message:
          error instanceof Error
            ? error.message
            : "Feedback could not be saved.",
      });
    }
  }

  async function fetchCompanyContext(companyName: string): Promise<void> {
    const trimmedCompanyName = companyName.trim();
    if (trimmedCompanyName === "") {
      return;
    }

    setCompanyDiscoveryLoading(true);
    setCompanyDiscoveryErrorMessage(null);
    setCompanyContactsErrorMessage(null);
    setCompanyInteractionsErrorMessage(null);
    setCompanyJobsErrorMessage(null);
    setCompanyOpportunitiesErrorMessage(null);

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

      const payload = await readJsonResponse(response);

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

      const contactsResponse = await fetch(
        `/api/v1/candidates/discover-contacts-by-company?${searchParams.toString()}`,
        {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
        },
      );

      const contactsPayload = await readJsonResponse(contactsResponse);

      if (!contactsResponse.ok) {
        setCompanyContactResults([]);
        setCompanyContactsErrorMessage(
          (isApiErrorResponse(contactsPayload)
            ? contactsPayload.error?.message
            : undefined) ??
            `Company contacts request failed with ${contactsResponse.status}.`,
        );
        return;
      }

      const companyContactsResponse =
        contactsPayload as CompanyContactDiscoveryResponse;
      setCompanyContactResults(companyContactsResponse.results);

      const interactionsResponse = await fetch(
        `/api/v1/candidates/discover-interactions-by-company?${searchParams.toString()}`,
        {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
        },
      );

      const interactionsPayload = await readJsonResponse(interactionsResponse);

      if (!interactionsResponse.ok) {
        setCompanyInteractionResults([]);
        setCompanyInteractionsErrorMessage(
          (isApiErrorResponse(interactionsPayload)
            ? interactionsPayload.error?.message
            : undefined) ??
            `Company interactions request failed with ${interactionsResponse.status}.`,
        );
        return;
      }

      const companyInteractionsResponse =
        interactionsPayload as CompanyInteractionDiscoveryResponse;
      setCompanyInteractionResults(companyInteractionsResponse.results);

      const jobsResponse = await fetch(
        `/api/v1/candidates/discover-jobs-by-company?${searchParams.toString()}`,
        {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
        },
      );

      const jobsPayload = await readJsonResponse(jobsResponse);

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

      const opportunitiesResponse = await fetch(
        `/api/v1/candidates/discover-opportunities-by-company?${searchParams.toString()}`,
        {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
        },
      );

      const opportunitiesPayload = await readJsonResponse(opportunitiesResponse);

      if (!opportunitiesResponse.ok) {
        setCompanyOpportunityResults([]);
        setCompanyOpportunitiesErrorMessage(
          (isApiErrorResponse(opportunitiesPayload)
            ? opportunitiesPayload.error?.message
            : undefined) ??
            `Company opportunities request failed with ${opportunitiesResponse.status}.`,
        );
        return;
      }

      const companyOpportunitiesResponse =
        opportunitiesPayload as CompanyOpportunityDiscoveryResponse;
      setCompanyOpportunityResults(companyOpportunitiesResponse.results);
    } catch (error) {
      setCompanyDiscoveryResults([]);
      setCompanyContactResults([]);
      setCompanyInteractionResults([]);
      setCompanyJobResults([]);
      setCompanyOpportunityResults([]);
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

  async function runCompanyDiscovery(): Promise<void> {
    const trimmedCompanyName = companyNameQuery.trim();
    if (trimmedCompanyName === "") {
      setCompanyDiscoveryErrorMessage("Enter a company name before searching.");
      setCompanyDiscoveryResults([]);
      return;
    }

    await fetchCompanyContext(trimmedCompanyName);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runSearch();
  }

  function applyAutoRetrievalFocusTerms(): void {
    setIsFocusTermsAuto(true);
    setRetrievalFocusTerms(deriveRetrievalFocusTerms(jobDescription));
  }

  function applyFullBriefRetrievalFocusTerms(): void {
    setIsFocusTermsAuto(false);
    setRetrievalFocusTerms(jobDescription.trim());
  }

  function resetToExampleBrief(): void {
    setActiveSavedBriefId(null);
    setSavedBriefTitle("Example data engineer role");
    setSavedBriefMessage(null);
    setSavedBriefErrorMessage(null);
    setIsSavedBriefDeleteConfirming(false);
    setJobDescription(DEFAULT_JOB_DESCRIPTION);
    setIsFocusTermsAuto(true);
    setRetrievalFocusTerms(deriveRetrievalFocusTerms(DEFAULT_JOB_DESCRIPTION));
  }

  function clearWorkspace(): void {
    setActiveSavedBriefId(null);
    setSavedBriefTitle("");
    setSavedBriefMessage(null);
    setSavedBriefErrorMessage(null);
    setIsSavedBriefDeleteConfirming(false);
    setJobDescription("");
    setRetrievalFocusTerms("");
    setIsFocusTermsAuto(true);
    setSearchResults([]);
    setShortlistResults([]);
    setMatchRunId(null);
    setFeedbackByCandidateId({});
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
    setCompanyContactResults([]);
    setCompanyContactsErrorMessage(null);
    setCompanyInteractionResults([]);
    setCompanyInteractionsErrorMessage(null);
    setCompanyJobResults([]);
    setCompanyJobsErrorMessage(null);
    setCompanyOpportunityResults([]);
    setCompanyOpportunitiesErrorMessage(null);
    setSubmittedCompanyName(null);
    setIsSearchResultsExpanded(false);
    setIsSearchQueryDetailsExpanded(false);
    setUploadedJobDescriptionFile(null);
    setUploadedJobDescriptionResult(null);
    setUploadedJobDescriptionErrorMessage(null);
    if (uploadedJobDescriptionInputRef.current) {
      uploadedJobDescriptionInputRef.current.value = "";
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
    <div className="grid gap-10">
      <section className="workspace-section grid gap-6 p-6 sm:p-8">
        <div className="flex flex-col gap-3 border-b border-zinc-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-3xl">
            <h2 className="text-3xl font-semibold text-zinc-950">
              Match operating modes
            </h2>
            <p className="mt-2 text-base leading-7 text-zinc-700">
              Pick one starting point, inspect the evidence, and then run the
              final shortlist. The point of this page is to keep retrieval
              visible before any ranking model makes the final call.
            </p>
          </div>
          <div className="text-sm text-zinc-600">
            Retrieval first. Reasoning second.
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <div className="workspace-card-soft p-5">
            <p className="text-xs font-semibold uppercase text-zinc-500">
              Mode 1
            </p>
            <p className="mt-2 text-lg font-semibold text-zinc-950">
              Role brief to shortlist
            </p>
            <p className="mt-2 text-sm leading-6 text-zinc-700">
              Best for a live vacancy where you want a recruiter-style shortlist
              with fit summaries, strengths, and gaps.
            </p>
            <a
              href="#role-brief-workflow"
              className="mt-4 inline-flex text-sm font-semibold text-emerald-700 underline decoration-emerald-300 underline-offset-4"
            >
              Go to role-brief workflow
            </a>
          </div>

          <div className="workspace-card-soft p-5">
            <p className="text-xs font-semibold uppercase text-zinc-500">
              Mode 2
            </p>
            <p className="mt-2 text-lg font-semibold text-zinc-950">
              Uploaded CV to similar profiles
            </p>
            <p className="mt-2 text-sm leading-6 text-zinc-700">
              Use one CV as transient search input when you want to find
              similar people already stored in the corpus without persisting
              that uploaded file.
            </p>
          </div>

          <div className="workspace-card-soft p-5">
            <p className="text-xs font-semibold uppercase text-zinc-500">
              Mode 3
            </p>
            <p className="mt-2 text-lg font-semibold text-zinc-950">
              Company intelligence
            </p>
            <p className="mt-2 text-sm leading-6 text-zinc-700">
              Use this when you want to know who works there, who knows them,
              and what jobs or opportunities are already linked to that firm.
            </p>
            <a
              href="#company-intelligence"
              className="mt-4 inline-flex text-sm font-semibold text-emerald-700 underline decoration-emerald-300 underline-offset-4"
            >
              Go to company lookup
            </a>
          </div>
        </div>

        <div className="workspace-highlight p-4 text-sm leading-6 text-emerald-950">
          <p className="font-semibold">Recommended path</p>
          <ol className="mt-2 grid gap-1 pl-5 list-decimal">
            <li>Paste the full role brief.</li>
            <li>
              Click <span className="font-semibold">1. Search corpus</span> to
              inspect the candidate pool.
            </li>
            <li>Open one or two candidate previews to sanity-check the retrieval.</li>
            <li>
              Click <span className="font-semibold">2. Shortlist top {shortlistLimit}</span>{" "}
              when the pool looks sensible.
            </li>
          </ol>
        </div>
      </section>

      <section
        id="role-brief-workflow"
        className="workspace-section grid gap-6 p-6 sm:p-8"
      >
        <div className="flex flex-col gap-3 border-b border-zinc-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-3xl font-semibold text-zinc-950">
              Role brief workflow
            </h2>
            <p className="mt-2 max-w-3xl text-base leading-7 text-zinc-700">
              Use this route when you are working a live vacancy and want to
              move from an unstructured brief to an explainable shortlist.
            </p>
          </div>
          <div className="text-sm text-zinc-600">
            Full brief in, ranked shortlist out.
          </div>
        </div>

        <div className="workspace-card-soft grid gap-4 p-4 sm:p-5">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
                Saved role library
              </p>
              <h3 className="mt-1 text-xl font-semibold text-zinc-950">
                Reopen a role without rebuilding the search
              </h3>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-600">
                A saved role keeps the full brief, retrieval settings, target
                company, and latest search and shortlist evidence. Reopen it,
                then use the live search buttons below whenever you want fresh
                results from the current database.
              </p>
            </div>
            <p className="text-sm text-zinc-600">
              {isSavedBriefLibraryLoading
                ? "Loading saved roles..."
                : `${savedBriefs.length} saved ${savedBriefs.length === 1 ? "role" : "roles"}`}
            </p>
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div className="grid gap-2">
              <label
                className="text-sm font-semibold text-zinc-800"
                htmlFor="saved-role-brief"
              >
                Open a saved role
              </label>
              <select
                id="saved-role-brief"
                value={activeSavedBriefId ?? ""}
                disabled={isSavedBriefLibraryLoading || isSavedBriefLoading}
                onChange={(event) => {
                  void loadSavedBrief(event.target.value);
                }}
                className="h-11 w-full rounded-md border border-zinc-300 bg-white px-3 text-sm text-zinc-950 outline-none transition focus:border-emerald-600 disabled:bg-zinc-100"
              >
                <option value="">Choose a saved role</option>
                {savedBriefs.map((savedBrief) => (
                  <option
                    key={savedBrief.saved_brief_id}
                    value={savedBrief.saved_brief_id}
                  >
                    {savedBrief.title}
                    {savedBrief.target_company_name
                      ? ` - ${savedBrief.target_company_name}`
                      : ""}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid gap-2">
              <label
                className="text-sm font-semibold text-zinc-800"
                htmlFor="saved-role-title"
              >
                Saved role title
              </label>
              <input
                id="saved-role-title"
                value={savedBriefTitle}
                onChange={(event) => setSavedBriefTitle(event.target.value)}
                className="h-11 w-full rounded-md border border-zinc-300 bg-white px-3 text-sm text-zinc-950 outline-none transition focus:border-emerald-600"
                placeholder="e.g. Starr Financial Systems Analyst"
                maxLength={200}
              />
            </div>
          </div>

          {activeSavedBrief ? (
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs leading-5 text-zinc-600">
              <span>Updated {formatTimestamp(activeSavedBrief.updated_at)}</span>
              <span>{activeSavedBrief.search_result_count} saved search results</span>
              <span>{activeSavedBrief.shortlist_count} saved shortlist results</span>
              <span>
                {activeSavedBrief.retrieved_candidate_count} candidates considered
              </span>
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={isSavedBriefSaving || isSavedBriefLoading}
              onClick={() => {
                void saveCurrentBrief(false);
              }}
              className="inline-flex h-10 items-center justify-center rounded-md bg-zinc-950 px-4 text-sm font-semibold text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400"
            >
              {isSavedBriefSaving
                ? "Saving..."
                : activeSavedBriefId
                  ? "Update saved role"
                  : "Save role"}
            </button>
            {activeSavedBriefId ? (
              <button
                type="button"
                disabled={isSavedBriefSaving || isSavedBriefLoading}
                onClick={() => {
                  void saveCurrentBrief(true);
                }}
                className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-900 transition hover:border-zinc-500 disabled:cursor-not-allowed disabled:bg-zinc-100"
              >
                Save as copy
              </button>
            ) : null}
            {activeSavedBriefId ? (
              <button
                type="button"
                disabled={isSavedBriefDeleting || isSavedBriefLoading}
                onClick={() => {
                  void deleteActiveSavedBrief();
                }}
                className="inline-flex h-10 items-center justify-center rounded-md border border-rose-300 bg-white px-4 text-sm font-semibold text-rose-700 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:bg-zinc-100"
              >
                {isSavedBriefDeleting
                  ? "Deleting..."
                  : isSavedBriefDeleteConfirming
                    ? "Confirm delete"
                    : "Delete"}
              </button>
            ) : null}
          </div>

          {savedBriefMessage ? (
            <p className="text-sm leading-6 text-emerald-800">{savedBriefMessage}</p>
          ) : null}
          {savedBriefErrorMessage ? (
            <p className="text-sm leading-6 text-rose-700">
              {savedBriefErrorMessage}
            </p>
          ) : null}
        </div>

        <form className="grid gap-6" onSubmit={handleSubmit}>
          <div className="workspace-card-soft grid gap-4 p-4 lg:grid-cols-3">
            <div>
              <p className="text-xs font-semibold uppercase text-zinc-500">
                Step 1
              </p>
              <p className="mt-2 text-base font-semibold text-zinc-950">
                Keep the full brief
              </p>
              <p className="mt-2 text-sm leading-6 text-zinc-700">
                The full brief stays here for reranking, even when the first
                search pass uses shorter focus terms.
              </p>
            </div>

            <div>
              <p className="text-xs font-semibold uppercase text-zinc-500">
                Step 2
              </p>
              <p className="mt-2 text-base font-semibold text-zinc-950">
                Inspect retrieval before ranking
              </p>
              <p className="mt-2 text-sm leading-6 text-zinc-700">
                Corpus search shows what the engine actually found before any
                LLM call is made.
              </p>
            </div>

            <div>
              <p className="text-xs font-semibold uppercase text-zinc-500">
                Step 3
              </p>
              <p className="mt-2 text-base font-semibold text-zinc-950">
                Use shortlist as the final pass
              </p>
              <p className="mt-2 text-sm leading-6 text-zinc-700">
                Shortlisting is slower because it adds reasoning and fit
                summaries on top of grounded retrieval.
              </p>
            </div>
          </div>

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
              className="workspace-textarea min-h-72 px-4 py-3 text-base leading-7 text-zinc-950"
              placeholder="Paste the role brief here."
            />
            <p className="text-sm leading-6 text-zinc-600">
              Keep the full brief here. Search retrieves the candidate pool and
              shortlist uses the same full text for reranking.
            </p>
          </div>

          <div className="workspace-card grid gap-3 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <label
                  className="text-sm font-semibold uppercase text-zinc-500"
                  htmlFor="uploaded-job-description"
                >
                  Alternative route: upload one job description
                </label>
                <p className="mt-2 text-sm leading-6 text-zinc-600">
                  Upload one PDF, DOCX, or DOC job spec and load its extracted
                  text into the role brief above. This step does not persist the
                  uploaded file.
                </p>
              </div>

              <button
                type="button"
                disabled={
                  isSearchLoading ||
                  isShortlistLoading ||
                  !uploadedJobDescriptionFile
                }
                onClick={() => {
                  void loadUploadedJobDescription();
                }}
                className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-5 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500 disabled:cursor-not-allowed disabled:border-zinc-300 disabled:bg-zinc-200"
              >
                {isSearchLoading
                  ? "Loading job description..."
                  : "Use uploaded job description"}
              </button>
            </div>

            <input
              id="uploaded-job-description"
              ref={uploadedJobDescriptionInputRef}
              type="file"
              accept=".pdf,.docx,.doc,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(event) => {
                const selectedFile = event.target.files?.[0] ?? null;
                setUploadedJobDescriptionFile(selectedFile);
                setUploadedJobDescriptionResult(null);
                setUploadedJobDescriptionErrorMessage(null);
              }}
              className="block w-full text-sm text-zinc-900 file:mr-4 file:rounded-md file:border file:border-zinc-300 file:bg-white file:px-4 file:py-2 file:text-sm file:font-semibold file:text-zinc-950 hover:file:border-zinc-500"
            />

            <p className="text-sm leading-6 text-zinc-600">
              {uploadedJobDescriptionFile
                ? `Selected file: ${uploadedJobDescriptionFile.name}`
                : "Supported formats: PDF, DOCX, DOC."}
            </p>
            {uploadedJobDescriptionErrorMessage ? (
              <p className="text-sm leading-6 text-rose-700">
                {uploadedJobDescriptionErrorMessage}
              </p>
            ) : null}
            {uploadedJobDescriptionResult ? (
              <div className="grid gap-1 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm leading-6 text-emerald-950">
                <p>
                  Loaded into role brief from{" "}
                  <span className="font-semibold">
                    {uploadedJobDescriptionResult.file_name ?? "uploaded file"}
                  </span>
                  .
                </p>
                <p>
                  Extractor:{" "}
                  <span className="font-medium">
                    {uploadedJobDescriptionResult.extractor ?? "Unknown"}
                  </span>
                  {uploadedJobDescriptionResult.page_count
                    ? `, pages: ${uploadedJobDescriptionResult.page_count}`
                    : ""}
                  {`, cleaned characters: ${uploadedJobDescriptionResult.character_count}`}
                </p>
                <p>
                  Preview:{" "}
                  <span className="font-medium">
                    {uploadedJobDescriptionResult.cleaned_text_preview}
                  </span>
                </p>
              </div>
            ) : null}
            {detectedTargetCompanyName ? (
              <p className="text-sm leading-6 text-zinc-600">
                Detected target company:{" "}
                <span className="font-medium text-zinc-900">
                  {detectedTargetCompanyName}
                </span>
              </p>
            ) : null}
          </div>

          <div className="grid gap-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="grid gap-1">
                <label
                  className="text-sm font-semibold uppercase text-zinc-500"
                  htmlFor="retrieval-focus-terms"
                >
                  Retrieval focus terms
                </label>
                <p className="text-sm leading-6 text-zinc-600">
                  Search starts from this query first, then broadens if the
                  first pass is too narrow.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <label
                  className="text-sm font-medium text-zinc-700"
                  htmlFor="retrieval-focus-mode"
                >
                  Query mode
                </label>
                <select
                  id="retrieval-focus-mode"
                  value={isFocusTermsAuto ? "auto" : "full"}
                  onChange={(event) => {
                    if (event.target.value === "full") {
                      applyFullBriefRetrievalFocusTerms();
                      return;
                    }

                    applyAutoRetrievalFocusTerms();
                  }}
                  className="h-9 rounded-md border border-zinc-300 bg-white px-3 text-sm text-zinc-950 outline-none transition focus:border-zinc-500"
                >
                  <option value="auto">Auto terms from brief</option>
                  <option value="full">Use full brief text</option>
                </select>
                {isFocusTermsAuto ? (
                  <button
                    type="button"
                    onClick={applyAutoRetrievalFocusTerms}
                    className="inline-flex h-9 items-center justify-center rounded-md border border-zinc-300 bg-white px-3 text-sm font-semibold text-zinc-900 transition hover:border-zinc-500"
                  >
                    Refresh
                  </button>
                ) : null}
              </div>
            </div>

            <textarea
              id="retrieval-focus-terms"
              value={retrievalFocusTerms}
              onChange={(event) => {
                setIsFocusTermsAuto(false);
                setRetrievalFocusTerms(event.target.value);
              }}
              className="workspace-textarea min-h-24 px-4 py-3 text-base leading-7 text-zinc-950"
              placeholder="python sql aws data engineer etl"
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-[1fr_auto] xl:items-end">
            <div className="grid gap-4 md:grid-cols-3">
              <div className="grid gap-3">
                <label
                  className="text-sm font-semibold uppercase text-zinc-500"
                  htmlFor="search-result-limit"
                >
                  Step 1 search
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
                  Step 2 shortlist pool
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
                  Step 3 final shortlist
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

            <div className="grid gap-2 rounded-md border border-zinc-200 bg-zinc-50 p-4 text-sm leading-6 text-zinc-700 xl:max-w-xl">
              <p>
                Run <span className="font-semibold text-zinc-950">1. Search corpus</span>{" "}
                first to pull the initial candidate pool and sanity-check the
                evidence.
              </p>
              <p>
                Then run{" "}
                <span className="font-semibold text-zinc-950">
                  2. Shortlist top {shortlistLimit}
                </span>{" "}
                to send that retrieved pool to the reasoning model for the
                final ranked shortlist.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                type="submit"
                disabled={isSearchLoading || isShortlistLoading}
                className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-5 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500 disabled:cursor-not-allowed disabled:border-zinc-300 disabled:bg-zinc-200"
              >
                {isSearchLoading ? "Searching..." : "1. Search corpus"}
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
                  : `2. Shortlist top ${shortlistLimit}`}
              </button>
            </div>
          </div>
        </form>
      </section>

      {loadingMessage ? (
        <section className="rounded-md border border-sky-200 bg-sky-50 p-4 text-sm leading-6 text-sky-900 shadow-sm">
          {loadingMessage}
        </section>
      ) : null}

      <section
        id="candidate-preview"
        className="workspace-section order-50 grid gap-5 bg-[#fcfcf8] p-6 sm:p-8"
      >
        <div className="flex flex-col gap-3 border-b border-zinc-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-3xl font-semibold text-zinc-950">
              Selected candidate profile
            </h2>
            <p className="mt-2 max-w-3xl text-base leading-7 text-zinc-700">
              Inspect the selected candidate in-page before opening raw JSON or
              the original CV.
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
          <div className="workspace-empty bg-white p-6 text-sm leading-7 text-zinc-600">
            Use any result card to preview the candidate profile, skills, and
            contact details here.
          </div>
        ) : null}

        {previewProfile ? (
          <article className="workspace-card grid gap-6 p-5 sm:p-6">
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
              <div className="workspace-card-soft p-4">
                <dt className="text-xs font-semibold uppercase text-zinc-500">
                  Candidate status
                </dt>
                <dd className="mt-1 text-sm leading-6 text-zinc-900">
                  {previewProfile.candidate.candidate_status ?? "Unknown"}
                </dd>
              </div>

              <div className="workspace-card-soft p-4">
                <dt className="text-xs font-semibold uppercase text-zinc-500">
                  Availability
                </dt>
                <dd className="mt-1 text-sm leading-6 text-zinc-900">
                  {previewProfile.candidate.availability_status ?? "Unknown"}
                </dd>
              </div>

              <div className="workspace-card-soft p-4">
                <dt className="text-xs font-semibold uppercase text-zinc-500">
                  Resume updated
                </dt>
                <dd className="mt-1 text-sm leading-6 text-zinc-900">
                  {formatTimestamp(previewProfile.candidate.resume_updated_at)}
                </dd>
              </div>

              <div className="workspace-card-soft p-4">
                <dt className="text-xs font-semibold uppercase text-zinc-500">
                  Last contacted
                </dt>
                <dd className="mt-1 text-sm leading-6 text-zinc-900">
                  {formatTimestamp(previewProfile.candidate.last_contacted_at)}
                </dd>
              </div>

              <div className="workspace-card-soft p-4">
                <dt className="text-xs font-semibold uppercase text-zinc-500">
                  Email
                </dt>
                <dd className="mt-1 break-words text-sm leading-6 text-zinc-900">
                  {previewProfile.candidate.primary_email ?? "Not available"}
                </dd>
              </div>

              <div className="workspace-card-soft p-4">
                <dt className="text-xs font-semibold uppercase text-zinc-500">
                  Phone
                </dt>
                <dd className="mt-1 break-words text-sm leading-6 text-zinc-900">
                  {previewProfile.candidate.primary_phone ?? "Not available"}
                </dd>
              </div>

              <div className="workspace-card-soft p-4">
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

              <div className="workspace-card-soft p-4">
                <dt className="text-xs font-semibold uppercase text-zinc-500">
                  Location
                </dt>
                <dd className="mt-1 text-sm leading-6 text-zinc-900">
                  {previewProfile.candidate.location ?? "Unknown"}
                </dd>
              </div>
            </dl>

            <div className="flex flex-wrap gap-3">
              {previewProfile.candidate.primary_email ? (
                <a
                  href={`mailto:${previewProfile.candidate.primary_email}`}
                  className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                >
                  Email candidate
                </a>
              ) : null}
              {previewProfile.candidate.primary_phone ? (
                <a
                  href={`tel:${previewProfile.candidate.primary_phone}`}
                  className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                >
                  Call candidate
                </a>
              ) : null}
              {previewProfile.candidate.linkedin_url ? (
                <a
                  href={previewProfile.candidate.linkedin_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex h-10 items-center justify-center rounded-md border border-sky-200 bg-sky-50 px-4 text-sm font-semibold text-sky-900 transition hover:border-sky-400"
                >
                  Open LinkedIn
                </a>
              ) : null}
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <div className="workspace-card-soft bg-white p-4">
                <p className="text-xs font-semibold uppercase text-zinc-500">
                  Recent employment
                </p>
                {previewProfile.recent_employment.length > 0 ? (
                  <ol className="mt-3 grid gap-3">
                    {previewProfile.recent_employment.map((role, index) => (
                      <li
                        key={
                          role.employment_role_id ??
                          `${previewProfile.candidate.candidate_id}-employment-${index}`
                        }
                        className="rounded-md border border-zinc-200 bg-white p-3 text-sm leading-6 text-zinc-800"
                      >
                        <p className="font-semibold text-zinc-950">
                          {role.role_title ?? "Role title unavailable"}
                        </p>
                        <p>{role.company_name ?? "Company unavailable"}</p>
                        <p className="text-xs text-zinc-500">
                          {formatEmploymentPeriod(role)}
                        </p>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="mt-3 text-sm leading-6 text-zinc-600">
                    No canonical employment history is linked yet. The current
                    title and company above remain the available role evidence.
                  </p>
                )}
              </div>

              <div className="workspace-card-soft bg-[#f8faf8] p-4">
                <p className="text-xs font-semibold uppercase text-zinc-500">
                  Skills evidence
                </p>
                {previewSkillNames.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {previewSkillNames.map((skillName) => (
                      <span
                        key={skillName}
                        className="rounded-md border border-zinc-200 bg-white px-3 py-1 text-sm text-zinc-900"
                      >
                        {skillName}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="mt-3 text-sm leading-6 text-zinc-600">
                    No structured skills are linked.
                  </p>
                )}

                {previewProfile.skills.some((skill) => skill.evidence_text) ? (
                  <ul className="mt-4 grid gap-3 border-t border-zinc-200 pt-4">
                    {previewProfile.skills
                      .filter((skill) => skill.evidence_text)
                      .slice(0, 8)
                      .map((skill) => (
                        <li
                          key={`${skill.skill_id}-evidence`}
                          className="text-sm leading-6 text-zinc-700"
                        >
                          <span className="font-semibold text-zinc-950">
                            {skill.canonical_name ??
                              skill.skill_name ??
                              "Skill"}
                            :{" "}
                          </span>
                          {skill.evidence_text}
                        </li>
                      ))}
                  </ul>
                ) : null}
              </div>
            </div>

            {previewProfile.candidate.summary ? (
              <div className="workspace-card-soft bg-white p-4">
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
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
                  <div className="workspace-card-soft p-4">
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

                  <div className="workspace-card-soft p-4">
                    <p className="text-xs font-semibold uppercase text-zinc-500">
                      Other candidates there
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950">
                      {candidateLeadResult.peer_candidates.length}
                    </p>
                  </div>

                  <div className="workspace-card-soft p-4">
                    <p className="text-xs font-semibold uppercase text-zinc-500">
                      Known contacts
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950">
                      {candidateLeadResult.contacts.length}
                    </p>
                  </div>

                  <div className="workspace-card-soft p-4">
                    <p className="text-xs font-semibold uppercase text-zinc-500">
                      Interaction evidence
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950">
                      {candidateLeadResult.interactions.length}
                    </p>
                  </div>

                  <div className="workspace-card-soft p-4">
                    <p className="text-xs font-semibold uppercase text-zinc-500">
                      Open opportunities
                    </p>
                    <p className="mt-2 text-lg font-semibold text-zinc-950">
                      {candidateLeadResult.opportunities.length}
                    </p>
                  </div>
                </div>

                <div className="workspace-card-soft p-4">
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

                <div className="grid gap-6 xl:grid-cols-3">
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
                      <div className="workspace-card-soft p-4 text-sm leading-6 text-zinc-700">
                        No contacts are linked to this company yet.
                      </div>
                    ) : (
                      candidateLeadResult.contacts.map((contact) => (
                        <article
                          key={contact.contact_id}
                          className="workspace-card p-4"
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
                        Known opportunities at this company
                      </h4>
                      <p className="mt-2 text-sm leading-6 text-zinc-700">
                        Existing opportunities already linked to the same target company.
                      </p>
                    </div>

                    {candidateLeadResult.opportunities.length === 0 ? (
                      <div className="workspace-card-soft p-4 text-sm leading-6 text-zinc-700">
                        No canonical opportunities are linked to this company yet.
                      </div>
                    ) : (
                      candidateLeadResult.opportunities.map((opportunity) => (
                        <article
                          key={opportunity.opportunity_id}
                          className="workspace-card p-4"
                        >
                          <h5 className="text-lg font-semibold text-zinc-950">
                            {opportunity.title ?? "Untitled opportunity"}
                          </h5>
                          <p className="mt-1 text-sm leading-6 text-zinc-700">
                            {opportunity.contact_name
                              ? `${opportunity.contact_name}${opportunity.contact_role_title ? ` | ${opportunity.contact_role_title}` : ""}`
                              : "No linked contact yet"}
                          </p>
                          <p className="mt-3 text-sm leading-6 text-zinc-900">
                            {opportunity.smart_summary ?? "No opportunity summary available."}
                          </p>
                          <p className="mt-3 text-xs uppercase text-zinc-500">
                            {opportunity.stage ?? "Unknown stage"} | Next task{" "}
                            {formatTimestamp(opportunity.next_task_at)} | Value{" "}
                            {formatCurrencyValue(opportunity.value)}
                          </p>
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
                      <div className="workspace-card-soft p-4 text-sm leading-6 text-zinc-700">
                        No recent interaction evidence was returned.
                      </div>
                    ) : (
                      candidateLeadResult.interactions.map((interaction) => (
                        <article
                          key={interaction.interaction_id}
                          className="workspace-card p-4"
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
                          <dl className="mt-3 grid gap-1 text-sm leading-6 text-zinc-800">
                            {interaction.job_title ? (
                              <div>
                                <dt className="inline font-semibold">Job:</dt>{" "}
                                <dd className="inline">{interaction.job_title}</dd>
                              </div>
                            ) : null}
                            {interaction.company_name ? (
                              <div>
                                <dt className="inline font-semibold">Company:</dt>{" "}
                                <dd className="inline">{interaction.company_name}</dd>
                              </div>
                            ) : null}
                            {interaction.contact_id ? (
                              <div>
                                <dt className="inline font-semibold">Contact link:</dt>{" "}
                                <dd className="inline">Linked</dd>
                              </div>
                            ) : null}
                          </dl>
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
                      <div className="workspace-card-soft p-4 text-sm leading-6 text-zinc-700">
                        No canonical jobs are linked to this company yet.
                      </div>
                    ) : (
                      candidateLeadResult.jobs.map((job) => (
                        <article key={job.job_id} className="workspace-card p-4">
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
                      <div className="workspace-card-soft p-4 text-sm leading-6 text-zinc-700">
                        No other linked candidates were returned for this company.
                      </div>
                    ) : (
                      candidateLeadResult.peer_candidates.map((peer) => (
                        <article
                          key={`${peer.candidate_id}-${peer.document_id}-peer`}
                          className="workspace-card p-4"
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

      <section
        id="shortlist-results"
        ref={shortlistSectionRef}
        className="order-40 grid gap-6 rounded-md border border-emerald-200 bg-[#f7fbf8] p-6 shadow-sm sm:p-8"
      >
        <div className="flex flex-col gap-3 border-b border-zinc-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-3xl font-semibold text-zinc-950">
              Recruiter shortlist
            </h2>
            <p className="mt-2 max-w-3xl text-base leading-7 text-zinc-700">
              Final recruiter-facing output after grounded retrieval plus LLM
              reranking over the retrieved candidate pool.
            </p>
          </div>

          <div className="flex flex-col items-start gap-3 sm:items-end">
            <div className="text-sm text-zinc-600">
              {submittedJobDescription
                ? shortlistCountLabel
                : "Run shortlist to see the top fit."}
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <label className="grid gap-1 text-xs font-semibold uppercase text-zinc-500">
                Link expiry
                <select
                  value={shortlistShareExpiryDays}
                  onChange={(event) =>
                    setShortlistShareExpiryDays(event.target.value)
                  }
                  className="workspace-select h-11 min-w-28 px-3 text-sm font-semibold normal-case text-zinc-950"
                >
                  <option value="7">7 days</option>
                  <option value="14">14 days</option>
                  <option value="30">30 days</option>
                </select>
              </label>
              <button
                type="button"
                onClick={() => void createShortlistShare()}
                disabled={
                  isShortlistShareLoading ||
                  !matchRunId ||
                  shortlistResults.length === 0
                }
                className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-5 text-sm font-semibold text-zinc-950 transition hover:border-emerald-500 disabled:cursor-not-allowed disabled:bg-zinc-200 disabled:text-zinc-500"
              >
                {isShortlistShareLoading ? "Creating link..." : "Create secure link"}
              </button>
              <button
                type="button"
                onClick={() => void exportShortlistPackage()}
                disabled={
                  isShortlistExportLoading ||
                  !matchRunId ||
                  shortlistResults.length === 0
                }
                className="inline-flex h-11 items-center justify-center rounded-md border border-emerald-800 bg-emerald-800 px-5 text-sm font-semibold text-white transition hover:bg-emerald-900 disabled:cursor-not-allowed disabled:border-zinc-300 disabled:bg-zinc-300"
              >
                {isShortlistExportLoading
                  ? "Preparing package..."
                  : "Download shortlist + CVs"}
              </button>
            </div>
          </div>
        </div>

        {shortlistShareUrl ? (
          <div className="grid gap-3 rounded-md border border-sky-200 bg-sky-50 p-4">
            <p className="text-sm font-semibold text-sky-950">
              Secure shortlist link
            </p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                type="text"
                readOnly
                value={shortlistShareUrl}
                onFocus={(event) => event.currentTarget.select()}
                className="workspace-input h-11 min-w-0 flex-1 px-3 text-sm text-zinc-800"
                aria-label="Secure shortlist link"
              />
              <button
                type="button"
                onClick={() => void copyShortlistShareUrl()}
                className="inline-flex h-11 items-center justify-center rounded-md border border-sky-300 bg-white px-4 text-sm font-semibold text-sky-900 transition hover:bg-sky-100"
              >
                Copy link
              </button>
              <a
                href={shortlistShareUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-11 items-center justify-center rounded-md bg-sky-900 px-4 text-sm font-semibold text-white transition hover:bg-sky-950"
              >
                Open link
              </a>
            </div>
            <p className="text-xs leading-5 text-sky-800">
              Only approved signed-in workspace accounts can open this link.
            </p>
          </div>
        ) : null}

        {shortlistShareMessage ? (
          <div className="rounded-md border border-sky-200 bg-white p-4 text-sm leading-6 text-sky-800">
            {shortlistShareMessage}
          </div>
        ) : null}

        {shortlistShareErrorMessage ? (
          <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
            {shortlistShareErrorMessage}
          </div>
        ) : null}

        {shortlistExportMessage ? (
          <div className="rounded-md border border-emerald-200 bg-white p-4 text-sm leading-6 text-emerald-800">
            {shortlistExportMessage}
          </div>
        ) : null}

        {shortlistExportErrorMessage ? (
          <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
            {shortlistExportErrorMessage}
          </div>
        ) : null}

        {submittedJobDescription && retrievedCandidateCount > 0 ? (
          <div className="rounded-md border border-emerald-200 bg-white p-4 text-sm leading-6 text-zinc-700">
            Candidate pool sent to reranking:{" "}
            <span className="font-medium text-zinc-900">
              {retrievedCandidateCount}
            </span>
          </div>
        ) : null}

        {activeCompanyContextName ? (
          <div className="grid gap-4 rounded-md border border-sky-200 bg-white p-5">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase text-zinc-500">
                  Target company context
                </p>
                <h3 className="mt-2 text-xl font-semibold text-zinc-950">
                  What do we already know about {activeCompanyContextName}?
                </h3>
                <p className="mt-2 text-sm leading-6 text-zinc-700">
                  This brings in existing company-linked contacts, interactions,
                  jobs, and opportunities alongside the candidate shortlist.
                </p>
              </div>

              <a
                href={`/company?company=${encodeURIComponent(activeCompanyContextName)}`}
                className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
              >
                Open full company intelligence
              </a>
            </div>

            {companyDiscoveryLoading ? (
              <div className="rounded-md border border-sky-200 bg-sky-50 p-4 text-sm leading-6 text-sky-900">
                Loading linked company context for {activeCompanyContextName}.
              </div>
            ) : null}

            {!companyDiscoveryLoading ? (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4">
                  <p className="text-xs font-semibold uppercase text-zinc-500">
                    Contacts
                  </p>
                  <p className="mt-2 text-lg font-semibold text-zinc-950">
                    {companyContactResults.length}
                  </p>
                </div>

                <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4">
                  <p className="text-xs font-semibold uppercase text-zinc-500">
                    Interactions
                  </p>
                  <p className="mt-2 text-lg font-semibold text-zinc-950">
                    {companyInteractionResults.length}
                  </p>
                </div>

                <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4">
                  <p className="text-xs font-semibold uppercase text-zinc-500">
                    Jobs
                  </p>
                  <p className="mt-2 text-lg font-semibold text-zinc-950">
                    {companyJobResults.length}
                  </p>
                </div>

                <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4">
                  <p className="text-xs font-semibold uppercase text-zinc-500">
                    Opportunities
                  </p>
                  <p className="mt-2 text-lg font-semibold text-zinc-950">
                    {companyOpportunityResults.length}
                  </p>
                </div>
              </div>
            ) : null}

            {!companyDiscoveryLoading &&
            (primaryCompanyContact || primaryCompanyInteraction) ? (
              <div className="grid gap-4 xl:grid-cols-2">
                <article className="rounded-md border border-zinc-200 bg-zinc-50 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800">
                      Best known contact
                    </span>
                    {primaryCompanyContact?.is_hiring_manager ? (
                      <span className="rounded-md border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-800">
                        Hiring manager
                      </span>
                    ) : null}
                    {primaryCompanyContact ? (
                      <span className="rounded-md border border-zinc-200 bg-white px-3 py-1 text-xs font-semibold text-zinc-700">
                        {formatCompanyMatchSourceLabel(
                          primaryCompanyContact.company_match_source,
                        )}
                      </span>
                    ) : null}
                  </div>

                  {primaryCompanyContact ? (
                    <>
                      <h4 className="mt-4 text-lg font-semibold text-zinc-950">
                        {primaryCompanyContact.full_name ?? "Unnamed contact"}
                      </h4>
                      <p className="mt-1 text-sm leading-6 text-zinc-700">
                        {primaryCompanyContact.role_title ??
                          primaryCompanyContact.headline ??
                          "Role not available"}
                      </p>
                      <p className="mt-3 text-sm leading-6 text-zinc-900">
                        {primaryCompanyContact.primary_email ??
                          primaryCompanyContact.primary_phone ??
                          "No direct contact details"}
                      </p>
                      <p className="mt-2 text-sm leading-6 text-zinc-600">
                        {primaryCompanyContact.location ??
                          "Location not available"}
                      </p>
                    </>
                  ) : (
                    <div className="mt-4 rounded-md border border-dashed border-zinc-300 bg-white p-4 text-sm leading-6 text-zinc-600">
                      No contact route has been linked to this company yet.
                    </div>
                  )}
                </article>

                <article className="rounded-md border border-zinc-200 bg-zinc-50 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md border border-violet-200 bg-violet-50 px-3 py-1 text-xs font-semibold text-violet-800">
                      Strongest prior interaction
                    </span>
                    {primaryCompanyInteraction ? (
                      <>
                        <span className="rounded-md border border-zinc-200 bg-white px-3 py-1 text-xs font-semibold text-zinc-700">
                          {formatUnderscoredLabel(
                            primaryCompanyInteraction.interaction_type,
                          )}
                        </span>
                        <span className="rounded-md border border-zinc-200 bg-white px-3 py-1 text-xs font-semibold text-zinc-700">
                          {formatUnderscoredLabel(
                            primaryCompanyInteraction.matched_entity_type,
                          )}
                        </span>
                      </>
                    ) : null}
                  </div>

                  {primaryCompanyInteraction ? (
                    <>
                      <h4 className="mt-4 text-lg font-semibold text-zinc-950">
                        {primaryCompanyInteraction.full_name ??
                          primaryCompanyInteraction.subject ??
                          "Interaction"}
                      </h4>
                      <p className="mt-1 text-sm leading-6 text-zinc-700">
                        {primaryCompanyInteraction.role_title ??
                          primaryCompanyInteraction.company_name ??
                          "No linked role title"}
                      </p>
                      <p className="mt-3 text-sm leading-6 text-zinc-900">
                        {primaryCompanyInteraction.summary ??
                          primaryCompanyInteraction.subject ??
                          primaryCompanyInteraction.body ??
                          "No interaction summary available."}
                      </p>
                      <p className="mt-3 text-xs uppercase text-zinc-500">
                        {formatTimestamp(primaryCompanyInteraction.occurred_at)} |{" "}
                        {primaryCompanyInteraction.source_system ??
                          "Unknown source"}
                      </p>
                    </>
                  ) : (
                    <div className="mt-4 rounded-md border border-dashed border-zinc-300 bg-white p-4 text-sm leading-6 text-zinc-600">
                      No prior interaction history has been linked to this
                      company yet.
                    </div>
                  )}
                </article>
              </div>
            ) : null}

            {companyContactsErrorMessage ? (
              <div className="border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
                {companyContactsErrorMessage}
              </div>
            ) : null}

            {!companyDiscoveryLoading &&
            companyContactResults.length === 0 &&
            companyInteractionResults.length === 0 &&
            companyJobResults.length === 0 &&
            companyOpportunityResults.length === 0 &&
            !companyContactsErrorMessage ? (
              <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4 text-sm leading-6 text-zinc-700">
                No linked company context has been found for this employer yet.
              </div>
            ) : null}

            {!companyDiscoveryLoading && companyContactResults.length > 0 ? (
              <div className="grid gap-4">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                  <div>
                    <h4 className="text-lg font-semibold text-zinc-950">
                      Known contacts at this company
                    </h4>
                    <p className="mt-1 text-sm leading-6 text-zinc-700">
                      Top linked contacts already in the database.
                    </p>
                  </div>
                  <div className="text-sm text-zinc-600">
                    Showing {Math.min(companyContactResults.length, 3)} of{" "}
                    {companyContactResults.length}
                  </div>
                </div>

                <div className="grid gap-4 xl:grid-cols-3">
                  {companyContactResults.slice(0, 3).map((contact) => (
                    <article
                      key={`shortlist-company-contact-${contact.contact_id}`}
                      className="rounded-md border border-zinc-200 bg-zinc-50 p-4"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        {contact.is_hiring_manager ? (
                          <span className="rounded-md border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-800">
                            Hiring manager
                          </span>
                        ) : null}
                        <span className="rounded-md border border-zinc-200 bg-white px-3 py-1 text-xs font-semibold text-zinc-700">
                          {formatCompanyMatchSourceLabel(contact.company_match_source)}
                        </span>
                      </div>

                      <h5 className="mt-4 text-lg font-semibold text-zinc-950">
                        {contact.full_name ?? "Unnamed contact"}
                      </h5>
                      <p className="mt-1 text-sm leading-6 text-zinc-700">
                        {contact.role_title ?? contact.headline ?? "Role not available"}
                      </p>
                      <p className="mt-3 text-sm leading-6 text-zinc-900">
                        {contact.primary_email ??
                          contact.primary_phone ??
                          "No direct contact details"}
                      </p>
                    </article>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
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
          <div className="rounded-md border border-dashed border-zinc-300 bg-white p-6 text-sm leading-7 text-zinc-600">
            Use the shortlist action when you want the reasoning model to turn
            retrieval output into a recruiter-style top list with strengths,
            gaps, and fit summaries.
          </div>
        ) : null}

        <CandidateComparison candidates={shortlistResults} />

        <div className="grid gap-5">
          {shortlistResults.map((result, index) => (
            <article
              key={`${result.candidate_id}-${result.document_id}`}
              className="rounded-md border border-zinc-200 bg-white p-6 shadow-sm"
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
                    {result.graph_context_score !== null ? (
                      <span className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700">
                        Graph {result.graph_context_score.toFixed(3)}
                      </span>
                    ) : null}
                    {result.retrieval_sources.map((source) => (
                      <span
                        key={`${result.candidate_id}-${source}`}
                        className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold text-zinc-700"
                      >
                        {formatRetrievalSourceLabel(source)}
                      </span>
                    ))}
                    <span
                      title={
                        result.source_systems.length > 0
                          ? `Sources: ${result.source_systems.join(", ")}`
                          : "No linked source provenance found"
                      }
                      className={`rounded-md border px-3 py-1 text-xs font-semibold ${candidateSourceCategoryClassName(
                        result.source_category,
                      )}`}
                    >
                      {formatCandidateSourceCategory(result.source_category)}
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

                  <p className="mt-4 max-w-3xl text-base leading-7 text-zinc-900">
                    {result.fit_summary}
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-3 lg:w-[15rem] lg:grid-cols-1">
                  {result.document_id ? (
                    <a
                      href={`/api/v1/candidates/${result.candidate_id}/current-resume`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                    >
                      Open CV
                    </a>
                  ) : (
                    <span className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-200 bg-zinc-100 px-4 text-sm font-semibold text-zinc-500">
                      No CV on file
                    </span>
                  )}

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
                    className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
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
                    Ranking input
                  </dt>
                  <dd className="mt-1 text-sm leading-6 text-zinc-900">
                    {result.ranking_input_score !== null
                      ? result.ranking_input_score.toFixed(3)
                      : "Unknown"}
                  </dd>
                </div>

                <div>
                  <dt className="text-xs font-semibold uppercase text-zinc-500">
                    Resume document
                  </dt>
                  <dd className="mt-1 break-words text-sm leading-6 text-zinc-900">
                    {result.document_title ??
                      result.document_id ??
                      "Profile data only"}
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
                <div className="rounded-md border border-zinc-200 bg-[#f8faf8] p-4">
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

                <div className="rounded-md border border-zinc-200 bg-[#fff8f4] p-4">
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

              <div className="mt-6 border-t border-zinc-200 pt-6">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase text-zinc-500">
                      Recruiter feedback
                    </p>
                    <p className="mt-2 text-sm leading-6 text-zinc-700">
                      Record whether this result is useful. Saved judgements build
                      the labelled evidence needed to evaluate and tune matching.
                    </p>
                  </div>
                  {feedbackByCandidateId[result.candidate_id]?.message ? (
                    <p
                      className={`text-sm font-semibold ${
                        feedbackByCandidateId[result.candidate_id]?.status ===
                        "error"
                          ? "text-rose-700"
                          : "text-emerald-700"
                      }`}
                      role="status"
                    >
                      {feedbackByCandidateId[result.candidate_id]?.message}
                    </p>
                  ) : null}
                </div>

                <div className="mt-4 flex flex-wrap gap-3">
                  <button
                    type="button"
                    aria-pressed={
                      feedbackByCandidateId[result.candidate_id]?.value ===
                      "good_match"
                    }
                    onClick={() =>
                      updateCandidateFeedback(result.candidate_id, {
                        value: "good_match",
                        status: "idle",
                        message: null,
                      })
                    }
                    className={`inline-flex h-10 items-center justify-center rounded-md border px-4 text-sm font-semibold transition ${
                      feedbackByCandidateId[result.candidate_id]?.value ===
                      "good_match"
                        ? "border-emerald-700 bg-emerald-700 text-white"
                        : "border-zinc-300 bg-white text-zinc-900 hover:border-emerald-600"
                    }`}
                  >
                    Good match
                  </button>
                  <button
                    type="button"
                    aria-pressed={
                      feedbackByCandidateId[result.candidate_id]?.value ===
                      "not_suitable"
                    }
                    onClick={() =>
                      updateCandidateFeedback(result.candidate_id, {
                        value: "not_suitable",
                        status: "idle",
                        message: null,
                      })
                    }
                    className={`inline-flex h-10 items-center justify-center rounded-md border px-4 text-sm font-semibold transition ${
                      feedbackByCandidateId[result.candidate_id]?.value ===
                      "not_suitable"
                        ? "border-rose-700 bg-rose-700 text-white"
                        : "border-zinc-300 bg-white text-zinc-900 hover:border-rose-600"
                    }`}
                  >
                    Not suitable
                  </button>
                </div>

                {feedbackByCandidateId[result.candidate_id]?.value ? (
                  <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
                    <label className="grid gap-2 text-sm font-semibold text-zinc-800">
                      Reason or note (optional)
                      <textarea
                        value={
                          feedbackByCandidateId[result.candidate_id]?.reason ?? ""
                        }
                        maxLength={1000}
                        rows={2}
                        onChange={(event) =>
                          updateCandidateFeedback(result.candidate_id, {
                            reason: event.target.value,
                            status: "idle",
                            message: null,
                          })
                        }
                        placeholder="For example: strong technical fit, but location is unsuitable."
                        className="min-h-20 w-full resize-y rounded-md border border-zinc-300 bg-white px-3 py-2 font-normal text-zinc-950 outline-none transition focus:border-emerald-600"
                      />
                    </label>
                    <button
                      type="button"
                      disabled={
                        feedbackByCandidateId[result.candidate_id]?.status ===
                        "saving"
                      }
                      onClick={() => {
                        void submitCandidateFeedback(result, index + 1);
                      }}
                      className="inline-flex h-11 items-center justify-center rounded-md bg-zinc-950 px-5 text-sm font-semibold text-white transition hover:bg-emerald-800 disabled:cursor-wait disabled:bg-zinc-400"
                    >
                      {feedbackByCandidateId[result.candidate_id]?.status ===
                      "saving"
                        ? "Saving..."
                        : "Save feedback"}
                    </button>
                  </div>
                ) : null}
              </div>

              {result.graph_evidence ? (
                <div className="mt-6 grid gap-4 rounded-md border border-zinc-200 bg-zinc-50 p-4">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <p className="text-xs font-semibold uppercase text-zinc-500">
                        Linked evidence
                      </p>
                      <p className="mt-2 text-sm leading-6 text-zinc-700">
                        Bounded graph-style context from linked canonical skills,
                        contacts, interactions, jobs, and opportunities.
                      </p>
                    </div>

                    <div className="text-sm text-zinc-600">
                      {result.graph_evidence.current_company_name
                        ? `Company context: ${result.graph_evidence.current_company_name}`
                        : "No current-company context linked."}
                    </div>
                  </div>

                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                    <div className="rounded-md border border-zinc-200 bg-white p-4">
                      <p className="text-xs font-semibold uppercase text-zinc-500">
                        Skills
                      </p>
                      <p className="mt-2 text-lg font-semibold text-zinc-950">
                        {result.graph_evidence.skill_names.length}
                      </p>
                    </div>

                    <div className="rounded-md border border-zinc-200 bg-white p-4">
                      <p className="text-xs font-semibold uppercase text-zinc-500">
                        Contacts
                      </p>
                      <p className="mt-2 text-lg font-semibold text-zinc-950">
                        {result.graph_evidence.contacts_count}
                      </p>
                    </div>

                    <div className="rounded-md border border-zinc-200 bg-white p-4">
                      <p className="text-xs font-semibold uppercase text-zinc-500">
                        Interactions
                      </p>
                      <p className="mt-2 text-lg font-semibold text-zinc-950">
                        {result.graph_evidence.interactions_count}
                      </p>
                    </div>

                    <div className="rounded-md border border-zinc-200 bg-white p-4">
                      <p className="text-xs font-semibold uppercase text-zinc-500">
                        Jobs
                      </p>
                      <p className="mt-2 text-lg font-semibold text-zinc-950">
                        {result.graph_evidence.jobs_count}
                      </p>
                    </div>

                    <div className="rounded-md border border-zinc-200 bg-white p-4">
                      <p className="text-xs font-semibold uppercase text-zinc-500">
                        Opportunities
                      </p>
                      <p className="mt-2 text-lg font-semibold text-zinc-950">
                        {result.graph_evidence.opportunities_count}
                      </p>
                    </div>
                  </div>

                  {result.graph_evidence.skill_names.length > 0 ? (
                    <div>
                      <p className="text-xs font-semibold uppercase text-zinc-500">
                        Candidate skills
                      </p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {result.graph_evidence.skill_names.map((skillName) => (
                          <span
                            key={`${result.candidate_id}-${skillName}`}
                            className="rounded-md border border-zinc-200 px-3 py-1 text-sm text-zinc-900"
                          >
                            {skillName}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {(result.graph_evidence.recent_employment?.length ?? 0) > 0 ? (
                    <div>
                      <p className="text-xs font-semibold uppercase text-zinc-500">
                        Recent employment
                      </p>
                      <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                        {result.graph_evidence.recent_employment
                          ?.slice(0, 3)
                          .map((role, roleIndex) => (
                            <div
                              key={
                                role.employment_role_id ??
                                `${result.candidate_id}-graph-employment-${roleIndex}`
                              }
                              className="rounded-md border border-zinc-200 bg-white p-3 text-sm leading-6 text-zinc-800"
                            >
                              <p className="font-semibold text-zinc-950">
                                {role.role_title ?? "Role title unavailable"}
                              </p>
                              <p>{role.company_name ?? "Company unavailable"}</p>
                              <p className="text-xs text-zinc-500">
                                {formatEmploymentPeriod(role)}
                              </p>
                            </div>
                          ))}
                      </div>
                    </div>
                  ) : null}

                  <div className="grid gap-4 xl:grid-cols-2">
                    <div className="border border-zinc-200 p-4">
                      <p className="text-xs font-semibold uppercase text-zinc-500">
                        Contacts
                      </p>
                      <div className="mt-3 grid gap-3 text-sm leading-6 text-zinc-900">
                        {result.graph_evidence.contacts.length > 0 ? (
                          result.graph_evidence.contacts.map((contact) => (
                            <div
                              key={`${result.candidate_id}-${contact.contact_id}-graph-contact`}
                              className="rounded-md border border-zinc-200 bg-white p-3"
                            >
                              <p className="font-semibold text-zinc-950">
                                {contact.full_name ?? "Unnamed contact"}
                              </p>
                              <p className="text-zinc-700">
                                {contact.role_title ??
                                  contact.headline ??
                                  "Role not available"}
                              </p>
                              <p className="text-zinc-600">
                                {contact.primary_email ??
                                  contact.primary_phone ??
                                  "No direct contact details"}
                              </p>
                            </div>
                          ))
                        ) : (
                          <p>No contact evidence returned.</p>
                        )}
                      </div>
                    </div>

                    <div className="border border-zinc-200 p-4">
                      <p className="text-xs font-semibold uppercase text-zinc-500">
                        Recent interactions
                      </p>
                      <div className="mt-3 grid gap-3 text-sm leading-6 text-zinc-900">
                        {result.graph_evidence.interactions.length > 0 ? (
                          result.graph_evidence.interactions.map((interaction) => (
                            <div
                              key={`${result.candidate_id}-${interaction.interaction_id}-graph-interaction`}
                              className="rounded-md border border-zinc-200 bg-white p-3"
                            >
                              <p className="font-semibold text-zinc-950">
                                {interaction.full_name ??
                                  interaction.subject ??
                                  "Interaction"}
                              </p>
                              <p className="text-zinc-700">
                                {interaction.summary ??
                                  interaction.subject ??
                                  "No interaction summary available."}
                              </p>
                              <p className="text-zinc-600">
                                {formatTimestamp(interaction.occurred_at)} |{" "}
                                {interaction.source_system ?? "Unknown source"}
                              </p>
                            </div>
                          ))
                        ) : (
                          <p>No recent interaction evidence returned.</p>
                        )}
                      </div>
                    </div>

                    <div className="border border-zinc-200 p-4">
                      <p className="text-xs font-semibold uppercase text-zinc-500">
                        Linked jobs
                      </p>
                      <div className="mt-3 grid gap-3 text-sm leading-6 text-zinc-900">
                        {result.graph_evidence.jobs.length > 0 ? (
                          result.graph_evidence.jobs.map((job) => (
                            <div
                              key={`${result.candidate_id}-${job.job_id}-graph-job`}
                              className="rounded-md border border-zinc-200 bg-white p-3"
                            >
                              <p className="font-semibold text-zinc-950">
                                {job.title ?? "Untitled job"}
                              </p>
                              <p className="text-zinc-700">
                                {job.hiring_manager_name ??
                                  job.company_name ??
                                  "No linked hiring context"}
                              </p>
                              <p className="text-zinc-600">
                                {job.status ?? "Unknown status"}
                              </p>
                            </div>
                          ))
                        ) : (
                          <p>No linked job evidence returned.</p>
                        )}
                      </div>
                    </div>

                    <div className="border border-zinc-200 p-4">
                      <p className="text-xs font-semibold uppercase text-zinc-500">
                        Linked opportunities
                      </p>
                      <div className="mt-3 grid gap-3 text-sm leading-6 text-zinc-900">
                        {result.graph_evidence.opportunities.length > 0 ? (
                          result.graph_evidence.opportunities.map((opportunity) => (
                            <div
                              key={`${result.candidate_id}-${opportunity.opportunity_id}-graph-opportunity`}
                              className="rounded-md border border-zinc-200 bg-white p-3"
                            >
                              <p className="font-semibold text-zinc-950">
                                {opportunity.title ?? "Untitled opportunity"}
                              </p>
                              <p className="text-zinc-700">
                                {opportunity.contact_name ??
                                  opportunity.company_name ??
                                  "No linked contact"}
                              </p>
                              <p className="text-zinc-600">
                                {opportunity.stage ?? "Unknown stage"}
                              </p>
                            </div>
                          ))
                        ) : (
                          <p>No linked opportunity evidence returned.</p>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}

              {renderRetrievalDiagnostics(result, {
                primaryScoreLabel: "Fused retrieval",
                primaryScoreValue: result.retrieval_score,
              })}

              <div className="mt-6 rounded-md border border-zinc-200 bg-zinc-50 p-4">
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

      <section
        id="search-results"
        ref={searchResultsSectionRef}
        className="order-30 grid gap-6 rounded-md border border-zinc-200 bg-white p-6 shadow-sm sm:p-8"
      >
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

        <button
          type="button"
          onClick={() => setIsSearchResultsExpanded((current) => !current)}
          className="flex items-center justify-between rounded-md border border-zinc-200 bg-zinc-50 px-4 py-3 text-left transition hover:border-zinc-300 hover:bg-zinc-100"
          aria-expanded={isSearchResultsExpanded}
          aria-controls="corpus-search-panel"
        >
          <div className="grid gap-1">
            <span className="text-sm font-semibold text-zinc-950">
              {isSearchResultsExpanded ? "Hide corpus results" : "Show corpus results"}
            </span>
            <span className="text-sm leading-6 text-zinc-600">
              Open this when you want to inspect the raw retrieval pool before
              running the final shortlist.
            </span>
          </div>
          <span className="text-lg text-zinc-500" aria-hidden="true">
            {isSearchResultsExpanded ? "▾" : "▸"}
          </span>
        </button>

        {isSearchResultsExpanded ? (
          <div id="corpus-search-panel" className="grid gap-6">
            {submittedSearchQuery ? (
              <div className="grid gap-3 rounded-md border border-zinc-200 bg-zinc-50 p-4">
                <button
                  type="button"
                  onClick={() =>
                    setIsSearchQueryDetailsExpanded((current) => !current)
                  }
                  className="flex items-center justify-between text-left"
                  aria-expanded={isSearchQueryDetailsExpanded}
                  aria-controls="corpus-search-query-details"
                >
                  <div className="grid gap-1">
                    <span className="text-sm font-semibold text-zinc-950">
                      Retrieval query details
                    </span>
                    <span className="text-sm leading-6 text-zinc-600">
                      Expand this to inspect the exact terms used for the first
                      pass over the CV corpus.
                    </span>
                  </div>
                  <span className="text-lg text-zinc-500" aria-hidden="true">
                    {isSearchQueryDetailsExpanded ? "▾" : "▸"}
                  </span>
                </button>

                {isSearchQueryDetailsExpanded ? (
                  <div
                    id="corpus-search-query-details"
                    className="grid gap-1 text-sm leading-6 text-zinc-600"
                  >
                    <p>
                      Retrieval terms:{" "}
                      <span className="font-medium text-zinc-900">
                        {submittedSearchQuery}
                      </span>
                    </p>
                    {submittedJobDescription ? (
                      <p>Shortlist reasoning still uses the full brief above.</p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}

            {submittedSearchQuery &&
            searchResults.length === 0 &&
            !searchErrorMessage ? (
          <div className="grid gap-3 border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
            <p>
              Corpus search returned no CV matches for that retrieval query.
            </p>
            {jobDescription.trim() !== retrievalFocusTerms.trim() ? (
              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => {
                    applyFullBriefRetrievalFocusTerms();
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
                    const regeneratedTerms =
                      deriveRetrievalFocusTerms(jobDescription);
                    applyAutoRetrievalFocusTerms();
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
          <div className="rounded-md border border-dashed border-zinc-300 bg-zinc-50 p-6 text-sm leading-7 text-zinc-600">
            Start here when you want to inspect the raw candidate pool before
            running the LLM shortlist. This helps you sanity-check whether the
            retrieval layer is seeing the right CVs.
          </div>
        ) : null}

        <div className="grid gap-5">
          {searchResults.map((result, index) => (
            <article
              key={`${result.candidate_id}-${result.document_id}`}
              className="rounded-md border border-zinc-200 bg-[#fbfbf9] p-6 shadow-sm"
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
                    <span
                      title={
                        result.source_systems.length > 0
                          ? `Sources: ${result.source_systems.join(", ")}`
                          : "No linked source provenance found"
                      }
                      className={`rounded-md border px-3 py-1 text-xs font-semibold ${candidateSourceCategoryClassName(
                        result.source_category,
                      )}`}
                    >
                      {formatCandidateSourceCategory(result.source_category)}
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

                <div className="grid gap-3 sm:grid-cols-3 lg:w-[15rem] lg:grid-cols-1">
                  {result.document_id ? (
                    <a
                      href={`/api/v1/candidates/${result.candidate_id}/current-resume`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
                    >
                      Open CV
                    </a>
                  ) : (
                    <span className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-200 bg-zinc-100 px-4 text-sm font-semibold text-zinc-500">
                      No CV on file
                    </span>
                  )}

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
                    className="inline-flex h-11 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:border-zinc-500"
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
                    {result.document_title ??
                      result.document_id ??
                      "Profile data only"}
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

              <div className="mt-6 rounded-md border border-zinc-200 bg-white p-4">
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
          </div>
        ) : null}
      </section>
    </div>
      );
}
