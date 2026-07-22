type ClerkEmailAddress = {
  id?: string;
  emailAddress: string;
};

type ClerkUserLike = {
  primaryEmailAddress?: ClerkEmailAddress | null;
  primaryEmailAddressId?: string | null;
  emailAddresses: readonly ClerkEmailAddress[];
};

export function getAllowedEmails(rawValue = process.env.CLERK_ALLOWED_EMAILS): Set<string> {
  if (!rawValue?.trim()) {
    return new Set<string>();
  }

  return new Set(
    rawValue
      .split(",")
      .map((value) => value.trim().toLowerCase())
      .filter((value) => value.length > 0),
  );
}

export function getPrimaryEmailAddress(user: ClerkUserLike | null): string | null {
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

export function isProductionEnvironment(): boolean {
  return (
    process.env.VERCEL_ENV === "production" ||
    (!process.env.VERCEL_ENV && process.env.NODE_ENV === "production")
  );
}

export function isAuthorizedEmail(
  emailAddress: string | null,
  allowedEmails = getAllowedEmails(),
): boolean {
  if (allowedEmails.size === 0) {
    return !isProductionEnvironment();
  }

  return Boolean(emailAddress && allowedEmails.has(emailAddress.toLowerCase()));
}
