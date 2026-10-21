import 'server-only';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { decryptSnapshot } from './snapshot-crypto';
import { historicalAccess, type AccessResult } from './authorization';
import type { Snapshot } from '../snapshot-types';

export type SnapshotResult = { ok: true; snapshot: Snapshot } | Extract<AccessResult, { ok: false }>;

export async function authorizedSnapshot(): Promise<SnapshotResult> {
  // Authorization precedes file access/decryption on every request, including React server requests.
  const access = await historicalAccess();
  if (!access.ok) return access;
  try {
    const key = Buffer.from(process.env.UC_SNAPSHOT_KEY ?? '', 'base64');
    if (key.length !== 32 || access.scope !== 'historical-pilot') return { ok: false, reason: 'unavailable' };
    const frame = JSON.parse(await readFile(join(process.cwd(), 'private-snapshots', 'historical.enc.json'), 'utf8'));
    const text = decryptSnapshot(frame, key);
    const snapshot = JSON.parse(text) as Snapshot;
    if (snapshot.schema !== 'ultimate-coach-dashboard-snapshot-v1' || snapshot.mode !== 'historical-simulation'
        || snapshot.label !== 'REALISTIC DEMO USING HISTORICAL DATA' || !snapshot.players?.length || !snapshot.opponents?.length) {
      return { ok: false, reason: 'unavailable' };
    }
    return { ok: true, snapshot };
  } catch {
    return { ok: false, reason: 'unavailable' };
  }
}
