import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isPublicRoute = createRouteMatcher([
  "/sign-in(.*)",
  "/unauthorized(.*)",
  "/api/v1/health",
]);
const isApiRoute = createRouteMatcher(["/(api|trpc)(.*)"]);

export default clerkMiddleware(async (auth, request) => {
  if (isApiRoute(request) && !isPublicRoute(request)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
