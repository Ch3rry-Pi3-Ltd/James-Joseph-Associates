import { CompanyDiscoveryWorkspace } from "./company-discovery-workspace";

export default function CompanyPage() {
  return (
    <main className="min-h-screen bg-[#f7f7f2] text-zinc-950">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-8 sm:px-8 lg:px-10">
        <header className="flex flex-col gap-5 border-b border-zinc-200 pb-8 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold uppercase text-emerald-700">
              Company intelligence
            </p>
            <h1 className="mt-3 text-4xl font-semibold leading-tight text-zinc-950 sm:text-5xl">
              See who we already know at a target company
            </h1>
            <p className="mt-5 max-w-2xl text-lg leading-8 text-zinc-700">
              Search the current canonical database for candidates already tied
              to one company name, then inspect any linked jobs already landed
              in the system.
            </p>
          </div>
        </header>

        <CompanyDiscoveryWorkspace />
      </section>
    </main>
  );
}
