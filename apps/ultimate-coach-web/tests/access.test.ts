import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createCipheriv, randomBytes } from 'node:crypto';
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { isAuthorized, type VerifiedIdentity } from '../src/lib/access-policy.ts';
import { decryptSnapshot } from '../src/lib/server/snapshot-crypto.ts';

const allowed = ['captain@example.invalid'];
const valid: VerifiedIdentity = { userId: 'test-user', sessionUserId: 'test-user', sessionStatus: 'active',
  banned: false, locked: false, emails: [{ address: allowed[0], verified: true }] };

test('only a verified explicitly allowed active identity is authorized', () => {
  assert.equal(isAuthorized(valid, allowed), true);
  assert.equal(isAuthorized({ ...valid, emails: [{ address: ' CAPTAIN@example.invalid ', verified: true }] }, allowed), true);
});
test('anonymous, empty allowlist, unverified and unapproved accounts are denied', () => {
  assert.equal(isAuthorized(null, allowed), false);
  assert.equal(isAuthorized(valid, []), false);
  assert.equal(isAuthorized(valid, ['']), false);
  assert.equal(isAuthorized({ ...valid, emails: [{ address: allowed[0], verified: false }] }, allowed), false);
  assert.equal(isAuthorized({ ...valid, emails: [{ address: 'stranger@example.invalid', verified: true }] }, allowed), false);
});
test('revoked, expired, mismatched, banned and locked identities are denied', () => {
  for (const status of ['revoked', 'expired', 'ended', 'abandoned']) assert.equal(isAuthorized({ ...valid, sessionStatus: status }, allowed), false);
  assert.equal(isAuthorized({ ...valid, sessionUserId: 'other-user' }, allowed), false);
  assert.equal(isAuthorized({ ...valid, userId: '' }, allowed), false);
  assert.equal(isAuthorized({ ...valid, banned: true }, allowed), false);
  assert.equal(isAuthorized({ ...valid, locked: true }, allowed), false);
});

test('snapshot encryption authenticates the content, format and server-only key', () => {
  const key = randomBytes(32), iv = randomBytes(12), format = 'ultimate-coach-private-snapshot-v1';
  const cipher = createCipheriv('aes-256-gcm', key, iv);
  cipher.setAAD(Buffer.from(format));
  const ciphertext = Buffer.concat([cipher.update('synthetic-private-sentinel'), cipher.final(), cipher.getAuthTag()]);
  const frame = { format, iv: iv.toString('base64'), ciphertext: ciphertext.toString('base64') };
  assert.equal(decryptSnapshot(frame, key), 'synthetic-private-sentinel');
  assert.throws(() => decryptSnapshot(frame, randomBytes(32)));
  assert.throws(() => decryptSnapshot(frame, Buffer.alloc(0)));
  assert.throws(() => decryptSnapshot({ ...frame, format: 'other-format' }, key));
  ciphertext[0] ^= 1;
  assert.throws(() => decryptSnapshot({ ...frame, ciphertext: ciphertext.toString('base64') }, key));
});

test('historical loading is guarded before file access with no shared cache', () => {
  const loader = readFileSync('src/lib/server/historical-snapshot.ts', 'utf8');
  const authorizedLoader = loader.slice(loader.indexOf('export async function authorizedSnapshot'));
  assert.ok(authorizedLoader.indexOf('if (!access.ok) return access') < authorizedLoader.indexOf('fetchEncryptedFrame()'));
  assert.match(loader, /import 'server-only'/);
  assert.doesNotMatch(loader, /unstable_cache|React\.cache|force-cache/);
  const route = readFileSync('src/app/dashboard/[[...section]]/page.tsx', 'utf8');
  assert.match(route, /force-dynamic/);
  assert.ok(route.indexOf('if (!result.ok)') < route.indexOf('const snapshot = result.snapshot'));
  const authorization = readFileSync('src/lib/server/authorization.ts', 'utf8');
  assert.match(authorization, /sessions\.getSession\(sessionId\)/);
  assert.match(authorization, /users\.getUser\(userId\)/);
  assert.doesNotMatch(authorization, /searchParams|request\.json|headers\(\)/);
});

test('only ciphertext is accepted as a deployable snapshot; public modules have no private import', () => {
  assert.equal(existsSync('data/snapshot.json'), false);
  assert.equal(existsSync('private-snapshots/historical.enc.json'), false);
  const ignored = readFileSync('.gitignore', 'utf8');
  assert.match(ignored, /^private-snapshots\/$/m);
  function files(folder: string): string[] { return readdirSync(folder, { withFileTypes: true }).flatMap(e => e.isDirectory() ? files(join(folder, e.name)) : [join(folder, e.name)]); }
  for (const file of files('src')) {
    const text = readFileSync(file, 'utf8');
    if (!file.includes(join('lib', 'server')) && !file.includes(join('lib', 'db'))) {
      assert.doesNotMatch(text, /UC_SNAPSHOT_KEY|historical\.enc\.json|readFile\(/, file);
    }
    assert.doesNotMatch(text, /data\/snapshot\.json|NEXT_PUBLIC_UC_(?:SNAPSHOT|AUTHORIZED)|AUTH_BYPASS|MOCK_AUTH/i, file);
    if (text.startsWith("'use client'")) assert.doesNotMatch(text, /lib\/server|private-snapshots|process\.env/, file);
  }
  for (const file of ['src/app/page.tsx','src/app/match-night/page.tsx','src/app/recommendations/page.tsx','src/app/threats/page.tsx','src/app/team-status/page.tsx','src/app/summary/page.tsx']) {
    assert.doesNotMatch(readFileSync(file, 'utf8'), /from\s+['"][^'"]*(?:dashboard-pages|lib\/server)/);
  }
});
