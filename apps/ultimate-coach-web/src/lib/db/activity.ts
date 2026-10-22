import 'server-only';
import { execute } from './client';

export type ActivityEvent = 'sign_in' | 'snapshot_view' | 'admin_action';

export async function logActivity(
  userId: string,
  eventType: ActivityEvent,
  metadata?: Record<string, unknown>,
): Promise<void> {
  try {
    const meta = metadata ? JSON.stringify(metadata) : null;
    await execute(
      'INSERT INTO user_activity (user_id, event_type, metadata) VALUES (?, ?, ?)',
      [userId, eventType, meta],
    );
  } catch {
    // Activity logging is best-effort; never block the request on a log failure.
  }
}

export interface ActivityRow {
  id: number;
  user_id: string;
  event_type: ActivityEvent;
  metadata: string | null;
  created_at: string;
}

export async function listActivity(userId?: string, limit = 50): Promise<ActivityRow[]> {
  if (userId) {
    return execute(
      'SELECT * FROM user_activity WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
      [userId, limit],
    ) as Promise<ActivityRow[]>;
  }
  return execute(
    'SELECT * FROM user_activity ORDER BY created_at DESC LIMIT ?',
    [limit],
  ) as Promise<ActivityRow[]>;
}
