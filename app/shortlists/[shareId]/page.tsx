import Link from "next/link";

import { requireAuthorizedUser } from "@/lib/auth";

import { SharedShortlistWorkspace } from "./shared-shortlist-workspace";

export default async function SharedShortlistPage({
  params,
}: {
  params: Promise<{ shareId: string }>;
}) {
  await requireAuthorizedUser();
  const { shareId } = await params;

  return (
    <main className="min-h-screen bg-[linear-gradient(180deg,#edf2ef_0%,#f7f8f5_42%,#fbfbf8_100%)] text-zinc-950">
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-7 px-6 py-8 sm:px-8 lg:px-10">
        <header className="workspace-hero">
          <div className="grid gap-8 px-6 py-8 sm:px-8 lg:grid-cols-[minmax(0,1.25fr)_minmax(280px,0.75fr)] lg:px-10 lg:py-10">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-emerald-300">
                Secure shortlist
              </p>
              <h1 className="mt-4 text-4xl font-semibold leading-tight sm:text-5xl">
                Recruiter review package
              </h1>
              <p className="mt-5 max-w-3xl text-lg leading-8 text-zinc-200">
                A saved snapshot of the ranked candidates, supporting evidence,
                strengths, gaps, and canonical CV routes for one role.
              </p>
            </div>

            <aside className="workspace-card-contrast grid content-start gap-4 p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-300">
                Access control
              </p>
              <p className="text-xl font-semibold text-white">
                Approved workspace accounts only
              </p>
              <p className="text-sm leading-6 text-zinc-200">
                This link is protected by Clerk, expires automatically, and can
                be revoked by the operator who created it.
              </p>
              <Link
                href="/match"
                className="inline-flex h-10 w-fit items-center justify-center rounded-md bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:bg-emerald-50"
              >
                Return to matching
              </Link>
            </aside>
          </div>
        </header>

        <SharedShortlistWorkspace shareId={shareId} />
      </section>
    </main>
  );
}
