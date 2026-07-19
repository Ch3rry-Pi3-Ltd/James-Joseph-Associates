import "server-only";

import { auth, currentUser } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

type AuthorizedUser = {
  userId: string;
  emailAddress: string | null;
};

function getAllowedEmails(): Set<string> {
  const rawValue = process.env.CLERK_ALLOWED_EMAILS?.trim();

  if (!rawValue) {
    return new Set<string>();
  }

  return new Set(
    rawValue
      .split(",")
      .map((value) => value.trim().toLowerCase())
      .filter((value) => value.length > 0),
  );
}

function getPrimaryEmailAddress(
  user: Awaited<ReturnType<typeof currentUser>>,
): string | null {
  if (!user) {
    return null;
  }

  return (
    user.primaryEmailAddress?.emailAddress ??
    user.emailAddresses.find(
      (emailAddress) => emailAddress.id === user.primaryEmailAddressId,
    )?.emailAddress ??
    user.emailAddresses[0]?.emailAddress ??
    null
  );
}

export async function requireAuthorizedUser(): Promise<AuthorizedUser> {
  const { userId } = await auth();

  if (!userId) {
    redirect("/sign-in");
  }

  const allowedEmails = getAllowedEmails();

  if (allowedEmails.size === 0) {
    return {
      userId,
      emailAddress: null,
    };
  }

  const user = await currentUser();
  const emailAddress = getPrimaryEmailAddress(user)?.toLowerCase() ?? null;

  if (!emailAddress || !allowedEmails.has(emailAddress)) {
    redirect("/unauthorized");
  }

  return {
    userId,
    emailAddress,
  };
}
