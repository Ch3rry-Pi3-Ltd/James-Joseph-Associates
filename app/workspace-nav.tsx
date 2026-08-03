"use client";

import { ClerkLoaded, ClerkLoading, UserButton, useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { usePathname } from "next/navigation";

const navigationItems = [
  { href: "/", label: "Home" },
  { href: "/review", label: "Review" },
  { href: "/company", label: "Company" },
  { href: "/match", label: "Match" },
];

function isActivePath(pathname: string, href: string): boolean {
  return href === "/"
    ? pathname === "/"
    : pathname === href || pathname.startsWith(`${href}/`);
}

export function WorkspaceNav() {
  const pathname = usePathname();
  const { userId } = useAuth();

  return (
    <header className="sticky top-0 z-50 border-b border-slate-950/10 bg-[#fbfaf7]/95 text-[#071b2a] shadow-[0_10px_35px_rgba(7,27,42,0.06)] backdrop-blur-xl">
      <div className="bg-[#071827] text-white">
        <div className="mx-auto flex min-h-8 w-full max-w-7xl items-center justify-between gap-4 px-6 text-[11px] font-semibold tracking-[0.05em] sm:px-8 lg:px-10">
          <span>Recruitment intelligence, grounded in evidence.</span>
          <span className="hidden text-cyan-200 sm:inline">
            Restricted operator workspace
          </span>
        </div>
      </div>

      <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4 sm:px-8 lg:px-10">
        <Link href="/" className="group flex items-center gap-3" aria-label="JJA workspace home">
          <span className="grid h-12 w-12 place-items-center rounded-[1.05rem] bg-[linear-gradient(145deg,#0d6b6d,#2859e8)] text-xs font-extrabold tracking-[0.12em] text-white shadow-[0_12px_28px_rgba(40,89,232,0.2)] transition group-hover:-translate-y-0.5">
            JJA
          </span>
          <span className="hidden sm:block">
            <span className="block text-base font-bold leading-tight tracking-[-0.02em]">
              James Joseph Associates
            </span>
            <span className="mt-0.5 block text-[10px] font-bold uppercase tracking-[0.19em] text-[#0d6b6d]">
              Recruitment intelligence
            </span>
          </span>
        </Link>

        <nav aria-label="Primary" className="order-3 grid w-full min-w-0 basis-full grid-cols-4 gap-1 rounded-full border border-slate-900/10 bg-white/72 p-1.5 shadow-sm lg:order-none lg:flex lg:w-auto lg:basis-auto lg:items-center lg:justify-center">
          {navigationItems.map((item) => {
            const isActive = isActivePath(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`inline-flex min-h-10 min-w-0 items-center justify-center rounded-full px-2 text-xs font-semibold transition sm:px-4 sm:text-sm ${
                  isActive
                    ? "bg-[#071827] text-white shadow-md"
                    : "text-slate-600 hover:bg-cyan-50 hover:text-[#071b2a]"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-3">
          <ClerkLoading>
            <div className="h-11 w-11 rounded-full border border-slate-200 bg-slate-100" />
          </ClerkLoading>
          <ClerkLoaded>
            {userId ? (
              <>
                <span className="hidden text-right xl:block">
                  <span className="block text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">
                    Workspace
                  </span>
                  <span className="block text-sm font-semibold text-slate-700">
                    Secure access
                  </span>
                </span>
                <UserButton
                  appearance={{ elements: { userButtonAvatarBox: "h-11 w-11" } }}
                />
              </>
            ) : (
              <Link href="/sign-in" className="app-primary-action min-h-11 px-4 sm:px-5">
                Sign in <span aria-hidden="true">→</span>
              </Link>
            )}
          </ClerkLoaded>
        </div>
      </div>
    </header>
  );
}
