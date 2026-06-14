"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavigationItem = {
  href: string;
  label: string;
};

const navigationItems: NavigationItem[] = [
  { href: "/", label: "Home" },
  { href: "/review", label: "Review" },
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

  return (
    <div className="border-b border-zinc-200 bg-[#f7f7f2]">
      <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-6 py-4 sm:px-8 lg:px-10">
        <div>
          <p className="text-xs font-semibold uppercase text-emerald-700">
            James Joseph Associates
          </p>
          <p className="text-sm text-zinc-600">Recruitment intelligence</p>
        </div>

        <nav aria-label="Primary" className="flex flex-wrap gap-2">
          {navigationItems.map((item) => {
            const isActive = isActivePath(pathname, item.href);

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`inline-flex h-10 items-center justify-center rounded-md border px-4 text-sm font-semibold transition ${
                  isActive
                    ? "border-zinc-950 bg-zinc-950 text-white"
                    : "border-zinc-300 bg-white text-zinc-950 hover:border-zinc-500"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
