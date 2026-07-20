type UsageGuideStep = {
  title: string;
  body: string;
};

type UsageGuideProps = {
  eyebrow: string;
  title: string;
  intro: string;
  steps: UsageGuideStep[];
  tip?: string;
};

export function UsageGuide({
  eyebrow,
  title,
  intro,
  steps,
  tip,
}: UsageGuideProps) {
  return (
    <details className="rounded-md border border-zinc-200/80 bg-white shadow-[0_18px_40px_rgba(15,23,42,0.06)]">
      <summary className="cursor-pointer list-none px-6 py-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-600">
              {eyebrow}
            </p>
            <h2 className="mt-2 text-2xl font-semibold leading-tight text-zinc-950">
              {title}
            </h2>
            <p className="mt-3 text-sm leading-7 text-zinc-600">{intro}</p>
          </div>

          <span className="inline-flex h-10 shrink-0 items-center justify-center rounded-md border border-zinc-200 bg-zinc-50 px-4 text-sm font-semibold text-zinc-900">
            Open guide
          </span>
        </div>
      </summary>

      <div className="border-t border-zinc-200/80 px-6 py-6">
        <div className="grid gap-4 lg:grid-cols-3">
          {steps.map((step, index) => (
            <article
              key={`${step.title}-${index}`}
              className="rounded-md border border-zinc-200 bg-[linear-gradient(180deg,#ffffff_0%,#f7faf8_100%)] p-4"
            >
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-400">
                Step {index + 1}
              </p>
              <h3 className="mt-2 text-lg font-semibold text-zinc-950">
                {step.title}
              </h3>
              <p className="mt-3 text-sm leading-7 text-zinc-700">{step.body}</p>
            </article>
          ))}
        </div>

        {tip ? (
          <div className="mt-5 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm leading-7 text-emerald-950">
            {tip}
          </div>
        ) : null}
      </div>
    </details>
  );
}
