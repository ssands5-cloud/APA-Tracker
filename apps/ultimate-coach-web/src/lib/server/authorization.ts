import 'server-only';
import { auth, clerkClient } from '@clerk/nextjs/server';
import { authConfigured } from '../auth-config';
import { isAuthorized } from '../access-policy';

export type AccessResult = { ok: true; scope: 'historical-pilot' } | { ok: false; reason: 'anonymous' | 'denied' | 'unavailable' };

export async function historicalAccess(): Promise<AccessResult> {
  if (!authConfigured()) return { ok: false, reason: 'unavailable' };
  try {
    const { userId, sessionId } = await auth();
    if (!userId || !sessionId) return { ok: false, reason: 'anonymous' };
    const client = await clerkClient();
    // Fresh provider reads: a valid cached JWT alone does not override session/account revocation.
    const [session, user] = await Promise.all([client.sessions.getSession(sessionId), client.users.getUser(userId)]);
    const allowed = (process.env.UC_AUTHORIZED_EMAILS ?? '').split(',');
    const permitted = isAuthorized({ userId, sessionUserId: session.userId, sessionStatus: session.status,
      banned: user.banned, locked: user.locked,
      emails: user.emailAddresses.map(email => ({ address: email.emailAddress, verified: email.verification?.status === 'verified' })) }, allowed);
    return permitted ? { ok: true, scope: 'historical-pilot' } : { ok: false, reason: 'denied' };
  } catch {
    // No provider error bodies, identity data, credentials or tokens go into logs/responses.
    return { ok: false, reason: 'unavailable' };
  }
}
