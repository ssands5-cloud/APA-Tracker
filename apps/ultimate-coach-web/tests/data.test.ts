import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { evidence, players, opponents, responses, record, meetings, coverage } from '../src/lib/demo.ts';

test('every response and matrix entry belongs to the same invented fixture', () => {
  assert.equal(players.length, 3);
  assert.equal(opponents.length, 3);
  for (const opponent of opponents) {
    assert.match(opponent.id, /^demo-/);
    assert.ok(players.some(player => player.name === responses[opponent.id].player));
    for (const [playerId, row] of Object.entries(evidence[opponent.id])) {
      assert.ok(players.some(player => player.id === playerId));
      assert.ok(Number.isInteger(row.wins) && row.wins >= 0);
      assert.ok(Number.isInteger(row.losses) && row.losses >= 0);
      if (meetings(row) === 1) assert.match(row.note, /only 1 meeting/);
    }
  }
});
test('display totals and missing evidence are internally consistent', () => {
  const values = Object.values(evidence).flatMap(rows => Object.values(rows));
  assert.equal(values.length, 8);
  assert.equal(values.reduce((sum, row) => sum + meetings(row), 0), 20);
  assert.deepEqual(coverage('demo-yara'), { players: 2, meetings: 2 });
  assert.equal(record(evidence['demo-yara']['demo-alex']), 'No record');
  assert.equal(meetings(undefined), 0);
});
test('dashboard has no write, database or APA integration', () => {
  function files(folder: string): string[] {
    return readdirSync(folder, { withFileTypes: true }).flatMap(entry => entry.isDirectory() ? files(join(folder, entry.name)) : [join(folder, entry.name)]);
  }
  for (const file of files('src')) {
    const text = readFileSync(file, 'utf8');
    assert.doesNotMatch(text, /fetch\(|XMLHttpRequest|localStorage|sessionStorage|indexedDB|dangerouslySetInnerHTML|use server|\.db["']/i, file);
    assert.doesNotMatch(text, /export\s+(?:async\s+)?function\s+(?:POST|PUT|PATCH|DELETE)\b/, file);
  }
});
test('simple demo navigation avoids speculative RSC fetches', () => {
  for (const file of ['src/components/navigation.tsx', 'src/app/layout.tsx', 'src/app/page.tsx']) {
    const text = readFileSync(file, 'utf8');
    assert.doesNotMatch(text, /next\/link|<Link\b/);
    assert.match(text, /<a\b/);
  }
});
