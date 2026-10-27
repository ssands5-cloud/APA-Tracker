import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

function fixture() {
  const input = JSON.parse(readFileSync('tests/fixtures/captain-command.json', 'utf8'));
  const s = input.snapshot;
  s.plan.lead.alternatives = [];
  s.plan.holds = [{ our: 'Alex', covers: [], why: 'General remaining-plan support.' }];
  s.plan.sacrifices = [];
  s.evidence = {};
  s.simulation = { cap: 23, games: 5, availability: 'Captured players assumed available.', capNote: 'Reference only.' };
  s.provenance = { capturedAt: '2026-01-01', latestResult: '2025-12-31', fixtureWhen: 'Historical replay', notice: 'Synthetic test fixture.' };
  return input;
}
function render(script: string, input: unknown): string {
  const result = spawnSync(process.execPath, ['--experimental-strip-types', `tests/${script}`], {
    input: JSON.stringify(input), encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout;
}

test('protection-reasoning link reaches one designated-answer card without mixing general holds', () => {
  for (const multiple of [false, true]) {
    const input = fixture();
    if (multiple) input.snapshot.plan.protect.push({ our: 'Jordan', covers: ['Zane'], why: 'Keep the supplied Zane answer available.' });
    const command = render('render-captain-command.mjs', input);
    const href = command.match(/href="([^"]+)">See protection reasoning/)?.[1];
    assert.equal(href, '/dashboard/match-night#protected-options');
    const html = render('render-dashboard-pages.mjs', { ...input, page: 'MatchNightPage' });
    assert.equal((html.match(/\bid="protected-options"/g) ?? []).length, 1, 'the linked destination must exist exactly once');
    const target = html.match(/<section\b[^>]*\bid="protected-options"[^>]*>([\s\S]*?)<\/section>/)?.[1];
    assert.ok(target, 'destination must be the real designated-answer Card');
    assert.match(target, /Protect \/ designated answers/);
    for (const option of input.snapshot.plan.protect) {
      assert.ok(target.includes(option.our), 'designated player must be inside the destination');
      assert.ok(target.includes(option.why), 'protection rationale must be inside the destination');
      for (const opponent of option.covers) assert.ok(target.includes(opponent), 'designated target must be inside the destination');
    }
    assert.match(target, /One player can cover only one match/);
    assert.ok(!target.includes('General remaining-plan support.'), 'general holds must not be relabelled designated answers');
    assert.match(html, /General remaining-plan support\./, 'general hold reference must remain available');
  }
});

test('a bookmarked protection destination remains honest when the fixture has no designated protection', () => {
  const input = fixture();
  input.snapshot.plan.protect = [];
  const html = render('render-dashboard-pages.mjs', { ...input, page: 'MatchNightPage' });
  assert.equal((html.match(/\bid="protected-options"/g) ?? []).length, 1);
  const target = html.match(/<section\b[^>]*\bid="protected-options"[^>]*>([\s\S]*?)<\/section>/)?.[1];
  assert.ok(target);
  assert.match(target, /No designated hold is established under these assumptions\./);
  assert.doesNotMatch(target, /Keep for|General remaining-plan support/);
  assert.doesNotMatch(render('render-captain-command.mjs', input), /See protection reasoning/);
});
