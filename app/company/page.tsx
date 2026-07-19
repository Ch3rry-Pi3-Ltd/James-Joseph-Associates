import { CompanyDiscoveryWorkspace } from "./company-discovery-workspace";
import { requireAuthorizedUser } from "@/lib/auth";

type CompanyPageProps = {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export default async function CompanyPage({
  searchParams,
}: CompanyPageProps) {
  await requireAuthorizedUser();
  const resolvedSearchParams = await searchParams;
  const requestedCompany = resolvedSearchParams.company;
  const initialCompanyName =
    typeof requestedCompany === "string" ? requestedCompany : null;

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#eef1ec_0%,#f6f6f1_40%,#fbfbf8_100%)] text-zinc-950">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-8 sm:px-8 lg:px-10">
        <header className="workspace-hero">
          <div className="grid gap-8 px-6 py-8 sm:px-8 lg:grid-cols-[minmax(0,1.2fr)_minmax(340px,0.8fr)] lg:px-10 lg:py-10">
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

              <div className="mt-8 grid gap-4 sm:grid-cols-3">
                <div className="workspace-card-contrast p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-200">
                    Candidates
                  </p>
                  <p className="mt-3 text-sm leading-6 text-zinc-100">
                    Current-employer matches plus resume mentions.
                  </p>
                </div>
                <div className="workspace-card-contrast p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-200">
                    Contacts
                  </p>
                  <p className="mt-3 text-sm leading-6 text-zinc-100">
                    Hiring managers, linked people, and prior warm routes.
                  </p>
                </div>
                <div className="workspace-card-contrast p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-200">
                    Jobs
                  </p>
                  <p className="mt-3 text-sm leading-6 text-zinc-100">
                    Open roles and opportunities already tied to the firm.
                  </p>
                </div>
              </div>
            </div>

            <aside className="grid gap-4 rounded-md border border-white/10 bg-white/6 p-5 backdrop-blur-sm">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-300">
                  Current use
                </p>
                <p className="mt-2 text-2xl font-semibold text-white">
                  Company-first relationship lookup
                </p>
              </div>
              <div className="grid gap-3 rounded-md border border-white/10 bg-black/15 p-4">
                <div className="flex items-center justify-between gap-3 text-sm text-zinc-200">
                  <span>Starting point</span>
                  <span className="font-semibold text-white">Target firm</span>
                </div>
                <div className="flex items-center justify-between gap-3 text-sm text-zinc-200">
                  <span>Operator mode</span>
                  <span className="font-semibold text-white">Relationship scan</span>
                </div>
                <div className="flex items-center justify-between gap-3 text-sm text-zinc-200">
                  <span>Evidence returned</span>
                  <span className="font-semibold text-white">People + jobs</span>
                </div>
              </div>
              <p className="text-sm leading-6 text-zinc-200">
                Use this tab when the starting point is a firm, not a person or
                a role brief.
              </p>
            </aside>
          </div>
        </header>

        <CompanyDiscoveryWorkspace initialCompanyName={initialCompanyName} />
      </section>
    </main>
  );
}
