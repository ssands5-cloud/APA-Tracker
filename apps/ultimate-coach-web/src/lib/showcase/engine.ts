/**
 * Showcase engine. Takes ONE season of already-decided games (simulated, or the owner's own
 * local export) and derives every number the ESPN-style screens show: ratings replayed game by
 * game, standings, power index, projected lineups and win probabilities, leaders and a feed.
 *
 * Win probabilities are this engine's own rating model. They are not the production evidence
 * engine and they are not calibrated.
 */
import type {
  ActivityItem, Fixture, IndividualMatch, Player, PowerRow, Preview, RawSeason, StandingRow, Team, TeamMatch,
} from './types.ts';

const K = 28;

export function playerWinProb(a: Player, b: Player): number { return 1 / (1 + 10 ** ((b.rating - a.rating) / 400)); }

/** Probability the first team wins the team match (a majority of its individual matches). */
export function teamWinProb(probs: number[]): number {
  let dist = [1];
  for (const p of probs) {
    const next = new Array(dist.length + 1).fill(0);
    dist.forEach((v, k) => { next[k] += v * (1 - p); next[k + 1] += v * p; });
    dist = next;
  }
  const need = Math.floor(probs.length / 2) + 1;
  return dist.slice(need).reduce((a, b) => a + b, 0);
}

export function winPct(p: Player): number { return p.played ? p.wins / p.played : 0; }
export function ppm(p: Player): number { return p.played ? p.points / p.played : 0; }
export function ratingTrend(p: Player, span = 3): number { const h = p.ratingHistory; return h[h.length - 1] - h[Math.max(0, h.length - 1 - span)]; }

/** The best-rated five whose skill levels fit under the cap (exact search); the cheapest five if none fit. */
export function bestLegalFive(pool: Player[], cap: number): Player[] {
  const sorted = [...pool].sort((x, y) => y.rating - x.rating || (x.id < y.id ? -1 : 1));
  const size = Math.min(5, sorted.length);
  let best: Player[] | null = null, bestRating = -Infinity, cheapest: Player[] = [], cheapestSl = Infinity;
  const walk = (start: number, chosen: Player[]) => {
    if (chosen.length === size) {
      const sl = chosen.reduce((s, c) => s + c.sl, 0), rating = chosen.reduce((s, c) => s + c.rating, 0);
      if (sl <= cap && rating > bestRating) { best = [...chosen]; bestRating = rating; }
      if (sl < cheapestSl) { cheapest = [...chosen]; cheapestSl = sl; }
      return;
    }
    for (let i = start; i < sorted.length; i++) { chosen.push(sorted[i]); walk(i + 1, chosen); chosen.pop(); }
  };
  walk(0, []);
  return [...(best ?? cheapest)].sort((x, y) => y.rating - x.rating);
}

export function buildSeason(raw: RawSeason) {
  const LEAGUE = raw.league;
  const MY_TEAM = raw.myTeam;
  const teams: Team[] = raw.teams.map((t, i) => ({ id: i, name: t.name, short: t.short, venue: t.venue, roster: [] }));
  const players: Record<string, Player> = {};
  const rawPlayers = new Map(raw.players.map(p => [p.id, p]));
  for (const rp of raw.players) {
    players[rp.id] = { id: rp.id, name: rp.name, team: rp.team, sl: rp.sl, startSl: rp.startSl, rating: 1500, ratingHistory: [1500],
      played: 0, wins: 0, losses: 0, points: 0, shutouts: 0, form: [], weekly: [] };
    teams[rp.team].roster.push(rp.id);
  }
  const slAt = (id: string, week: number): number => {
    const rp = rawPlayers.get(id)!;
    let sl = rp.startSl;
    for (const e of rp.slEvents) if (e.week <= week) sl = e.to;
    return sl;
  };

  /* ── Replay every played game in order ────────────────────────────────────── */
  const results: TeamMatch[] = [];
  const activity: ActivityItem[] = [];
  for (const rw of [...raw.weeks].sort((a, b) => a.week - b.week)) {
    const w = rw.week;
    for (const m of rw.matches) {
      const games: IndividualMatch[] = [];
      const probs: number[] = [];
      for (const g of m.games) {
        const a = players[g.home], b = players[g.away];
        const shown = playerWinProb(a, b);
        probs.push(shown);
        const homeWon = g.winner === g.home;
        const [winner, loser] = homeWon ? [a, b] : [b, a];
        const [wp, lp] = homeWon ? [g.homePts, g.awayPts] : [g.awayPts, g.homePts];
        winner.wins++; loser.losses++; winner.played++; loser.played++;
        winner.points += wp; loser.points += lp;
        if (lp === 0 && wp >= LEAGUE.maxGamePoints) winner.shutouts++;
        winner.form.push('W'); loser.form.push('L');
        winner.weekly.push({ week: w, result: 'W', points: wp, opp: loser.name });
        loser.weekly.push({ week: w, result: 'L', points: lp, opp: winner.name });
        const expectW = playerWinProb(winner, loser);
        const delta = Math.round(K * (1 - expectW));
        winner.rating += delta; loser.rating -= delta;
        games.push({ home: g.home, away: g.away, homePts: g.homePts, awayPts: g.awayPts, winner: g.winner, homeProb: shown });
        const wSl = slAt(winner.id, w), lSl = slAt(loser.id, w);
        if (expectW < 0.36) activity.push({ week: w, kind: 'upset', team: winner.team,
          text: `${winner.name} (SL ${wSl}) upset ${loser.name} (SL ${lSl}) — a ${Math.round(expectW * 100)}% underdog going in.` });
        if (lp === 0 && wp >= LEAGUE.maxGamePoints && wSl <= 3) activity.push({ week: w, kind: 'shutout', team: winner.team,
          text: `${winner.name} (SL ${wSl}) pitched a ${wp}-0 shutout over ${loser.name}.` });
      }
      results.push({ week: w, home: m.home, away: m.away, homePts: m.homePts, awayPts: m.awayPts, homeWins: m.homeWins, awayWins: m.awayWins,
        games, homeProb: teamWinProb(probs) });
      if (m.homeWins === 5 || m.awayWins === 5) {
        const t = m.homeWins === 5 ? m.home : m.away;
        activity.push({ week: w, kind: 'sweep', team: t, text: `${teams[t].name} swept ${teams[t === m.home ? m.away : m.home].name} 5-0 in individual matches.` });
      }
    }
    for (const p of Object.values(players)) {
      p.ratingHistory.push(p.rating);
      const last5 = p.form.slice(-5);
      const playedThisWeek = p.weekly.some(x => x.week === w);
      if (playedThisWeek && last5.length === 5 && last5.every(r => r === 'W') && p.form.slice(-6, -5)[0] !== 'W')
        activity.push({ week: w, kind: 'streak', team: p.team, text: `${p.name} is on a 5-match win streak for ${teams[p.team].name}.` });
      if (playedThisWeek && p.wins === 10 && p.form[p.form.length - 1] === 'W')
        activity.push({ week: w, kind: 'milestone', team: p.team, text: `${p.name} reached 10 wins this season.` });
    }
  }
  for (const rp of raw.players) {
    for (const e of rp.slEvents) {
      activity.push({ week: e.announcedWeek ?? e.week, kind: 'skill', team: rp.team,
        text: e.note ?? `${rp.name} moved ${e.to > e.from ? 'up' : 'down'} to SL ${e.to} (was SL ${e.from}).` });
    }
  }
  // Skill level shown for a player is the one in force now.
  for (const p of Object.values(players)) p.sl = slAt(p.id, Number.MAX_SAFE_INTEGER);

  /* ── Standings ───────────────────────────────────────────────────────────── */
  function standingsThrough(week: number): StandingRow[] {
    const rows: StandingRow[] = teams.map(team => {
      const ms = results.filter(m => m.week <= week && (m.home === team.id || m.away === team.id));
      let w = 0, l = 0, pts = 0, iw = 0, il = 0; const seq: ('W' | 'L')[] = [];
      for (const m of ms) {
        const home = m.home === team.id;
        const mine = home ? m.homePts : m.awayPts, theirs = home ? m.awayPts : m.homePts;
        const myWins = home ? m.homeWins : m.awayWins, theirWins = home ? m.awayWins : m.homeWins;
        const won = mine > theirs || (mine === theirs && myWins > theirWins);
        if (won) w++; else l++;
        seq.push(won ? 'W' : 'L'); pts += mine; iw += myWins; il += theirWins;
      }
      let s = 0; const last = seq[seq.length - 1];
      for (let i = seq.length - 1; i >= 0 && seq[i] === last; i--) s++;
      return { team, rank: 0, tied: false, w, l, points: pts, pointsPerWeek: ms.length ? pts / ms.length : 0, indivW: iw, indivL: il,
        winPct: iw + il ? iw / (iw + il) : 0, streak: last ? `${last}${s}` : '—', last5: seq.slice(-5), behind: 0, matchesPlayed: ms.length };
    });
    rows.sort((a, b) => b.points - a.points || b.w - a.w || b.winPct - a.winPct);
    rows.forEach((r, i) => { r.rank = i + 1; r.behind = rows[0].points - r.points; });
    return rows;
  }
  const computedStandings = standingsThrough(LEAGUE.currentWeek - 1);
  const previousStandings = standingsThrough(LEAGUE.currentWeek - 2);

  /** In real data the league's own table decides rank and points; W-L still comes from the scoresheets. */
  function applyApa(rows: StandingRow[]): StandingRow[] {
    if (!raw.apaStandings?.length) return rows;
    const apa = new Map(raw.apaStandings.map(a => [a.team, a]));
    const out = rows.map(r => {
      const a = apa.get(r.team.id);
      return a ? { ...r, rank: a.rank, tied: !!a.tied, points: a.points, pointsPerWeek: a.points / Math.max(LEAGUE.currentWeek - 1, 1) } : r;
    });
    out.sort((x, y) => x.rank - y.rank || y.points - x.points || y.w - x.w);
    const top = Math.max(...out.map(r => r.points));
    out.forEach(r => { r.behind = top - r.points; });
    return out;
  }
  const standings = applyApa(computedStandings);

  /* ── Power rankings (always from scoresheet results, so week-over-week is comparable) ── */
  function power(week: number, table: StandingRow[]): PowerRow[] {
    const rows = table.map(row => {
      const window = results.filter(m => m.week > week - 3 && m.week <= week && (m.home === row.team.id || m.away === row.team.id));
      const recent = window.reduce((s, m) => s + (m.home === row.team.id ? m.homePts : m.awayPts), 0) / Math.max(window.length, 1);
      const roster = row.team.roster.map(id => players[id]);
      const avgRating = roster.reduce((s, p) => s + p.ratingHistory[Math.min(week, p.ratingHistory.length - 1)], 0) / Math.max(roster.length, 1);
      const score = row.pointsPerWeek * 5 + recent * 3 + (avgRating - 1500) / 6;
      return { team: row.team, rank: 0, prev: 0, score, avgRating, recentPts: recent, blurb: '' };
    });
    rows.sort((a, b) => b.score - a.score);
    rows.forEach((r, i) => { r.rank = i + 1; });
    return rows;
  }
  const prevPower = power(LEAGUE.currentWeek - 2, previousStandings);
  const powerRankings: PowerRow[] = power(LEAGUE.currentWeek - 1, computedStandings).map(row => {
    const prev = prevPower.find(p => p.team.id === row.team.id)!.rank;
    const st = standings.find(s => s.team.id === row.team.id)!;
    const star = row.team.roster.map(id => players[id]).sort((a, b) => b.rating - a.rating)[0];
    const move = prev - row.rank;
    const trend = move > 0 ? `Up ${move} after` : move < 0 ? `Down ${-move} after` : 'Holding steady after';
    const lastMatch = [...results].reverse().find(m => m.home === row.team.id || m.away === row.team.id);
    let form = '';
    if (lastMatch) {
      const home = lastMatch.home === row.team.id;
      const opp = teams[home ? lastMatch.away : lastMatch.home];
      const mine = home ? lastMatch.homePts : lastMatch.awayPts, theirs = home ? lastMatch.awayPts : lastMatch.homePts;
      const myWins = home ? lastMatch.homeWins : lastMatch.awayWins, theirWins = home ? lastMatch.awayWins : lastMatch.homeWins;
      const won = mine > theirs || (mine === theirs && myWins > theirWins);
      const bye = lastMatch.week < LEAGUE.currentWeek - 1;
      form = `${bye ? 'Coming off a bye after' : trend} a ${mine}-${theirs} ${won ? 'win over' : 'loss to'} ${opp.name}${bye ? ` in week ${lastMatch.week}` : ''}${mine === theirs ? ` (decided ${myWins}-${theirWins} on individual matches)` : ''}.`;
    }
    const streak = st.streak.startsWith('W') ? `${st.streak.slice(1)}-match win streak` : `${st.streak.slice(1)}-match skid`;
    const blurb = `${form} ${star ? `${star.name} (SL ${star.sl}, ${star.rating} rating) leads the roster; ` : ''}the team is ${st.w}-${st.l} with a ${streak}.`.trim();
    return { ...row, prev, blurb };
  });

  /* ── Upcoming week ───────────────────────────────────────────────────────── */
  const allGames = results.flatMap(r => r.games);
  const winPts = allGames.map(g => (g.winner === g.home ? g.homePts : g.awayPts));
  const losePts = allGames.map(g => (g.winner === g.home ? g.awayPts : g.homePts));
  const avgWin = winPts.length ? winPts.reduce((a, b) => a + b, 0) / winPts.length : 2.2;
  const avgLose = losePts.length ? losePts.reduce((a, b) => a + b, 0) / losePts.length : 0.6;
  const projectedPoints = (p: number): [number, number] => [p * avgWin + (1 - p) * avgLose, (1 - p) * avgWin + p * avgLose];

  /** Players who have appeared in the team's last five matches (everyone, if that is fewer than five people). */
  function recentRegulars(team: number): Player[] {
    const mine = results.filter(m => m.home === team || m.away === team).slice(-5);
    const seen = new Set<string>();
    for (const m of mine) for (const g of m.games) seen.add(teams[team].roster.includes(g.home) ? g.home : g.away);
    const pool = teams[team].roster.filter(id => seen.has(id)).map(id => players[id]);
    return pool.length >= 5 ? pool : teams[team].roster.map(id => players[id]);
  }
  const predictLineup = (team: number) => bestLegalFive(recentRegulars(team), LEAGUE.cap).map(p => p.id);

  const upcoming: Preview[] = raw.upcoming.map(f => {
    const homeLineup = f.homeLineup ?? predictLineup(f.home), awayLineup = f.awayLineup ?? predictLineup(f.away);
    const n = Math.min(homeLineup.length, awayLineup.length);
    const pairProbs = homeLineup.slice(0, n).map((id, i) => playerWinProb(players[id], players[awayLineup[i]]));
    const proj = pairProbs.map(projectedPoints);
    const fixture: Fixture = { week: LEAGUE.currentWeek, home: f.home, away: f.away };
    return { fixture, homeLineup: homeLineup.slice(0, n), awayLineup: awayLineup.slice(0, n), pairProbs, homeProb: teamWinProb(pairProbs),
      projHome: proj.reduce((s, x) => s + x[0], 0), projAway: proj.reduce((s, x) => s + x[1], 0) };
  });
  const playingNext = new Set(upcoming.flatMap(u => [u.fixture.home, u.fixture.away]));
  const byeTeams = teams.filter(t => !playingNext.has(t.id));
  const featured: Preview = upcoming.find(u => u.fixture.home === MY_TEAM || u.fixture.away === MY_TEAM) ?? upcoming[0];
  const myTeamOnBye = !playingNext.has(MY_TEAM);

  /* ── Weekly stats and leaders ─────────────────────────────────────────────── */
  const weeks = [...Array(LEAGUE.currentWeek - 1).keys()].map(i => i + 1);
  const teamPointsGrid = (team: number): (number | null)[] => weeks.map(w => {
    const m = results.find(r => r.week === w && (r.home === team || r.away === team));
    return m ? (m.home === team ? m.homePts : m.awayPts) : null;
  });
  const teamPointsByWeek = (team: number): number[] => teamPointsGrid(team).filter((v): v is number => v != null);
  const leagueAvgByWeek = (): number[] => weeks.map(w => {
    const ms = results.filter(r => r.week === w);
    return ms.length ? ms.reduce((s, m) => s + m.homePts + m.awayPts, 0) / (ms.length * 2) : 0;
  });
  const weekStars = (week: number) => Object.values(players)
    .map(p => ({ p, g: p.weekly.find(x => x.week === week), d: p.ratingHistory[week] - p.ratingHistory[week - 1] }))
    .filter(x => x.g?.result === 'W').sort((a, b) => b.g!.points - a.g!.points || b.d - a.d).slice(0, 3);

  const allPlayers = Object.values(players);
  const feed = activity.filter(a => a.week >= LEAGUE.currentWeek - 3).sort((a, b) => b.week - a.week).slice(0, 14);
  const headToHead = (a: Player, b: Player) => {
    const games = allGames.filter(g => (g.home === a.id && g.away === b.id) || (g.home === b.id && g.away === a.id));
    return { aWins: games.filter(g => g.winner === a.id).length, bWins: games.filter(g => g.winner === b.id).length };
  };

  return {
    LEAGUE, MY_TEAM, provenance: raw.provenance ?? null,
    standings, powerRankings, upcoming, featured, myTeamOnBye, byeTeams, feed, weeks,
    allPlayers, allTeams: teams, allResults: results,
    player: (id: string) => players[id],
    team: (id: number) => teams[id],
    teamRecord: (t: number) => standings.find(s => s.team.id === t)!,
    resultsByWeek: (w: number) => results.filter(r => r.week === w),
    weekStars, teamPointsByWeek, teamPointsGrid, leagueAvgByWeek, headToHead,
  };
}
