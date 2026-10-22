import 'server-only';
import { auth, clerkClient } from '@clerk/nextjs/server';
import { authConfigured } from '../auth-config';
import { getUser, getUserByEmail, createUser, activateBootstrap, activatePreseed, type Role } from '../db/users';
import { appendAuditLog } from '../db/audit';
import { logActivity } from '../db/activity';

export type AccessResult =
  | { ok: true; scope: 'historical-pilot'; role: Role; userId: string }
  | { ok: false; reason: 'anonymous' | 'denied' | 'unavailable' };

export async function historicalAccess(): Promise<AccessResult> {
  if (!authConfigured()) return { ok: false, reason: 'unavailable' };
  try {
    const { userId, sessionId } = await auth();
    if (!userId || !sessionId) return { ok: false, reason: 'anonymous' };

    const client = await clerkClient();
    // Fresh provider reads: cached JWT alone does not override session or account revocation.
    const [session, clerkUser] = await Promise.all([
      client.sessions.getSession(sessionId),
      client.users.getUser(userId),
    ]);

    if (
      session.userId !== userId ||
      session.status !== 'active' ||
      clerkUser.banned ||
      clerkUser.locked
    ) {
      return { ok: false, reason: 'denied' };
    }

    const primaryEmail =
      clerkUser.emailAddresses.find(e => e.verification?.status === 'verified')?.emailAddress ?? '';

    let user = await getUser(userId);

    if (!user) {
      // First sign-in for this Clerk identity.
      const byEmail = await getUserByEmail(primaryEmail);
      if (byEmail?.id === 'bootstrap-seed') {
        // Activate the seeded admin record.
        const displayName = [clerkUser.firstName, clerkUser.lastName].filter(Boolean).join(' ') || null;
        await activateBootstrap(userId, primaryEmail, displayName);
        await appendAuditLog(userId, 'bootstrap', userId, null, 'ADMIN', 'Seed admin activated');
        await logActivity(userId, 'sign_in', { bootstrap: true });
        user = await getUser(userId);
      } else if (byEmail?.id.startsWith('preseed-') && byEmail.role !== 'PENDING' && byEmail.role !== 'SUSPENDED') {
        // Pre-authorized user: an admin seeded this email with a role before sign-up.
        // Activate the placeholder by replacing the preseed id with the real Clerk id.
        const displayName = [clerkUser.firstName, clerkUser.lastName].filter(Boolean).join(' ') || null;
        await activatePreseed(byEmail.id, userId, displayName);
        await appendAuditLog(userId, 'bootstrap', userId, null, byEmail.role, `Pre-seed activated: ${byEmail.id}`);
        await logActivity(userId, 'sign_in', { preseed: true, role: byEmail.role });
        user = await getUser(userId);
      } else {
        // New user — register as PENDING; no access until an admin approves.
        const displayName = [clerkUser.firstName, clerkUser.lastName].filter(Boolean).join(' ') || null;
        await createUser(userId, primaryEmail, 'PENDING', displayName);
        return { ok: false, reason: 'denied' };
      }
    }

    if (!user || user.role === 'PENDING' || user.role === 'SUSPENDED') {
      return { ok: false, reason: 'denied' };
    }

    // Log sign-in; log admin sign-ins to the audit trail too.
    await logActivity(userId, 'sign_in', { role: user.role });
    if (user.role === 'ADMIN') {
      await appendAuditLog(userId, 'admin_sign_in', userId, null, null, null);
    }

    return { ok: true, scope: 'historical-pilot', role: user.role, userId };
  } catch {
    // No provider error bodies, identity data, credentials or tokens go into logs or responses.
    return { ok: false, reason: 'unavailable' };
  }
}
