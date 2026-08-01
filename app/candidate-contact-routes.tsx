"use client";

import { useState } from "react";

type ContactRoute = {
  key: "email" | "phone" | "linkedin";
  label: string;
  value: string;
  actionLabel: string;
  href: string;
  external?: boolean;
};

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "No contact date recorded";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

function normalizeLinkedInUrl(value: string): string {
  const trimmedValue = value.trim();
  if (/^https?:\/\//i.test(trimmedValue)) {
    return trimmedValue;
  }
  return `https://${trimmedValue}`;
}

function normalizePhoneHref(value: string): string {
  return value.trim().replace(/(?!^)\+|[^\d+]/g, "");
}

export function CandidateContactRoutes({
  candidateId,
  primaryEmail,
  primaryPhone,
  linkedinUrl,
  lastContactedAt,
}: {
  candidateId: string;
  primaryEmail: string | null;
  primaryPhone: string | null;
  linkedinUrl: string | null;
  lastContactedAt: string | null;
}) {
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const routes: ContactRoute[] = [];

  if (primaryEmail?.trim()) {
    routes.push({
      key: "email",
      label: "Email",
      value: primaryEmail.trim(),
      actionLabel: "Start email",
      href: `mailto:${primaryEmail.trim()}`,
    });
  }

  if (primaryPhone?.trim()) {
    routes.push({
      key: "phone",
      label: "Phone",
      value: primaryPhone.trim(),
      actionLabel: "Call candidate",
      href: `tel:${normalizePhoneHref(primaryPhone)}`,
    });
  }

  if (linkedinUrl?.trim()) {
    routes.push({
      key: "linkedin",
      label: "LinkedIn",
      value: linkedinUrl.trim(),
      actionLabel: "Open profile",
      href: normalizeLinkedInUrl(linkedinUrl),
      external: true,
    });
  }

  async function copyRoute(route: ContactRoute) {
    try {
      await navigator.clipboard.writeText(route.value);
      setCopyMessage(`${route.label} copied.`);
    } catch {
      setCopyMessage(`${route.label} could not be copied.`);
    }
  }

  const headingId = `candidate-${candidateId}-contact-routes`;

  return (
    <section
      aria-labelledby={headingId}
      className="rounded-md border border-sky-200 bg-sky-50/50 p-5"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-sky-800">
            Private candidate details
          </p>
          <h4 id={headingId} className="mt-1 text-lg font-semibold text-zinc-950">
            Contact routes
          </h4>
        </div>
        <p className="text-sm text-zinc-600">
          Last contacted: {formatTimestamp(lastContactedAt)}
        </p>
      </div>

      {routes.length > 0 ? (
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          {routes.map((route) => (
            <article
              key={route.key}
              className="grid content-between gap-4 rounded-md border border-zinc-200 bg-white p-4"
            >
              <div>
                <p className="text-xs font-semibold uppercase text-zinc-500">
                  {route.label}
                </p>
                <p className="mt-1 break-all text-sm leading-6 text-zinc-900">
                  {route.value}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <a
                  href={route.href}
                  target={route.external ? "_blank" : undefined}
                  rel={route.external ? "noreferrer" : undefined}
                  className="inline-flex h-9 items-center justify-center rounded-md bg-zinc-950 px-3 text-xs font-semibold text-white transition hover:bg-emerald-900"
                >
                  {route.actionLabel}
                </a>
                <button
                  type="button"
                  onClick={() => void copyRoute(route)}
                  className="inline-flex h-9 items-center justify-center rounded-md border border-zinc-300 bg-white px-3 text-xs font-semibold text-zinc-900 transition hover:border-zinc-500"
                >
                  Copy
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
          No email address, phone number, or LinkedIn route is recorded for this
          candidate.
        </p>
      )}

      <div className="mt-4 flex flex-col gap-1 text-xs leading-5 text-zinc-600 sm:flex-row sm:items-center sm:justify-between">
        <p>Contact details stay in the signed-in preview and are not added to shared shortlists.</p>
        <p aria-live="polite">{copyMessage}</p>
      </div>
    </section>
  );
}
