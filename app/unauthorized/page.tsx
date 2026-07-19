import Link from "next/link";

export default function UnauthorizedPage() {
  return (
    <main className="min-h-screen bg-[#0b1110] px-6 py-10 text-zinc-50 sm:px-8 lg:px-10">
      <section className="mx-auto grid w-full max-w-3xl gap-6 rounded-md border border-white/10 bg-[#101714] p-8 shadow-2xl">
        <div className="inline-flex w-fit rounded-md border border-amber-400/25 bg-amber-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-amber-300">
          Access blocked
        </div>

        <div>
          <h1 className="text-4xl font-semibold text-white">
            This email address is not allowed into the workspace
          </h1>
          <p className="mt-4 text-lg leading-8 text-zinc-300">
            Clerk authentication is live, but this deployment is still limited
            to the approved operator list configured in the environment.
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <Link
            href="/sign-in"
            className="inline-flex h-11 items-center justify-center rounded-md bg-white px-4 text-sm font-semibold text-zinc-950 transition hover:bg-zinc-200"
          >
            Back to sign-in
          </Link>
          <Link
            href="/"
            className="inline-flex h-11 items-center justify-center rounded-md border border-white/15 px-4 text-sm font-semibold text-white transition hover:bg-white/8"
          >
            Return to workspace
          </Link>
        </div>
      </section>
    </main>
  );
}
