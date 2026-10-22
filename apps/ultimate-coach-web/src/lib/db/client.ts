import 'server-only';

// Turso HTTP API client — no external dependency; uses the standard fetch available in Next.js.
// TURSO_DATABASE_URL: libsql://<db-name>-<org>.turso.io
// TURSO_AUTH_TOKEN: Turso auth token

type SqlArg = string | number | null;
type Row = Record<string, string | number | null>;

interface TursoValue { type: string; value?: string }
interface TursoCol  { name: string }
interface TursoResult {
  type: 'ok';
  response: { result: { cols: TursoCol[]; rows: TursoValue[][] } };
}
interface TursoError { type: 'error'; error: { message: string } }
interface TursoPipelineResponse { results: (TursoResult | TursoError)[] }

function toArg(v: SqlArg): TursoValue {
  if (v === null) return { type: 'null' };
  if (typeof v === 'number') return { type: Number.isInteger(v) ? 'integer' : 'float', value: String(v) };
  return { type: 'text', value: v };
}

function fromArg(v: TursoValue): string | number | null {
  if (v.type === 'null') return null;
  if (v.type === 'integer') return parseInt(v.value!, 10);
  if (v.type === 'float') return parseFloat(v.value!);
  return v.value ?? null;
}

function endpoint(): string {
  const raw = process.env.TURSO_DATABASE_URL ?? '';
  if (!raw) throw new Error('TURSO_DATABASE_URL is not set');
  return raw.replace(/^libsql:\/\//, 'https://') + '/v2/pipeline';
}

export async function execute(sql: string, args: SqlArg[] = []): Promise<Row[]> {
  const resp = await fetch(endpoint(), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${process.env.TURSO_AUTH_TOKEN ?? ''}`,
      'Content-Type': 'application/json',
    },
    cache: 'no-store',
    body: JSON.stringify({
      requests: [
        { type: 'execute', stmt: { sql, args: args.map(toArg) } },
        { type: 'close' },
      ],
    }),
  });
  if (!resp.ok) throw new Error(`Turso HTTP ${resp.status}`);
  const data = await resp.json() as TursoPipelineResponse;
  const first = data.results[0];
  if (first.type === 'error') throw new Error(`DB: ${(first as TursoError).error.message}`);
  const { cols, rows } = (first as TursoResult).response.result;
  return rows.map(row => Object.fromEntries(cols.map((c, i) => [c.name, fromArg(row[i])])));
}

export async function executeBatch(stmts: { sql: string; args?: SqlArg[] }[]): Promise<void> {
  const requests = stmts.map(s => ({ type: 'execute', stmt: { sql: s.sql, args: (s.args ?? []).map(toArg) } }));
  requests.push({ type: 'close' } as never);
  const resp = await fetch(endpoint(), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${process.env.TURSO_AUTH_TOKEN ?? ''}`,
      'Content-Type': 'application/json',
    },
    cache: 'no-store',
    body: JSON.stringify({ requests }),
  });
  if (!resp.ok) throw new Error(`Turso HTTP ${resp.status}`);
  const data = await resp.json() as TursoPipelineResponse;
  for (const r of data.results) {
    if (r.type === 'error') throw new Error(`DB batch: ${(r as TursoError).error.message}`);
  }
}
