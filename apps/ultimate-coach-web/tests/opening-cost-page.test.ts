import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

test('Blind Send never borrows an opponent response cost; response-table costs stay scoped', () => {
  const costs = ['Spends the answer reserved for Xeno.', 'Spends the answer reserved for Zane.'];
  for (const reverse of [false, true]) {
    const { snapshot } = JSON.parse(readFileSync('tests/fixtures/captain-command.json', 'utf8'));
    snapshot.plan.lead.alternatives = [];
    snapshot.plan.holds = [];
    snapshot.plan.sacrifices = [];
    snapshot.simulation = { cap: 23, games: 5, availability: 'Captured players assumed available.', capNote: 'Reference only.' };
    snapshot.provenance = { capturedAt: '2026-01-01', latestResult: '2025-12-31', fixtureWhen: 'Historical replay', notice: 'Synthetic test fixture.' };
    snapshot.opponents.push({ id: 'demo-zane', name: 'Zane' });
    snapshot.evidence = {};
    const response = snapshot.responses['demo-xeno'];
    const entries = [
      ['demo-xeno', { ...response, cost: costs[0] }],
      ['demo-zane', { ...response, cost: costs[1] }],
    ];
    snapshot.responses = Object.fromEntries(reverse ? entries.reverse() : entries);
    const result = spawnSync(process.execPath, ['--experimental-strip-types', 'tests/render-dashboard-pages.mjs'], {
      input: JSON.stringify({ snapshot, page: 'MatchNightPage' }), encoding: 'utf8',
    });
    assert.equal(result.status, 0, result.stderr);
    const html = result.stdout;
    const blindSend = html.match(/<aside\b[^>]*aria-label="Blind Send recommendation"[^>]*>([\s\S]*?)<\/aside>/)?.[1];
    assert.ok(blindSend, 'real MatchNightPage must expose its Blind Send aside');
    assert.match(blindSend, /Opening-specific cost is not established in this snapshot\./);
    for (const cost of costs) assert.ok(!blindSend.includes(cost), `Blind Send borrowed a response cost: ${cost}`);
    assert.match(blindSend, /Jordan/);
    assert.match(html, /Quinn/);
    for (const [index, name] of ['Xeno', 'Zane'].entries()) {
      const row = html.match(new RegExp(`<tr><th scope="row"><a[^>]*>${name}<\\/a><\\/th>([\\s\\S]*?)<\\/tr>`))?.[1];
      assert.ok(row, `response row missing for ${name}`);
      assert.ok(row.includes(costs[index]), `response cost must stay with ${name}`);
      assert.ok(!row.includes(costs[1 - index]), `response cost crossed opponents for ${name}`);
    }
  }
});
