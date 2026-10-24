import 'server-only';
import { execute } from './client';

export type AdminAction = 'approve' | 'deny' | 'promote' | 'demote' | 'suspend' | 'remove' | 'bootstrap' | 'admin_sign_in';

export interface AuditEntry {
  id: number;
  actor_id: string;
  actor_email: string | null;
  action: AdminAction;
  target_id: string | null;
  target_email: string | null;
  old_role: string | null;
  new_role: string | null;
  note: string | null;
  created_at: string;
}

export async function appendAuditLog(
  actorId: string,
  action: AdminAction,
  targetId?: string | null,
  oldRole?: string | null,
  newRole?: string | null,
  note?: string | null,
): Promise<void> {
  await execute(
    "INSERT INTO audit_log (actor_id, action, target_id, old_role, new_role, note, created_at) VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))",
    [actorId, action, targetId ?? null, oldRole ?? null, newRole ?? null, note ?? null],
  );
}

export async function listAuditLog(limit = 50): Promise<AuditEntry[]> {
  const rows = await execute(
    `SELECT a.id, a.actor_id, u1.email AS actor_email, a.action, a.target_id, u2.email AS target_email,
            a.old_role, a.new_role, a.note, a.created_at
     FROM audit_log a
     LEFT JOIN users u1 ON u1.id = a.actor_id
     LEFT JOIN users u2 ON u2.id = a.target_id
     ORDER BY a.id DESC LIMIT ?`,
    [limit],
  );
  return rows as unknown as AuditEntry[];
}
