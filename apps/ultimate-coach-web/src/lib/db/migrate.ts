/**
 * Database initialisation script.
 * Run once against a fresh Turso database:
 *   TURSO_DATABASE_URL=libsql://... TURSO_AUTH_TOKEN=... node --experimental-strip-types src/lib/db/migrate.ts
 */
import { readFile } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dir = dirname(fileURLToPath(import.meta.url));

async function run() {
  const url = (process.env.TURSO_DATABASE_URL ?? '').replace(/^libsql:\/\//, 'https://') + '/v2/pipeline';
  const token = process.env.TURSO_AUTH_TOKEN ?? '';
  if (!url || !token) { console.error('Set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN'); process.exit(1); }

  const schema = await readFile(join(__dir, 'schema.sql'), 'utf8');
  // Split on semicolons, drop empty lines
  const stmts = schema.split(';').map(s => s.trim()).filter(Boolean);

  for (const sql of stmts) {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ requests: [{ type: 'execute', stmt: { sql } }, { type: 'close' }] }),
    });
    if (!resp.ok) { console.error(`HTTP ${resp.status} for: ${sql.slice(0, 60)}`); process.exit(1); }
    const data = await resp.json() as { results: { type: string; error?: { message: string } }[] };
    if (data.results[0].type === 'error') {
      console.error(`DB error: ${data.results[0].error?.message} — for: ${sql.slice(0, 60)}`); process.exit(1);
    }
    console.log('OK:', sql.slice(0, 60));
  }
  console.log('Migration complete.');
}

run().catch(e => { console.error(e); process.exit(1); });
