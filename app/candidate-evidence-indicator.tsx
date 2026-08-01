type EvidencePresentation = {
  label: string;
  description: string;
  badgeClassName: string;
  dotClassName: string;
};

export type CandidateSourceDetail = {
  source_system: string;
  latest_record_received_at: string | null;
};

function formatSourceSystem(sourceSystem: string): string {
  const knownSources: Record<string, string> = {
    dropbox: "Dropbox",
    jobadder: "JobAdder",
    linkedin_helper: "Linked Helper",
    outlook: "Outlook",
    recruiterflow: "Recruiterflow",
    recruitly: "Recruitly",
  };
  const normalizedSource = sourceSystem.trim().toLowerCase();
  return (
    knownSources[normalizedSource] ??
    normalizedSource
      .replaceAll("_", " ")
      .replace(/\b\w/g, (character) => character.toUpperCase())
  );
}

function formatEvidenceDate(value: string | null): string {
  if (!value) {
    return "date unavailable";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

function getEvidencePresentation(sourceCategory: string): EvidencePresentation {
  if (sourceCategory === "cross_source") {
    return {
      label: "Cross-source evidence",
      description: "Current CV evidence plus structured profile enrichment.",
      badgeClassName: "border-teal-200 bg-teal-50 text-teal-900",
      dotClassName: "bg-teal-600",
    };
  }

  if (
    sourceCategory === "profile_only" ||
    sourceCategory === "linkedin_helper_only"
  ) {
    return {
      label: "Profile-only evidence",
      description: "Structured profile evidence; no current CV is linked.",
      badgeClassName: "border-sky-200 bg-sky-50 text-sky-900",
      dotClassName: "bg-sky-600",
    };
  }

  if (sourceCategory === "cv_backed") {
    return {
      label: "CV-backed evidence",
      description: "A current CV is linked to this canonical candidate.",
      badgeClassName: "border-violet-200 bg-violet-50 text-violet-900",
      dotClassName: "bg-violet-600",
    };
  }

  return {
    label: "Evidence unconfirmed",
    description: "Neither a current CV nor structured source evidence is confirmed.",
    badgeClassName: "border-amber-200 bg-amber-50 text-amber-900",
    dotClassName: "bg-amber-600",
  };
}

export function CandidateEvidenceIndicator({
  sourceCategory,
  compact = false,
}: {
  sourceCategory: string;
  compact?: boolean;
}) {
  const presentation = getEvidencePresentation(sourceCategory);

  return (
    <span className={compact ? "inline-flex" : "inline-grid gap-1.5"}>
      <span
        className={`inline-flex w-fit items-center gap-2 rounded-md border px-3 py-1 text-xs font-semibold ${presentation.badgeClassName}`}
      >
        <span
          aria-hidden="true"
          className={`h-2 w-2 rounded-full ${presentation.dotClassName}`}
        />
        {presentation.label}
      </span>
      {compact ? null : (
        <span className="max-w-72 text-xs leading-5 text-zinc-600">
          {presentation.description}
        </span>
      )}
    </span>
  );
}

export function CandidateEvidenceLegend() {
  return (
    <div className="grid gap-3 rounded-md border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-3">
      {(["cv_backed", "profile_only", "cross_source"] as const).map(
        (sourceCategory) => (
          <CandidateEvidenceIndicator
            key={sourceCategory}
            sourceCategory={sourceCategory}
          />
        ),
      )}
      <p className="text-xs leading-5 text-zinc-600 sm:col-span-3">
        CV dates describe the linked resume. Source receipt dates describe when
        evidence entered this system; they do not prove the upstream profile was
        updated on that date.
      </p>
    </div>
  );
}

export function CandidateEvidenceProvenance({
  sourceDetails = [],
  sourceSystems = [],
  resumeUpdatedAt,
  hasResumeDocument,
  compact = false,
}: {
  sourceDetails?: CandidateSourceDetail[];
  sourceSystems?: string[];
  resumeUpdatedAt: string | null;
  hasResumeDocument: boolean;
  compact?: boolean;
}) {
  const detailsBySource = new Map(
    sourceDetails.map((detail) => [detail.source_system, detail]),
  );
  for (const sourceSystem of sourceSystems) {
    if (!detailsBySource.has(sourceSystem)) {
      detailsBySource.set(sourceSystem, {
        source_system: sourceSystem,
        latest_record_received_at: null,
      });
    }
  }
  const resolvedDetails = Array.from(detailsBySource.values());

  if (!hasResumeDocument && resolvedDetails.length === 0) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">
        No linked CV or source-record provenance is available.
      </div>
    );
  }

  return (
    <div className="grid gap-2">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
        Provenance and freshness
      </p>
      <div className="flex flex-wrap gap-2">
        {hasResumeDocument ? (
          <span className="rounded-md border border-violet-200 bg-violet-50 px-3 py-1.5 text-xs leading-5 text-violet-950">
            <strong>Current CV</strong> · updated {formatEvidenceDate(resumeUpdatedAt)}
          </span>
        ) : null}
        {resolvedDetails.map((detail) => (
          <span
            key={detail.source_system}
            className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-xs leading-5 text-zinc-800"
          >
            <strong>{formatSourceSystem(detail.source_system)}</strong> · record
            received {formatEvidenceDate(detail.latest_record_received_at)}
          </span>
        ))}
      </div>
      {compact ? null : (
        <p className="text-xs leading-5 text-zinc-500">
          Receipt dates show ingestion freshness, not when the upstream profile
          content was last edited.
        </p>
      )}
    </div>
  );
}
