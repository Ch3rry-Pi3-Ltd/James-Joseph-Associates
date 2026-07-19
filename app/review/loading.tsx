const COUNT_CARD_TOTAL = 6;
const SECTION_CARD_TOTAL = 4;
const ROW_PLACEHOLDER_TOTAL = 3;

export default function ReviewLoading() {
  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#eef1ec_0%,#f6f6f1_40%,#fbfbf8_100%)] text-zinc-950">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-10 px-6 py-8 sm:px-8 lg:px-10">
        <header className="grid gap-6 rounded-md border border-zinc-900 bg-[#101714] px-6 py-8 text-white shadow-[0_24px_60px_rgba(15,23,42,0.18)] sm:px-8 lg:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)] lg:px-10 lg:py-10">
          <div className="max-w-4xl">
            <div className="h-4 w-32 animate-pulse rounded bg-white/10" />
            <div className="mt-4 h-12 w-full max-w-xl animate-pulse rounded bg-white/10" />
            <div className="mt-4 h-6 w-full max-w-3xl animate-pulse rounded bg-white/10" />
            <div className="mt-3 h-6 w-4/5 max-w-2xl animate-pulse rounded bg-white/10" />
          </div>

          <div className="grid content-start gap-4 rounded-md border border-white/10 bg-white/6 p-5">
            <div className="h-4 w-28 animate-pulse rounded bg-white/10" />
            <div className="h-8 w-52 animate-pulse rounded bg-white/10" />
            <div className="grid gap-3 rounded-md border border-white/10 bg-black/15 p-4">
              {Array.from({ length: 3 }).map((_, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between gap-4"
                >
                  <div className="h-4 w-28 animate-pulse rounded bg-white/10" />
                  <div className="h-4 w-20 animate-pulse rounded bg-white/10" />
                </div>
              ))}
            </div>
            <div className="h-11 w-36 animate-pulse rounded bg-white/10" />
          </div>
        </header>

        <section className="grid gap-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <div className="h-3 w-24 animate-pulse rounded bg-zinc-200" />
              <div className="mt-2 h-10 w-72 animate-pulse rounded bg-zinc-200" />
            </div>
            <div className="h-5 w-full max-w-xl animate-pulse rounded bg-zinc-100" />
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: COUNT_CARD_TOTAL }).map((_, index) => (
              <article
                key={index}
                className="relative overflow-hidden rounded-md border border-zinc-200/80 bg-white p-6 shadow-[0_18px_45px_rgba(15,23,42,0.06)]"
              >
                <div className="absolute inset-x-0 top-0 h-1 bg-zinc-200" />
                <div className="h-3 w-20 animate-pulse rounded bg-zinc-200" />
                <div className="mt-4 h-10 w-20 animate-pulse rounded bg-zinc-200" />
              </article>
            ))}
          </div>
        </section>

        {Array.from({ length: 3 }).map((_, bandIndex) => (
          <section key={bandIndex} className="grid gap-6">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <div className="h-3 w-28 animate-pulse rounded bg-zinc-200" />
                <div className="mt-2 h-10 w-80 animate-pulse rounded bg-zinc-200" />
              </div>
              <div className="h-5 w-full max-w-xl animate-pulse rounded bg-zinc-100" />
            </div>

            <div className="grid gap-6 xl:grid-cols-2">
              {Array.from({ length: SECTION_CARD_TOTAL }).map((__, cardIndex) => (
                <article
                  key={cardIndex}
                  className="grid gap-5 rounded-md border border-zinc-200/80 bg-white p-6 shadow-[0_18px_45px_rgba(15,23,42,0.06)]"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3 border-b border-zinc-200/80 pb-4">
                    <div className="max-w-2xl">
                      <div className="h-3 w-20 animate-pulse rounded bg-zinc-200" />
                      <div className="mt-2 h-8 w-56 animate-pulse rounded bg-zinc-200" />
                      <div className="mt-2 h-5 w-full max-w-md animate-pulse rounded bg-zinc-100" />
                    </div>
                    <div className="h-8 w-16 animate-pulse rounded bg-emerald-100" />
                  </div>

                  <div className="grid gap-3">
                    {Array.from({ length: ROW_PLACEHOLDER_TOTAL }).map(
                      (___, rowIndex) => (
                        <div
                          key={rowIndex}
                          className="rounded-md border border-zinc-200/80 bg-[linear-gradient(180deg,#ffffff_0%,#f7f8f7_100%)] p-4 shadow-[0_12px_30px_rgba(15,23,42,0.05)]"
                        >
                          <div className="grid gap-2">
                            <div className="h-3 w-28 animate-pulse rounded bg-zinc-200" />
                            <div className="h-4 w-full animate-pulse rounded bg-zinc-100" />
                            <div className="h-4 w-5/6 animate-pulse rounded bg-zinc-100" />
                          </div>
                        </div>
                      ),
                    )}
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))}
      </section>
    </main>
  );
}
