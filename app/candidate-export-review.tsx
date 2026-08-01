import { CandidateStrengthsAndGaps } from "./candidate-assessment";
import { CandidateEvidenceIndicator } from "./candidate-evidence-indicator";

export type ExportReviewChecks = {
  roleBrief: boolean;
  candidateOrder: boolean;
  evidenceAndFiles: boolean;
};

type ExportReviewCandidate = {
  candidate_id: string;
  full_name: string | null;
  current_title: string | null;
  current_company_name: string | null;
  fit_score: number;
  fit_summary: string;
  document_id: string | null;
  source_category: string;
  strengths: string[];
  gaps: string[];
};

export function CandidateExportReview({
  roleTitle,
  jobDescription,
  candidates,
  checks,
  isExporting,
  onRoleTitleChange,
  onCheckChange,
  onCancel,
  onExport,
}: {
  roleTitle: string;
  jobDescription: string;
  candidates: ExportReviewCandidate[];
  checks: ExportReviewChecks;
  isExporting: boolean;
  onRoleTitleChange: (value: string) => void;
  onCheckChange: (key: keyof ExportReviewChecks, checked: boolean) => void;
  onCancel: () => void;
  onExport: () => void;
}) {
  const linkedCvCount = candidates.filter((candidate) => candidate.document_id).length;
  const profileOnlyCount = candidates.filter(
    (candidate) => !candidate.document_id,
  ).length;
  const gapCount = candidates.reduce(
    (total, candidate) => total + candidate.gaps.length,
    0,
  );
  const isConfirmed = Object.values(checks).every(Boolean);

  return (
    <section
      aria-labelledby="candidate-export-review-title"
      className="grid gap-5 rounded-md border-2 border-amber-300 bg-white p-5 shadow-sm sm:p-6"
    >
      <div className="flex flex-col gap-2 border-b border-zinc-200 pb-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-800">
            Final checkpoint
          </p>
          <h3
            id="candidate-export-review-title"
            className="mt-1 text-2xl font-semibold text-zinc-950"
          >
            Review before export
          </h3>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-700">
            Confirm exactly what the recruiter package will contain. Export does
            not rerun retrieval or change the candidate ranking.
          </p>
        </div>
        <button
          type="button"
          onClick={onCancel}
          disabled={isExporting}
          className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-900 transition hover:border-zinc-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Close review
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.7fr)]">
        <label className="grid gap-2 text-sm font-semibold text-zinc-900">
          Export role title
          <input
            type="text"
            value={roleTitle}
            onChange={(event) => onRoleTitleChange(event.target.value)}
            maxLength={200}
            className="workspace-input h-11 px-3 text-sm font-normal text-zinc-950"
          />
          <span className="text-xs font-normal leading-5 text-zinc-500">
            This appears in the Word shortlist and exported package filename.
          </span>
        </label>

        <details className="rounded-md border border-zinc-200 bg-zinc-50 p-4">
          <summary className="cursor-pointer text-sm font-semibold text-zinc-900">
            Inspect submitted role brief
          </summary>
          <p className="mt-3 max-h-56 overflow-y-auto whitespace-pre-wrap text-xs leading-5 text-zinc-700">
            {jobDescription}
          </p>
        </details>
      </div>

      <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4">
          <dt className="text-xs font-semibold uppercase text-zinc-500">Candidates</dt>
          <dd className="mt-1 text-xl font-semibold text-zinc-950">
            {candidates.length}
          </dd>
        </div>
        <div className="rounded-md border border-violet-200 bg-violet-50 p-4">
          <dt className="text-xs font-semibold uppercase text-violet-700">Linked CVs</dt>
          <dd className="mt-1 text-xl font-semibold text-violet-950">
            {linkedCvCount}
          </dd>
        </div>
        <div className="rounded-md border border-sky-200 bg-sky-50 p-4">
          <dt className="text-xs font-semibold uppercase text-sky-700">Without CVs</dt>
          <dd className="mt-1 text-xl font-semibold text-sky-950">
            {profileOnlyCount}
          </dd>
        </div>
        <div className="rounded-md border border-amber-200 bg-amber-50 p-4">
          <dt className="text-xs font-semibold uppercase text-amber-800">Gaps to clarify</dt>
          <dd className="mt-1 text-xl font-semibold text-amber-950">{gapCount}</dd>
        </div>
      </dl>

      <ol className="grid gap-4">
        {candidates.map((candidate, index) => (
          <li
            key={`export-review-${candidate.candidate_id}`}
            className="rounded-md border border-zinc-200 bg-zinc-50/60 p-4"
          >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase text-emerald-700">
                  Rank {index + 1} · Fit {candidate.fit_score}/100
                </p>
                <h4 className="mt-1 text-lg font-semibold text-zinc-950">
                  {candidate.full_name ?? "Unnamed candidate"}
                </h4>
                <p className="mt-1 text-sm text-zinc-700">
                  {candidate.current_title ?? "Title unavailable"}
                  {candidate.current_company_name
                    ? ` at ${candidate.current_company_name}`
                    : ""}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <CandidateEvidenceIndicator
                  sourceCategory={candidate.source_category}
                  compact
                />
                <span
                  className={`rounded-md border px-3 py-1 text-xs font-semibold ${
                    candidate.document_id
                      ? "border-violet-200 bg-violet-50 text-violet-900"
                      : "border-sky-200 bg-sky-50 text-sky-900"
                  }`}
                >
                  {candidate.document_id ? "CV will be requested" : "No CV to include"}
                </span>
              </div>
            </div>
            <p className="mt-3 text-sm leading-6 text-zinc-800">
              {candidate.fit_summary}
            </p>
            <div className="mt-4">
              <CandidateStrengthsAndGaps
                strengths={candidate.strengths}
                gaps={candidate.gaps}
              />
            </div>
          </li>
        ))}
      </ol>

      <fieldset className="grid gap-3 rounded-md border border-zinc-300 bg-zinc-50 p-4">
        <legend className="px-2 text-sm font-semibold text-zinc-950">
          Required confirmations
        </legend>
        <ReviewConfirmation
          checked={checks.roleBrief}
          onChange={(checked) => onCheckChange("roleBrief", checked)}
          label="The role title and submitted brief are correct for this export."
        />
        <ReviewConfirmation
          checked={checks.candidateOrder}
          onChange={(checked) => onCheckChange("candidateOrder", checked)}
          label="I reviewed the candidate order, fit summaries, strengths, and gaps."
        />
        <ReviewConfirmation
          checked={checks.evidenceAndFiles}
          onChange={(checked) => onCheckChange("evidenceAndFiles", checked)}
          label="I reviewed evidence types and understand that unavailable CVs are recorded in the manifest."
        />
      </fieldset>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end">
        {!isConfirmed ? (
          <p className="text-sm text-amber-800">
            Complete all three confirmations to enable export.
          </p>
        ) : null}
        <button
          type="button"
          onClick={onExport}
          disabled={!isConfirmed || isExporting || roleTitle.trim() === ""}
          className="inline-flex h-11 items-center justify-center rounded-md border border-emerald-800 bg-emerald-800 px-5 text-sm font-semibold text-white transition hover:bg-emerald-900 disabled:cursor-not-allowed disabled:border-zinc-300 disabled:bg-zinc-300"
        >
          {isExporting ? "Preparing package..." : "Confirm and download package"}
        </button>
      </div>
    </section>
  );
}

function ReviewConfirmation({
  checked,
  label,
  onChange,
}: {
  checked: boolean;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 text-sm leading-6 text-zinc-800">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-1 h-4 w-4 accent-emerald-700"
      />
      <span>{label}</span>
    </label>
  );
}
