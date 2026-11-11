import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { opponentFromSearch } from '../src/components/opponent-link.ts';

function fixture() {
  const input = JSON.parse(readFileSync('tests/fixtures/captain-command.json', 'utf8'));
  const s = input.snapshot;
  s.evidence = {};
  s.simulation = { cap: 23, games: 5, availability: 'Captured players assumed available.', capNote: 'Reference only.' };
  s.provenance = { capturedAt: '2026-01-01', latestResult: '2025-12-31', fixtureWhen: 'Historical replay', notice: 'Synthetic test fixture.' };
  s.opponents.push({ id: 'demo-zane & scout', name: 'Zane' });
  s.threats.push({ name: 'Zane', text: 'Limited recorded support against one captured player.', wins: 1, meetings: 1, playersMet: 1 });
  s.responses['demo-zane & scout'] = { player: 'Alex', why: 'Recorded support for Zane only.', level: 'Thin', cost: 'Uses the supplied Zane answer.' };
  s.plan.protect.push({ our: 'Alex', covers: ['Zane'], why: 'Keep the supplied Zane answer available.' });
  return s;
}
function render(snapshot: unknown): string {
  const result = spawnSync(process.execPath, ['--experimental-strip-types', 'tests/render-dashboard-pages.mjs'], {
    input: JSON.stringify({ snapshot, page: 'ThreatsPage' }), encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout;
}
const dossiers = (html: string) => [...html.matchAll(/<section class="card threat-dossier"[^>]*>([\s\S]*?)<\/section>/g)].map(match => match[1]);

test('actual scouting page pairs each supplied counter, preservation and cost before supporting records', () => {
  const s = fixture();
  const html = render(s);
  const cards = dossiers(html);
  assert.equal(cards.length, 2, 'actual ThreatsPage must mount the existing dossier component');
  for (const [index, expected] of [
    { name: 'Xeno', id: 'demo-xeno', counter: 'Jordan', protect: 'Quinn', cost: 'Spends the recorded answer against Zane.' },
    { name: 'Zane', id: 'demo-zane & scout', counter: 'Alex', protect: 'Alex', cost: 'Uses the supplied Zane answer.' },
  ].entries()) {
    const card = cards[index];
    assert.match(card, new RegExp(`<h2>${expected.name}<\\/h2>`));
    assert.match(card, new RegExp(`Plan(?:&#x27;|')s counter<\\/dt><dd>${expected.counter}<\\/dd>`));
    assert.match(card, new RegExp(`Who to preserve<\\/dt><dd>${expected.protect}<\\/dd>`));
    assert.ok(card.includes(expected.cost));
    assert.match(card, /Why dangerous:|Why this counter:/);
    assert.match(card, /Mistake to avoid:/);
    assert.match(card, /One player can cover only one match/);
    const href = card.match(/href="([^"]+)">Prepare this response/)?.[1];
    assert.ok(href);
    const url = new URL(href, 'https://fixture.invalid');
    assert.equal(url.pathname, '/dashboard/match-night');
    assert.equal(url.hash, '#response-explorer');
    assert.equal(opponentFromSearch(url.search, s.opponents), expected.id);
  }
  assert.match(cards[1], /Thin Evidence/);
  assert.match(cards[1], /Small sample; this is not a proven dangerous matchup/);
  assert.match(cards[0], /2 of 3 captured players/);
  const context = html.match(/<details class="snapshot-context"><summary>Recorded threat evidence and context<\/summary>([\s\S]*?)<\/details>/)?.[1];
  assert.ok(context, 'legacy records remain in a closed native disclosure');
  assert.match(context, /shark-profile-card/);
  assert.match(context, /Historical direct record rate/);
  assert.ok(html.indexOf('card threat-dossier') < html.indexOf('<details class="snapshot-context">'));
  assert.match(html, /All captured players are assumed available/);
});

test('scouting page keeps absent counters, blank costs and no-threat uncertainty explicit', () => {
  const s = fixture();
  delete s.responses['demo-xeno'];
  s.responses['demo-zane & scout'].cost = '   ';
  const cards = dossiers(render(s));
  assert.equal(cards.length, 2);
  assert.match(cards[0], /No response supplied/);
  assert.match(cards[0], /No counter is established here/);
  assert.match(cards[1], /Response cost is not established in this snapshot\./);
  s.threats = [];
  s.plan.protect = [];
  const html = render(s);
  assert.equal(dossiers(html).length, 0);
  assert.match(html, /No named threat is established/);
  assert.match(html, /Missing evidence is not clearance/);
  assert.match(html, /href="\/dashboard\/match-night#response-explorer">Find a response/);
});
