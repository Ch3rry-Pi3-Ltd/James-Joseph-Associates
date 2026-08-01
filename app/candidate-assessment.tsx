type AssessmentKind = "strengths" | "gaps";

type AssessmentPresentation = {
  label: string;
  emptyLabel: string;
  marker: string;
  containerClassName: string;
  countClassName: string;
  markerClassName: string;
};

function getAssessmentPresentation(
  kind: AssessmentKind,
): AssessmentPresentation {
  if (kind === "strengths") {
    return {
      label: "Evidence-backed strengths",
      emptyLabel: "No specific evidence-backed strength was returned.",
      marker: "+",
      containerClassName: "border-emerald-200 bg-emerald-50/60",
      countClassName: "bg-emerald-100 text-emerald-900",
      markerClassName: "bg-emerald-600 text-white",
    };
  }

  return {
    label: "Evidence gaps to clarify",
    emptyLabel: "No material evidence gap was identified.",
    marker: "?",
    containerClassName: "border-amber-200 bg-amber-50/60",
    countClassName: "bg-amber-100 text-amber-950",
    markerClassName: "bg-amber-500 text-amber-950",
  };
}

export function CandidateAssessmentList({
  kind,
  items,
  compact = false,
}: {
  kind: AssessmentKind;
  items: string[];
  compact?: boolean;
}) {
  const presentation = getAssessmentPresentation(kind);

  return (
    <section
      className={`rounded-md border ${compact ? "p-3" : "p-5"} ${presentation.containerClassName}`}
    >
      <div className="flex items-center justify-between gap-3">
        <h4 className="text-xs font-semibold uppercase tracking-[0.1em] text-zinc-700">
          {presentation.label}
        </h4>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-semibold ${presentation.countClassName}`}
        >
          {items.length}
        </span>
      </div>

      {items.length > 0 ? (
        <ul className={`${compact ? "mt-2 gap-2" : "mt-4 gap-3"} grid`}>
          {items.map((item, index) => (
            <li
              key={`${kind}-${index}-${item}`}
              className="grid grid-cols-[1.25rem_minmax(0,1fr)] gap-2 text-sm leading-6 text-zinc-900"
            >
              <span
                aria-hidden="true"
                className={`mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold ${presentation.markerClassName}`}
              >
                {presentation.marker}
              </span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm leading-6 text-zinc-600">
          {presentation.emptyLabel}
        </p>
      )}
    </section>
  );
}

export function CandidateStrengthsAndGaps({
  strengths,
  gaps,
}: {
  strengths: string[];
  gaps: string[];
}) {
  return (
    <section aria-label="Candidate strengths and evidence gaps">
      <div className="grid gap-4 lg:grid-cols-2">
        <CandidateAssessmentList kind="strengths" items={strengths} />
        <CandidateAssessmentList kind="gaps" items={gaps} />
      </div>
      <p className="mt-3 text-xs leading-5 text-zinc-500">
        These points are generated from the evidence supplied to ranking. Verify
        material claims against the candidate profile or CV before export.
      </p>
    </section>
  );
}
