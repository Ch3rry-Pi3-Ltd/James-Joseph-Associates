"use client";

import { ClerkLoaded, ClerkLoading, UserButton, useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { usePathname } from "next/navigation";

type NavigationItem = {
  href: string;
  label: string;
};

const navigationItems: NavigationItem[] = [
  { href: "/", label: "Home" },
  { href: "/review", label: "Review" },
  { href: "/company", label: "Company" },
  { href: "/match", label: "Match" },
];

function isActivePath(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }

  return pathname === href || pathname.startsWith(`${href}/`);
}

export function WorkspaceNav() {
  const pathname = usePathname();
  const { userId } = useAuth();

  return (
    <div className="border-b border-zinc-800 bg-[#101714] text-zinc-50">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-4 px-6 py-4 sm:px-8 lg:px-10">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <div className="grid h-11 w-11 place-items-center rounded-md border border-emerald-400/30 bg-emerald-400/10 text-sm font-semibold text-emerald-200">
              RI
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-300">
                Recruitment intelligence
              </p>
              <p className="text-sm text-zinc-300">
                Canonical search and workflow platform
              </p>
            </div>
          </div>

          <div className="grid gap-1 text-sm text-zinc-400 sm:text-right">
            <p>Canonical data, retrieval, review, and workflow execution</p>
            <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">
              Restricted operator workspace
            </p>
          </div>
        </div>

        <nav
          aria-label="Primary"
          className="flex flex-col gap-3 rounded-md border border-zinc-800 bg-[#161f1b] p-2 md:flex-row md:items-center md:justify-between"
        >
          <div className="flex flex-wrap gap-2">
            {navigationItems.map((item) => {
              const isActive = isActivePath(pathname, item.href);

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`inline-flex h-10 items-center justify-center rounded-md px-4 text-sm font-semibold transition ${
                    isActive
                      ? "bg-white text-zinc-950 shadow-sm"
                      : "text-zinc-300 hover:bg-zinc-800 hover:text-white"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>

          <div className="flex items-center gap-3">
            <ClerkLoading>
              <div className="h-10 w-10 rounded-full border border-zinc-700 bg-zinc-900/60" />
            </ClerkLoading>

            <ClerkLoaded>
              {userId ? (
                <>
                  <div className="hidden text-right md:block">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                      Auth
                    </p>
                    <p className="text-sm text-zinc-300">Restricted access</p>
                  </div>
                  <UserButton
                    appearance={{
                      elements: {
                        userButtonAvatarBox: "h-10 w-10",
                      },
                    }}
                  />
                </>
              ) : (
                <Link
                  href="/sign-in"
                  className="inline-flex h-10 items-center justify-center rounded-md border border-zinc-700 px-4 text-sm font-semibold text-zinc-200 transition hover:bg-zinc-800 hover:text-white"
                >
                  Sign in
                </Link>
              )}
            </ClerkLoaded>
          </div>
        </nav>
      </div>
    </div>
  );
}
