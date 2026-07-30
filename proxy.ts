import {
  clerkClient,
  clerkMiddleware,
  createRouteMatcher,
} from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

import {
  getAllowedEmails,
  getPrimaryEmailAddress,
  isAuthorizedEmail,
} from "./lib/auth-policy";

const isPublicRoute = createRouteMatcher([
  "/sign-in(.*)",
  "/unauthorized(.*)",
  "/api/v1/health",
]);
const isApiRoute = createRouteMatcher(["/(api|trpc)(.*)"]);
const isBearerProtectedBackendRoute = createRouteMatcher([
  "/api/v1/make(.*)",
  "/api/v1/operator(.*)",
]);

function apiAccessError(status: number, code: string, message: string) {
  return NextResponse.json(
    {
      error: {
        code,
        message,
        details: [],
      },
    },
    { status },
  );
}

export default clerkMiddleware(async (auth, request) => {
  if (
    !isApiRoute(request) ||
    isPublicRoute(request) ||
    isBearerProtectedBackendRoute(request)
  ) {
    return;
  }

  await auth.protect();
  const { userId } = await auth();
  if (!userId) {
    return apiAccessError(401, "unauthorized", "Authentication is required.");
  }

  const allowedEmails = getAllowedEmails();
  if (allowedEmails.size === 0 && !isAuthorizedEmail(null, allowedEmails)) {
    return apiAccessError(
      503,
      "authorization_not_configured",
      "API access is not configured.",
    );
  }

  try {
    const client = await clerkClient();
    const user = await client.users.getUser(userId);
    const emailAddress = getPrimaryEmailAddress(user)?.toLowerCase() ?? null;

    if (
      allowedEmails.size > 0 &&
      !isAuthorizedEmail(emailAddress, allowedEmails)
    ) {
      return apiAccessError(403, "forbidden", "This account is not authorized.");
    }

    const requestHeaders = new Headers(request.headers);
    requestHeaders.set("x-workspace-user-id", userId);
    requestHeaders.set("x-workspace-user-email", emailAddress ?? "");

    return NextResponse.next({
      request: {
        headers: requestHeaders,
      },
    });
  } catch {
    return apiAccessError(
      503,
      "authorization_unavailable",
      "Authorization could not be verified.",
    );
  }
});

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
