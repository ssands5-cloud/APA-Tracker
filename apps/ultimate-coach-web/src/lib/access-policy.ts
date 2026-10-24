/** Pure policy, shared by server authorization and negative tests. No browser/session trust. */
export type VerifiedIdentity = {
  userId: string; sessionUserId: string; sessionStatus: string; banned: boolean; locked: boolean;
  emails: { address: string; verified: boolean }[];
};
export function isAuthorized(identity: VerifiedIdentity | null, allowedEmails: string[]): boolean {
  if (!identity || !identity.userId || identity.sessionStatus !== 'active'
      || identity.sessionUserId !== identity.userId || identity.banned || identity.locked) return false;
  const allowed = new Set(allowedEmails.map(email => email.trim().toLowerCase()).filter(Boolean));
  return identity.emails.some(email => email.verified && allowed.has(email.address.trim().toLowerCase()));
}
