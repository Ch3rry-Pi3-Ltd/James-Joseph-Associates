import { CompanyDiscoveryWorkspace } from "./company-discovery-workspace";

export default function CompanyPage() {
  return (
    <main className="min-h-screen bg-[#eef1ec] text-zinc-950">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-8 sm:px-8 lg:px-10">
        <header className="overflow-hidden rounded-md border border-zinc-900 bg-[#101714] text-white shadow-sm">
          <div className="grid gap-6 px-6 py-8 sm:px-8 lg:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.9fr)] lg:px-10 lg:py-10">
            <div className="max-w-4xl">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-emerald-300">
                Company intelligence
              </p>
              <h1 className="mt-4 text-4xl font-semibold leading-tight sm:text-5xl">
                Surface who we know at a target company
              </h1>
              <p className="mt-5 max-w-3xl text-lg leading-8 text-zinc-200">
                Search one firm name and inspect linked candidates, contacts,
                jobs, interactions, and opportunities already landed in the
                canonical database.
              </p>
            </div>

            <aside className="grid gap-4 rounded-md border border-white/10 bg-white/6 p-5">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-300">
                  Current use
                </p>
                <p className="mt-2 text-2xl font-semibold text-white">
                  Company-first relationship lookup
                </p>
              </div>
              <p className="text-sm leading-6 text-zinc-200">
                Use this tab when the starting point is a firm, not a person or
                a role brief.
              </p>
            </aside>
          </div>
        </header>

        <CompanyDiscoveryWorkspace />
      </section>
    </main>
  );
}
