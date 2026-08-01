type CandidateEmploymentRole = {
  employment_role_id?: string | null;
  company_id?: string | null;
  company_name: string | null;
  role_title: string | null;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
};

export type CandidateComparisonItem = {
  candidate_id: string;
  full_name: string | null;
  current_title: string | null;
  current_company_name: string | null;
  fit_score: number;
  graph_evidence: {
    skill_names: string[];
    recent_employment?: CandidateEmploymentRole[];
  } | null;
};

function formatMonthYear(value: string | null): string | null {
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
}

function formatEmploymentPeriod(role: CandidateEmploymentRole): string {
  const start = formatMonthYear(role.start_date);
  const end = role.is_current ? "Present" : formatMonthYear(role.end_date);

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

function getRecentEmployment(
  candidate: CandidateComparisonItem,
): CandidateEmploymentRole[] {
  const linkedRoles = candidate.graph_evidence?.recent_employment ?? [];
  if (linkedRoles.length > 0) {
    return linkedRoles.slice(0, 3);
  }

  if (candidate.current_title || candidate.current_company_name) {
    return [
      {
        company_name: candidate.current_company_name,
        role_title: candidate.current_title,
        start_date: null,
        end_date: null,
        is_current: true,
      },
    ];
  }

  return [];
}

export function CandidateComparison({
  candidates,
}: {
  candidates: CandidateComparisonItem[];
}) {
  if (candidates.length < 2) {
    return null;
  }

  return (
    <section
      aria-labelledby="candidate-comparison-title"
      className="rounded-md border border-emerald-200 bg-white p-5 shadow-sm sm:p-6"
    >
      <div className="flex flex-col gap-2 border-b border-zinc-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-700">
            Shortlist comparison
          </p>
          <h3
            id="candidate-comparison-title"
            className="mt-2 text-2xl font-semibold text-zinc-950"
          >
            Compare candidates side by side
          </h3>
        </div>
        <p className="max-w-xl text-sm leading-6 text-zinc-600">
          Recent canonical employment and linked skill evidence are aligned so
          differences can be scanned before opening the detailed candidate cards.
        </p>
      </div>

      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[760px] border-separate border-spacing-0 text-left">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 w-40 border-b border-r border-zinc-200 bg-zinc-50 p-4 text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                Evidence
              </th>
              {candidates.map((candidate, index) => (
                <th
                  key={`${candidate.candidate_id}-comparison-heading`}
                  className="min-w-64 border-b border-zinc-200 bg-zinc-50 p-4 align-top"
                >
                  <span className="text-xs font-semibold uppercase text-emerald-700">
                    Rank {index + 1} · Fit {candidate.fit_score}/100
                  </span>
                  <span className="mt-2 block text-lg font-semibold text-zinc-950">
                    {candidate.full_name ?? "Unnamed candidate"}
                  </span>
                  <span className="mt-1 block text-sm font-normal leading-6 text-zinc-600">
                    {candidate.current_title ?? "Title unavailable"}
                    {candidate.current_company_name
                      ? ` at ${candidate.current_company_name}`
                      : ""}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th className="sticky left-0 z-10 border-b border-r border-zinc-200 bg-white p-4 align-top text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                Recent employment
              </th>
              {candidates.map((candidate) => {
                const roles = getRecentEmployment(candidate);
                return (
                  <td
                    key={`${candidate.candidate_id}-comparison-employment`}
                    className="border-b border-zinc-200 p-4 align-top"
                  >
                    {roles.length > 0 ? (
                      <ol className="grid gap-3">
                        {roles.map((role, index) => (
                          <li
                            key={
                              role.employment_role_id ??
                              `${candidate.candidate_id}-role-${index}`
                            }
                            className="text-sm leading-6 text-zinc-800"
                          >
                            <span className="block font-semibold text-zinc-950">
                              {role.role_title ?? "Role title unavailable"}
                            </span>
                            <span className="block">
                              {role.company_name ?? "Company unavailable"}
                            </span>
                            <span className="block text-xs text-zinc-500">
                              {formatEmploymentPeriod(role)}
                            </span>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="text-sm leading-6 text-zinc-500">
                        No canonical employment history linked.
                      </p>
                    )}
                  </td>
                );
              })}
            </tr>
            <tr>
              <th className="sticky left-0 z-10 border-r border-zinc-200 bg-white p-4 align-top text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">
                Skills evidence
              </th>
              {candidates.map((candidate) => {
                const skills = candidate.graph_evidence?.skill_names ?? [];
                return (
                  <td
                    key={`${candidate.candidate_id}-comparison-skills`}
                    className="p-4 align-top"
                  >
                    {skills.length > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {skills.slice(0, 12).map((skill) => (
                          <span
                            key={`${candidate.candidate_id}-${skill}`}
                            className="rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-xs font-medium text-zinc-800"
                          >
                            {skill}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm leading-6 text-zinc-500">
                        No structured skills linked.
                      </p>
                    )}
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
