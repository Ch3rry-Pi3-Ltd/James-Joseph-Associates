import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <main className="min-h-screen bg-[#0b1110] px-6 py-10 text-zinc-50 sm:px-8 lg:px-10">
      <section className="mx-auto grid w-full max-w-6xl gap-8 lg:grid-cols-[minmax(0,1.1fr)_420px]">
        <div className="grid content-start gap-6 rounded-md border border-white/10 bg-[#101714] p-8 shadow-2xl">
          <div className="inline-flex w-fit rounded-md border border-emerald-400/25 bg-emerald-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-emerald-300">
            Secure access
          </div>

          <div className="max-w-3xl">
            <h1 className="text-4xl font-semibold leading-tight text-white sm:text-5xl">
              Sign in to the recruitment intelligence workspace
            </h1>
            <p className="mt-5 text-lg leading-8 text-zinc-300">
              This app is restricted to approved operator email addresses. Once
              signed in, the existing Review, Company, and Match surfaces stay
              behind Clerk authentication.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-md border border-white/10 bg-white/5 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-400">
                Review
              </p>
              <p className="mt-2 text-sm leading-6 text-zinc-200">
                Inspect canonical records, documents, and source provenance.
              </p>
            </div>
            <div className="rounded-md border border-white/10 bg-white/5 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-400">
                Company
              </p>
              <p className="mt-2 text-sm leading-6 text-zinc-200">
                Surface linked contacts, candidates, jobs, and opportunities.
              </p>
            </div>
            <div className="rounded-md border border-white/10 bg-white/5 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-400">
                Match
              </p>
              <p className="mt-2 text-sm leading-6 text-zinc-200">
                Search the corpus and produce evidence-backed shortlists.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-start justify-center rounded-md border border-white/10 bg-white p-4 shadow-2xl">
          <SignIn
            routing="path"
            path="/sign-in"
            forceRedirectUrl="/"
            fallbackRedirectUrl="/"
          />
        </div>
      </section>
    </main>
  );
}
