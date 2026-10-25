'use server';
import { revalidatePath } from 'next/cache';
import { historicalAccess } from '@/lib/server/authorization';
import { getUser, updateUserRole, deleteUser, type Role } from '@/lib/db/users';
import { appendAuditLog } from '@/lib/db/audit';

async function requireAdmin(): Promise<string> {
  const access = await historicalAccess();
  if (!access.ok || access.role !== 'ADMIN') throw new Error('Unauthorized');
  return access.userId;
}

async function changeRole(formData: FormData, newRole: Role, action: Parameters<typeof appendAuditLog>[1]): Promise<void> {
  const actorId = await requireAdmin();
  const targetId = String(formData.get('userId') ?? '');
  if (!targetId) throw new Error('Missing userId');
  const target = await getUser(targetId);
  if (!target) throw new Error('User not found');
  await updateUserRole(targetId, newRole);
  await appendAuditLog(actorId, action, targetId, target.role, newRole);
  revalidatePath('/dashboard/admin');
}

export async function approveUser(formData: FormData): Promise<void> {
  await changeRole(formData, 'COACH', 'approve');
}

export async function denyUser(formData: FormData): Promise<void> {
  await changeRole(formData, 'SUSPENDED', 'deny');
}

export async function promoteUser(formData: FormData): Promise<void> {
  const actorId = await requireAdmin();
  const targetId = String(formData.get('userId') ?? '');
  const target = await getUser(targetId);
  if (!target) throw new Error('User not found');
  const newRole: Role = target.role === 'COACH' ? 'REVIEWER' : target.role === 'REVIEWER' ? 'ADMIN' : target.role;
  await updateUserRole(targetId, newRole);
  await appendAuditLog(actorId, 'promote', targetId, target.role, newRole);
  revalidatePath('/dashboard/admin');
}

export async function demoteUser(formData: FormData): Promise<void> {
  const actorId = await requireAdmin();
  const targetId = String(formData.get('userId') ?? '');
  const target = await getUser(targetId);
  if (!target) throw new Error('User not found');
  const newRole: Role = target.role === 'ADMIN' ? 'REVIEWER' : target.role === 'REVIEWER' ? 'COACH' : target.role;
  await updateUserRole(targetId, newRole);
  await appendAuditLog(actorId, 'demote', targetId, target.role, newRole);
  revalidatePath('/dashboard/admin');
}

export async function suspendUser(formData: FormData): Promise<void> {
  await changeRole(formData, 'SUSPENDED', 'suspend');
}

export async function removeAccess(formData: FormData): Promise<void> {
  const actorId = await requireAdmin();
  const targetId = String(formData.get('userId') ?? '');
  if (!targetId) throw new Error('Missing userId');
  const target = await getUser(targetId);
  if (!target) throw new Error('User not found');
  await appendAuditLog(actorId, 'remove', targetId, target.role, null, 'Access record removed');
  await deleteUser(targetId);
  revalidatePath('/dashboard/admin');
}
