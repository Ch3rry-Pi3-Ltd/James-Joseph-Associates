import "server-only";

import { auth, currentUser } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import {
  getAllowedEmails,
  getPrimaryEmailAddress,
  isAuthorizedEmail,
} from "./auth-policy";

type AuthorizedUser = {
  userId: string;
  emailAddress: string | null;
};

export async function requireAuthorizedUser(): Promise<AuthorizedUser> {
  const { userId } = await auth();

  if (!userId) {
    redirect("/sign-in");
  }

  const allowedEmails = getAllowedEmails();

  if (allowedEmails.size === 0 && isAuthorizedEmail(null, allowedEmails)) {
    return {
      userId,
      emailAddress: null,
    };
  }

  const user = await currentUser();
  const emailAddress = getPrimaryEmailAddress(user)?.toLowerCase() ?? null;

  if (!isAuthorizedEmail(emailAddress, allowedEmails)) {
    redirect("/unauthorized");
  }

  return {
    userId,
    emailAddress,
  };
}
