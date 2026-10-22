import 'server-only';
import { execute, executeBatch } from './client';

export type Role = 'ADMIN' | 'COACH' | 'REVIEWER' | 'PENDING' | 'SUSPENDED';

export interface User {
  id: string;
  email: string;
  role: Role;
  display_name: string | null;
  created_at: string;
  updated_at: string;
}

const BOOTSTRAP_ID = 'bootstrap-seed';

export async function getUser(id: string): Promise<User | null> {
  const rows = await execute('SELECT * FROM users WHERE id = ?', [id]);
  return rows[0] as User ?? null;
}

export async function getUserByEmail(email: string): Promise<User | null> {
  const rows = await execute('SELECT * FROM users WHERE email = ?', [email.toLowerCase()]);
  return rows[0] as User ?? null;
}

export async function listUsers(role?: Role): Promise<User[]> {
  const rows = role
    ? await execute('SELECT * FROM users WHERE role = ? ORDER BY created_at DESC', [role])
    : await execute('SELECT * FROM users ORDER BY role ASC, created_at DESC', []);
  return rows as User[];
}

export async function createUser(
  id: string, email: string, role: Role, displayName?: string | null
): Promise<void> {
  await execute(
    "INSERT INTO users (id, email, role, display_name, created_at, updated_at) VALUES (?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'), strftime('%Y-%m-%dT%H:%M:%SZ','now'))",
    [id, email.toLowerCase(), role, displayName ?? null],
  );
}

export async function updateUserRole(id: string, role: Role): Promise<void> {
  await execute(
    "UPDATE users SET role = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?",
    [role, id],
  );
}

// Activate the bootstrap-seed placeholder when the seed admin first signs in.
export async function activateBootstrap(
  clerkId: string, email: string, displayName: string | null
): Promise<void> {
  await executeBatch([
    {
      sql: "UPDATE users SET id = ?, display_name = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?",
      args: [clerkId, displayName, BOOTSTRAP_ID],
    },
  ]);
}

export async function deleteUser(id: string): Promise<void> {
  await execute('DELETE FROM users WHERE id = ?', [id]);
}
