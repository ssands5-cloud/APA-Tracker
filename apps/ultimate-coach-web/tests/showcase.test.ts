import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import * as L from '../src/lib/showcase/league.ts';
import { buildSeason } from '../src/lib/showcase/engine.ts';
import type { RawSeason } from '../src/lib/showcase/types.ts';
import { isLocalHost, loadRealSeason, parseRealSeason, realBetaEnabled } from '../src/lib/server/showcase-real.ts';

const walk = (dir: string): string[] => readdirSync(dir, { withFileTypes: true }).flatMap(e => e.isDirectory() ? walk(join(dir, e.name)) : [join(dir, e.name)]);

/* ── The simulated season ──────────────────────────────────────────────────── */
test('the simulated season is internally consistent', () => {
  assert.equal(L.LEAGUE.mode, 'simulated');
  assert.equal(L.allTeams.length, 8);
  assert.equal(L.allPlayers.length, 64);
  const played = L.LEAGUE.currentWeek - 1;
  assert.equal(L.allResults.length, played * 4);
  for (const row of L.standings) {
    assert.equal(row.w + row.l, played, `${row.team.name} played every week`);
    assert.equal(row.indivW + row.indivL, played * 5, 'five individual matches per team match');
  }
  assert.deepEqual(L.standings.map(r => r.rank), [1, 2, 3, 4, 5, 6, 7, 8]);
  for (let i = 1; i < L.standings.length; i++) assert.ok(L.standings[i - 1].points >= L.standings[i].points, 'sorted by points');
  assert.equal(L.standings.reduce((s, r) => s + r.w, 0), L.standings.reduce((s, r) => s + r.l, 0), 'every win is someone else\'s loss');
  assert.equal(L.allPlayers.reduce((s, p) => s + p.wins, 0), L.allPlayers.reduce((s, p) => s + p.losses, 0));
});

test('every probability is a real number between 0 and 1 and lineups respect the cap', () => {
  for (const u of L.upcoming) {
    assert.ok(u.homeProb > 0 && u.homeProb < 1);
    assert.ok(u.pairProbs.every(p => p > 0 && p < 1));
    assert.ok(Number.isFinite(u.projHome) && Number.isFinite(u.projAway));
    for (const lineup of [u.homeLineup, u.awayLineup]) {
      assert.equal(new Set(lineup).size, 5);
      assert.ok(lineup.reduce((s, id) => s + L.player(id).sl, 0) <= L.LEAGUE.cap, 'skill levels fit under the cap');
    }
  }
  for (const m of L.allResults) assert.ok(m.homeProb > 0 && m.homeProb < 1);
});

test('every roster, power row and feed is populated', () => {
  assert.equal(L.featured.fixture.home === L.MY_TEAM || L.featured.fixture.away === L.MY_TEAM, true);
  assert.equal(L.powerRankings.length, 8);
  for (const r of L.powerRankings) { assert.ok(r.blurb.length > 40); assert.ok(Number.isFinite(r.score)); }
  assert.ok(L.feed.length >= 8);
  for (const t of L.allTeams) assert.equal(t.roster.length, 8);
  assert.equal(L.byeTeams.length, 0);
});

/* ── Real-data local beta: strictly gated ──────────────────────────────────── */
test('real data is read only under next dev, when explicitly switched on, and never on Vercel or CI', () => {
  const on = { UC_SHOWCASE_REAL: '1', NODE_ENV: 'development' };
  assert.equal(realBetaEnabled(on), true);
  assert.equal(realBetaEnabled({}), false, 'off by default');
  assert.equal(realBetaEnabled({ ...on, UC_SHOWCASE_REAL: '0' }), false);
  assert.equal(realBetaEnabled({ ...on, NODE_ENV: 'production' }), false, 'never in a build or next start');
  assert.equal(realBetaEnabled({ ...on, NODE_ENV: 'test' }), false);
  assert.equal(realBetaEnabled({ ...on, VERCEL: '1' }), false);
  assert.equal(realBetaEnabled({ ...on, VERCEL_ENV: 'preview' }), false);
  assert.equal(realBetaEnabled({ ...on, CI: 'true' }), false);
});

test('a real-data file on disk is ignored unless the gate is open', () => {
  const dir = mkdtempSync(join(tmpdir(), 'uc-real-'));
  try {
    mkdirSync(join(dir, 'private-snapshots'));
    writeFileSync(join(dir, 'private-snapshots', 'showcase-real.json'), 'not even json');
    assert.equal(loadRealSeason({ UC_SHOWCASE_REAL: '1', NODE_ENV: 'production' }, dir), null);
    assert.equal(loadRealSeason({ NODE_ENV: 'development' }, dir), null);
    assert.throws(() => loadRealSeason({ UC_SHOWCASE_REAL: '1', NODE_ENV: 'development' }, dir), 'an open gate reads the file (and rejects a bad one)');
    assert.equal(loadRealSeason({ UC_SHOWCASE_REAL: '1', NODE_ENV: 'development' }, join(dir, 'missing')), null, 'no file means the simulation, never an error page');
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test('only localhost is ever served real data', () => {
  for (const host of ['localhost:3011', '127.0.0.1:3011', '127.0.0.1', '[::1]:3000']) assert.equal(isLocalHost(host), true, host);
  for (const host of ['apa-tracker.vercel.app', 'example.com', '192.168.1.20:3011', 'localhost.evil.com', '', null, undefined]) assert.equal(isLocalHost(host), false, String(host));
});

test('real data can never be committed and never reaches the browser bundle', () => {
  assert.match(readFileSync('.gitignore', 'utf8'), /^private-snapshots\/$/m);
  const bad = /UC_SHOWCASE_REAL|showcase-real|private-snapshots/;
  for (const file of walk('src')) {
    const text = readFileSync(file, 'utf8');
    if (text.startsWith("'use client'")) {
      assert.doesNotMatch(text, /showcase\/league|showcase\/ui|lib\/server|from '\.\/ui'/, `${file} is a browser file and must not import season data`);
    }
    // Only the loader itself, the one module that calls it, and the layout's host check may mention it.
    const allowed = file.includes(join('lib', 'server')) || file.endsWith(join('showcase', 'layout.tsx')) || file.endsWith(join('lib', 'showcase', 'league.ts'));
    if (!allowed) assert.doesNotMatch(text, bad, `${file} must not reference the real-data file`);
  }
});

test('the engine handles a real-shaped division: byes, tied APA ranks, and APA points as the table', () => {
  const player = (id: string, team: number, sl: number) => ({ id, name: `Player ${id.toUpperCase()}`, team, sl, startSl: sl, slEvents: [] });
  const raw: RawSeason = {
    league: { name: 'Test League', division: 'Test Division', season: 'Fall', format: '8-Ball', cap: 23, currentWeek: 3, totalWeeks: 4,
      matchDate: 'Sun Nov 15, 2026', matchTime: '11:00 AM MT', maxMatchPoints: 14, maxGamePoints: 3, playoffSpots: null, venueKnown: false, mode: 'local-real' },
    myTeam: 0,
    teams: [{ name: 'Alpha', short: 'AL', venue: null }, { name: 'Bravo', short: 'BR', venue: null }, { name: 'Charlie', short: 'CH', venue: null }],
    players: [player('a1', 0, 4), player('a2', 0, 3), player('b1', 1, 5), player('b2', 1, 2), player('c1', 2, 4), player('c2', 2, 4)],
    weeks: [
      { week: 1, matches: [{ home: 0, away: 1, homePts: 9, awayPts: 7, homeWins: 2, awayWins: 0, games: [
        { home: 'a1', away: 'b1', homePts: 3, awayPts: 0, winner: 'a1' }, { home: 'a2', away: 'b2', homePts: 2, awayPts: 1, winner: 'a2' }] }] },
      { week: 2, matches: [{ home: 1, away: 2, homePts: 8, awayPts: 8, homeWins: 1, awayWins: 1, games: [
        { home: 'b1', away: 'c1', homePts: 2, awayPts: 1, winner: 'b1' }, { home: 'b2', away: 'c2', homePts: 0, awayPts: 2, winner: 'c2' }] }] },
    ],
    upcoming: [{ home: 0, away: 2 }],
    apaStandings: [{ team: 0, rank: 1, points: 20, tied: true }, { team: 1, rank: 3, points: 15 }, { team: 2, rank: 1, points: 20, tied: true }],
  };
  const s = buildSeason(raw);
  assert.deepEqual(s.byeTeams.map(t => t.name), ['Bravo']);
  assert.equal(s.myTeamOnBye, false);
  assert.deepEqual(s.teamPointsGrid(0), [9, null], 'a bye week is null, not zero');
  assert.deepEqual(s.teamPointsByWeek(0), [9]);
  assert.deepEqual(s.standings.map(r => [r.team.name, r.rank, r.tied, r.points]).sort(), [['Alpha', 1, true, 20], ['Bravo', 3, false, 15], ['Charlie', 1, true, 20]].sort());
  assert.equal(s.standings.find(r => r.team.name === 'Bravo')!.behind, 5);
  const alpha = s.standings.find(r => r.team.name === 'Alpha')!;
  assert.equal(`${alpha.w}-${alpha.l}`, '1-0', 'W-L still comes from the scoresheets');
  const u = s.upcoming[0];
  assert.equal(u.homeLineup.length, 2, 'fewer than five players still project');
  assert.ok(u.homeProb > 0 && u.homeProb < 1 && Number.isFinite(u.projHome));
  assert.ok(s.powerRankings.every(r => r.blurb.length > 20));
  assert.equal(parseRealSeason(JSON.stringify({ schema: 'ultimate-coach-showcase-real-v1', league: raw.league, myTeam: 0, teams: raw.teams,
    players: raw.players, weeks: raw.weeks, upcoming: raw.upcoming, apaStandings: raw.apaStandings })).league.mode, 'local-real');
  assert.throws(() => parseRealSeason(JSON.stringify({ schema: 'other' })));
  assert.throws(() => parseRealSeason(JSON.stringify({ schema: 'ultimate-coach-showcase-real-v1', league: raw.league, myTeam: 0, teams: raw.teams,
    players: raw.players, weeks: [{ week: 1, matches: [{ ...raw.weeks[0].matches[0], games: [{ home: 'zz', away: 'b1', homePts: 1, awayPts: 0, winner: 'zz' }] }] }], upcoming: [] })), 'an unknown player is rejected');
});

/* ── Source hygiene ────────────────────────────────────────────────────────── */
test('showcase pages ship no placeholder text and make no network, storage or database calls', () => {
  const files = [...walk('src/app/showcase'), ...walk('src/components/showcase'), ...walk('src/lib/showcase')].filter(f => /\.(ts|tsx)$/.test(f));
  for (const file of files) {
    const text = readFileSync(file, 'utf8');
    assert.doesNotMatch(text, /lorem ipsum|TODO|FIXME|placeholder|coming soon|TBD/i, file);
    assert.doesNotMatch(text, /fetch\(|XMLHttpRequest|localStorage|sessionStorage|indexedDB|dangerouslySetInnerHTML|use server|\.db["']|UC_SNAPSHOT_KEY|clerk/i, file);
    const mayImportServer = file.endsWith(join('showcase', 'layout.tsx')) || file.endsWith(join('lib', 'showcase', 'league.ts'));
    if (!mayImportServer) assert.doesNotMatch(text, /lib\/server|\.\.\/server\//, `${file}: only the layout (host check) and league.ts (loader) may import server code`);
  }
});
