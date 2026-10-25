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
  assert.match(html, /Quinn/);
  assert.match(html, /Save for Xeno/);
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
  assert.match(html, /Confirm tonight(?:&#x27;|’)s fixture/);
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

test('the opening panel exposes protection and its lineup cost before branding', () => {
  const html = render({ ...fixture(), withShell: true });
  assert.ok(html.indexOf('Who to protect') < html.indexOf('class="brand"'));
  assert.match(html, /Don(?:&#x27;|’)t spend your next answer/);
  assert.match(html, /one player can cover only one match/);
  assert.match(html, /href="\/dashboard\/match-night#protected-options"/);
});

test('no protected option does not invent a hold or claim the lineup is safe', () => {
  const input = fixture();
  input.snapshot.plan.protect = [];
  const html = render(input);
  assert.match(html, /No designated protection/);
  assert.match(html, /Check response tradeoffs/);
  assert.doesNotMatch(html, /Don’t spend your next answer|Save for Xeno/);
});

test('four immediate decisions precede full opening analysis', () => {
  const html = render(fixture());
  for (const label of ['SEND · if we lead', 'PROTECT', 'THREAT', 'TRADEOFF']) {
    assert.ok(html.indexOf(label) < html.indexOf('class="command-intelligence"'));
  }
});

test('scouting preserves only the answers designated for this opponent', () => {
  const input = fixture();
  input.view = 'dossiers';
  input.snapshot.plan.protect.push({ our: 'Alex', covers: ['Zane'], why: 'Save for Zane.' });
  const html = render(input);
  assert.match(html, /Plan(?:&#x27;|’)s counter<\/dt><dd>Jordan/);
  assert.match(html, /Who to preserve<\/dt><dd>Quinn/);
  assert.doesNotMatch(html, /Alex/);
  assert.match(html, /Spends the recorded answer against Zane/);
  assert.match(html, /2 of 3 captured players/);
  assert.match(html, /opponent=demo-xeno#response-explorer/);
});

test('scouting does not invent a counter when a response is absent', () => {
  const input = fixture(); input.view = 'dossiers'; input.snapshot.responses = {};
  const html = render(input);
  assert.match(html, /No response supplied/);
  assert.match(html, /No counter is established/);
  assert.doesNotMatch(html, /Strong Evidence/);
});

test('the team briefing presents conditional actions and their opportunity cost', () => {
  const input = fixture(); input.view = 'briefing';
  const html = render(input);
  assert.match(html, /If we put up first, lead with <b>Jordan/);
  assert.match(html, /Quinn for Xeno/);
  assert.match(html, /Sending a protected player early spends a later answer/);
  assert.match(html, /Confirm who is here/);
  assert.match(html, /Opening reason:/);
});
