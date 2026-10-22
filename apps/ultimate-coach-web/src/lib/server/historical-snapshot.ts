import 'server-only';
import { decryptSnapshot } from './snapshot-crypto';
import { historicalAccess, type AccessResult } from './authorization';
import type { Snapshot } from '../snapshot-types';

export type SnapshotResult = { ok: true; snapshot: Snapshot } | Extract<AccessResult, { ok: false }>;

async function fetchEncryptedFrame(): Promise<unknown> {
  const snapshotUrl = process.env.UC_SNAPSHOT_URL;
  if (snapshotUrl) {
    // Phase 1+: fetch encrypted frame from external storage (Vercel Blob, R2, S3, etc.).
    // URL is private — never forwarded to or exposed in the browser.
    const resp = await fetch(snapshotUrl, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`Snapshot fetch ${resp.status}`);
    return resp.json();
  }
  // Fallback for local development: read from a file placed manually outside git tracking.
  // This path is never used in production once UC_SNAPSHOT_URL is set.
  const { readFile } = await import('node:fs/promises');
  const { join } = await import('node:path');
  return JSON.parse(await readFile(join(process.cwd(), 'private-snapshots', 'historical.enc.json'), 'utf8'));
}

export async function authorizedSnapshot(): Promise<SnapshotResult> {
  // Authorization precedes file access and decryption on every request.
  const access = await historicalAccess();
  if (!access.ok) return access;
  try {
    const key = Buffer.from(process.env.UC_SNAPSHOT_KEY ?? '', 'base64');
    if (key.length !== 32 || access.scope !== 'historical-pilot') return { ok: false, reason: 'unavailable' };
    const frame = await fetchEncryptedFrame();
    const text = decryptSnapshot(frame, key);
    const snapshot = JSON.parse(text) as Snapshot;
    if (
      snapshot.schema !== 'ultimate-coach-dashboard-snapshot-v1' ||
      snapshot.mode !== 'historical-simulation' ||
      snapshot.label !== 'REALISTIC DEMO USING HISTORICAL DATA' ||
      !snapshot.players?.length ||
      !snapshot.opponents?.length
    ) {
      return { ok: false, reason: 'unavailable' };
    }
    return { ok: true, snapshot };
  } catch {
    return { ok: false, reason: 'unavailable' };
  }
}
