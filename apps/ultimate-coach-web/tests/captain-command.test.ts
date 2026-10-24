import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { evidenceLabel } from '../src/lib/evidence-label.ts';

const fixture = () => JSON.parse(readFileSync('tests/fixtures/captain-command.json', 'utf8'));
function render(input: unknown): string {
  const result = spawnSync(process.execPath, ['--experimental-strip-types', 'tests/render-captain-command.mjs'], {
    input: JSON.stringify(input), encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout;
}

test('the command presents the supplied opening, reasoning and matchup without changing the plan', () => {
  const input = fixture();
  const before = structuredClone(input);
  const html = render(input);
  assert.match(html, /Lead with<\/span> Jordan/);
  assert.match(html, /Solid Evidence/);
  assert.match(html, /Keeps a supported response/);
  assert.match(html, /8–2 in 10 recorded meetings/);
  assert.match(html, /Historical reference/);
  assert.match(html, /href="\/dashboard\/match-night\?opponent=demo-xeno#response-explorer"/);
  assert.deepEqual(input, before);
});

test('sparse evidence does not clear opponents or invent readiness', () => {
  const input = fixture();
  input.snapshot.threats = [];
  input.snapshot.plan.lead.level = 'Unknown';
  input.snapshot.plan.strongest.level = 'Unknown';
  const html = render(input);
  assert.match(html, /Unknown/);
  assert.match(html, /Unknown opponents are not cleared/);
  assert.match(html, /Confirm tonight’s fixture/);
  assert.doesNotMatch(html, /Strong Evidence|READY|win probability/i);
});

test('match night keeps the opening conditional and makes the opponent response reachable', () => {
  const html = render({ ...fixture(), matchNight: true });
  assert.match(html, /If we put up first/);
  assert.match(html, /href="#response-explorer"/);
  assert.match(html, /Find our response/);
});

test('caution and conflicted evidence are preserved rather than upgraded to confidence', () => {
  for (const level of ['Strong', 'Solid', 'Thin']) assert.equal(evidenceLabel(level), `${level} Evidence`);
  for (const level of ['Unknown', 'Caution', 'Conflicted']) assert.equal(evidenceLabel(level), level);
});

test('the opening action, reason and recorded concern precede supporting site branding', () => {
  const html = render({ ...fixture(), withShell: true });
  assert.ok(html.indexOf('Lead with') < html.indexOf('class="brand"'));
  assert.ok(html.indexOf('class="command-why"') < html.indexOf('class="brand"'));
  assert.ok(html.indexOf('class="command-risk"') < html.indexOf('class="command-primary"'));
  assert.match(html, /Biggest recorded concern/);
  assert.match(html, /Risk is not rated by the historical engine/);
});
