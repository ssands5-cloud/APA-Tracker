/**
 * Showcase simulation: an entirely invented 8-Ball division, simulated deterministically so every
 * screen has internally consistent numbers. No real teams, players or APA records are used.
 * Output is the same RawSeason shape the real-data export uses, so one engine serves both.
 */
import { bestLegalFive, playerWinProb } from './engine.ts';
import type { LeagueMeta, Player, RawFixture, RawGame, RawMatch, RawPlayer, RawSeason, RawWeek } from './types.ts';

function mulberry32(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const TEAM_DEFS = [
  { name: 'Corner Pocket Kings', venue: 'The Rack Room' },
  { name: 'Rack City Rollers', venue: 'Shooters Billiards' },
  { name: 'Chalk & Awe', venue: 'Cue Club Lakewood' },
  { name: 'Cue Tip Cartel', venue: 'Eight Ball Saloon' },
  { name: 'Bankroll Bandits', venue: 'Felt & Fortune' },
  { name: 'The Scratch Club', venue: 'Side Street Tavern' },
  { name: 'Eight Ball Express', venue: 'Golden Triangle Billiards' },
  { name: 'Side Pocket Saints', venue: 'Breakers Pub' },
] as const;

const FIRST = ['Marcus','Elena','Derek','Tasha','Ray','Monica','Luis','Kendra','Trevor','Angela','Victor','Brooke','Hector','Dana','Curtis','Renee','Omar','Shelby','Grant','Paula','Darius','Megan','Wes','Carla','Andre','Tina','Jared','Lena','Rico','Holly','Simon','Nadia','Calvin','Jolene','Felix','Rosa','Brent','Ivy','Malik','Gwen','Dean','Sofia','Ty','Erin','Nate','Leah','Cole','Maya','Reggie','Kim','Phil','Alana','Boyd','Trish','Gabe','Nina','Hank','Vera','Jon','Lucy','Otis','Bree','Sam','Dottie'];
const LAST = ['Delgado','Whitaker','Okafor','Brennan','Castillo','Pruitt','Nakamura','Hollis','Ferraro','Quintana','Vance','Mercer','Abernathy','Rios','Lindqvist','Tate','Gallagher','Moreno','Strickland','Huang','Ellison','Barajas','Kowalski','Dunbar','Archuleta','Fontaine','Sandoval','Pickett','Romero','Haskins','Medina','Calloway','Ostrowski','Banks','Villanueva','Garrity','Sato','McBride','Trujillo','Lund','Kessler','Booker','Montoya','Ruiz','Hale','Ackerman','Duarte','Petrakis','Wolfe','Navarro','Coyle','Esparza','Holm','Jaramillo','Bishop','Lucero','Rademacher','Ybarra','Stanton','Cordova','Fenwick','Maestas','Thorne','Valdez'];

const LEAGUE: LeagueMeta = {
  name: 'Front Range Pool League', division: 'Tuesday Night 8-Ball · Division 412', season: 'Fall 2026', format: '8-Ball', cap: 23,
  currentWeek: 11, totalWeeks: 16, matchDate: 'Tue Nov 10, 2026', matchTime: '7:00 PM MT',
  maxMatchPoints: 15, maxGamePoints: 3, playoffSpots: 4, venueKnown: true, mode: 'simulated',
};

type SimPlayer = Player & { skill: number };
type Fix = { week: number; home: number; away: number };

export function simulateSeason(): RawSeason {
  const rand = mulberry32(20261110);
  const pick = <T,>(xs: readonly T[]) => xs[Math.floor(rand() * xs.length)];
  function shuffle<T>(xs: T[]): T[] { const a = [...xs]; for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }

  /** A roster is playable when, even if its weakest player rests, five legal players fit under the cap. */
  const feasible = (sls: number[]) => [...sls].sort((a, b) => a - b).slice(1, 6).reduce((x, y) => x + y, 0) <= LEAGUE.cap;

  const teamIds = TEAM_DEFS.map((_, i) => i);
  const rosters: string[][] = teamIds.map(() => []);
  const players: Record<string, SimPlayer> = {};
  const slEvents: Record<string, RawPlayer['slEvents']> = {};
  const slPool = [2, 3, 3, 4, 4, 4, 5, 5, 5, 6, 6, 7];
  const teamStrength = [55, 70, 35, 15, -10, -35, -50, -75];
  const names = shuffle(FIRST).map((f, i) => `${f} ${shuffle(LAST)[i % LAST.length]}`);
  const usedNames = new Set<string>();
  let nameIndex = 0;
  for (const t of teamIds) {
    const sls = Array.from({ length: 8 }, () => pick(slPool));
    while (!feasible(sls)) { const i = sls.indexOf(Math.max(...sls)); sls[i] -= 1; }
    for (let k = 0; k < 8; k++) {
      let name = names[nameIndex++ % names.length];
      while (usedNames.has(name)) name = `${pick(FIRST)} ${pick(LAST)}`;
      usedNames.add(name);
      const id = `p${t}-${k}`;
      // "skill" is ability relative to the handicap: APA skill levels already even out raw ability.
      const skill = 1500 + teamStrength[t] + Math.round((rand() - 0.5) * 220);
      players[id] = { id, name, team: t, sl: sls[k], startSl: sls[k], rating: 1500, ratingHistory: [1500], skill,
        played: 0, wins: 0, losses: 0, points: 0, shutouts: 0, form: [], weekly: [] };
      slEvents[id] = [];
      rosters[t].push(id);
    }
  }

  /* Schedule: round robin (circle method), repeating. */
  function roundRobin(n: number): Fix[][] {
    const ids = [...Array(n).keys()];
    const rounds: Fix[][] = [];
    for (let r = 0; r < n - 1; r++) {
      const round: Fix[] = [];
      for (let i = 0; i < n / 2; i++) {
        const a = ids[i], b = ids[n - 1 - i];
        round.push(r % 2 ? { week: 0, home: b, away: a } : { week: 0, home: a, away: b });
      }
      rounds.push(round);
      ids.splice(1, 0, ids.pop()!);
    }
    return rounds;
  }
  const cycle = roundRobin(teamIds.length);
  const schedule: Fix[][] = [];
  for (let w = 1; w <= LEAGUE.totalWeeks; w++) {
    const base = cycle[(w - 1) % cycle.length];
    const flip = w > cycle.length;
    schedule.push(base.map(f => ({ week: w, home: flip ? f.away : f.home, away: flip ? f.home : f.away })));
  }

  const trueWinProb = (a: SimPlayer, b: SimPlayer) => 1 / (1 + 10 ** ((b.skill - a.skill) / 400));
  function lineup(team: number, week: number): string[] {
    const roster = rosters[team].map(id => players[id]);
    const resting = roster[(week * 3 + team) % roster.length].id;
    return bestLegalFive(roster.filter(p => p.id !== resting), LEAGUE.cap).map(p => p.id);
  }
  const points = (): [number, number] => { const r = rand(); return r < 0.24 ? [3, 0] : r < 0.6 ? [2, 1] : [2, 0]; };
  const K = 28;

  const weeks: RawWeek[] = [];
  for (let w = 1; w < LEAGUE.currentWeek; w++) {
    const matches: RawMatch[] = [];
    for (const f of schedule[w - 1]) {
      const hl = lineup(f.home, w), al = lineup(f.away, w);
      const games: RawGame[] = [];
      let hp = 0, ap = 0, hw = 0, aw = 0;
      for (let i = 0; i < 5; i++) {
        const a = players[hl[i]], b = players[al[i]];
        const homeWins = rand() < trueWinProb(a, b);
        const [wp, lp] = points();
        const [winner, loser] = homeWins ? [a, b] : [b, a];
        winner.wins++; loser.losses++; winner.played++; loser.played++;
        winner.form.push('W'); loser.form.push('L');
        winner.weekly.push({ week: w, result: 'W', points: wp, opp: loser.name });
        loser.weekly.push({ week: w, result: 'L', points: lp, opp: winner.name });
        const delta = Math.round(K * (1 - playerWinProb(winner, loser)));
        winner.rating += delta; loser.rating -= delta;
        if (homeWins) { hp += wp; ap += lp; hw++; } else { ap += wp; hp += lp; aw++; }
        games.push({ home: a.id, away: b.id, homePts: homeWins ? wp : lp, awayPts: homeWins ? lp : wp, winner: winner.id });
      }
      matches.push({ home: f.home, away: f.away, homePts: hp, awayPts: ap, homeWins: hw, awayWins: aw, games });
    }
    weeks.push({ week: w, matches });
    for (const p of Object.values(players)) {
      const recent = p.weekly.slice(-4);
      if (w >= 5 && w % 5 === 0 && recent.length === 4 && recent.every(r => r.result === 'W') && p.sl < 7
          && feasible(rosters[p.team].map(id => players[id].sl + (id === p.id ? 1 : 0)))) {
        slEvents[p.id].push({ week: w + 1, from: p.sl, to: p.sl + 1, announcedWeek: w,
          note: `${p.name} moved up to SL ${p.sl + 1} after ${recent.length} wins in ${recent.length} matches.` });
        p.sl++;
      }
    }
  }

  const upcoming: RawFixture[] = schedule[LEAGUE.currentWeek - 1].map(f => ({
    home: f.home, away: f.away, homeLineup: lineup(f.home, LEAGUE.currentWeek), awayLineup: lineup(f.away, LEAGUE.currentWeek),
  }));
  // The engine replays ratings itself, so hand it ratings-free players: id, name, team and skill level only.
  const rawPlayers: RawPlayer[] = Object.values(players).map(p => ({ id: p.id, name: p.name, team: p.team, sl: p.sl, startSl: p.startSl, slEvents: slEvents[p.id] }));
  return {
    league: LEAGUE, myTeam: 0,
    teams: TEAM_DEFS.map(t => ({ name: t.name, venue: t.venue,
      short: t.name.replace(/^The /, '').split(/\s+/).filter(x => x !== '&').slice(0, 2).map(x => x[0]).join('').toUpperCase() })),
    players: rawPlayers, weeks, upcoming,
  };
}
