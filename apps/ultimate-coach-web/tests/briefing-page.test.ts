import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

function fixture() {
  const { snapshot: s } = JSON.parse(readFileSync('tests/fixtures/captain-command.json', 'utf8'));
  s.plan.weakest = { our: 'Alex', their: 'Zane', level: 'Unknown', why: 'No direct support is established.' };
  s.plan.fragility = { rating: 'Thin', player: null, thinPairings: ['Alex versus Zane needs confirmation.'] };
  s.plan.summary = 'Conditional reference plan using the captured roster.';
  s.simulation = { cap: 23, games: 5, availability: 'Captured players assumed available.', capNote: 'Reference only.' };
  s.provenance = { capturedAt: '2026-01-01', latestResult: '2025-12-31', fixtureWhen: 'Historical replay', notice: 'Synthetic test fixture.' };
  return s;
}
function render(snapshot: unknown): string {
  const result = spawnSync(process.execPath, ['--experimental-strip-types', 'tests/render-dashboard-pages.mjs'], {
    input: JSON.stringify({ snapshot, page: 'SummaryPage' }), encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout;
}
function supportingContext(html: string): string {
  const match = html.match(/<details class="snapshot-context"><summary>Supporting plan and historical evidence<\/summary>([\s\S]*?)<\/details>/);
  assert.ok(match, 'real SummaryPage must group secondary notes in one closed native disclosure');
  return match[0];
}

test('actual SummaryPage has one primary team brief and retains all supporting plan evidence', () => {
  const html = render(fixture());
  const context = supportingContext(html);
  const primaryOnly = html.replace(context, '');
  assert.equal((primaryOnly.match(/aria-label="One-minute team briefing"/g) ?? []).length, 1);
  assert.doesNotMatch(primaryOnly, /class="briefing-items"|Match Night Engine briefing/);
  assert.match(primaryOnly, /If we put up first, lead with <b>Jordan/);
  assert.match(primaryOnly, /Quinn for Xeno/);
  assert.match(primaryOnly, /Sending a protected player early spends a later answer/);
  assert.match(primaryOnly, /Confirm who is here/);
  assert.match(primaryOnly, /href="\/dashboard\/match-night#response-explorer"/);
  assert.ok(html.indexOf('One-minute team briefing') < html.indexOf('<details class="snapshot-context">'));
  assert.match(context, /<strong>If we put up first, lead with Jordan\./);
  for (const retained of ['Best opportunity in the plan', 'Verify Before Acting', 'Strongest evidence in the planned matchups',
    'Weakest evidence in the planned matchups', 'Conditional reference plan using the captured roster.',
    'Alex versus Zane needs confirmation.', 'Captured players assumed available.', 'Latest recorded result: 2025-12-31']) {
    assert.ok(context.includes(retained), `supporting information lost: ${retained}`);
  }
  assert.match(context, /href="\/dashboard\/match-night"/);
  assert.doesNotMatch(context, /<strong>Lead with Jordan\./, 'reference notes must not turn the conditional opening into an unconditional send');
});

test('consolidated briefing does not invent protection, a threat or thin evidence in empty states', () => {
  const s = fixture();
  s.plan.protect = [];
  s.threats = [];
  s.plan.fragility.thinPairings = [];
  const html = render(s);
  const context = supportingContext(html);
  const primaryOnly = html.replace(context, '');
  assert.match(primaryOnly, /No matchup-specific protection is designated/);
  assert.match(primaryOnly, /No named threat is established. Unknown opponents are not cleared/);
  assert.match(context, /No unique designated-answer protection is established/);
  assert.match(context, /No thin pairing flagged in this plan/);
  assert.match(context, /No winning direct-record threat established; inspect missing evidence/);
});
