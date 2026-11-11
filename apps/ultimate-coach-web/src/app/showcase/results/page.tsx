import { LEAGUE, MY_TEAM, weeks, resultsByWeek, team, player, weekStars, leagueAvgByWeek, teamPointsGrid, allPlayers, allTeams } from '@/lib/showcase/league';
import { TeamMark, Section, Tag, pct0 } from '@/components/showcase/ui';

export const metadata = { title: 'Results & Stats' };

export default async function Results({ searchParams }: { searchParams: Promise<{ week?: string }> }) {
  const requested = Number((await searchParams).week);
  const week = weeks.includes(requested) ? requested : LEAGUE.currentWeek - 1;
  const matches = resultsByWeek(week);
  const stars = weekStars(week);
  const avg = leagueAvgByWeek();
  const grid = teamPointsGrid(MY_TEAM);
  const played = grid.map((v, i) => ({ v, w: i + 1 })).filter((x): x is { v: number; w: number } => x.v != null);
  const best = played.reduce((a, b) => (b.v > a.v ? b : a), played[0]);
  const worst = played.reduce((a, b) => (b.v < a.v ? b : a), played[0]);
  const games = matches.flatMap(m => m.games);
  const gameCount = Math.max(games.length, 1);
  const winnerProb = (g: (typeof games)[number]) => (g.winner === g.home ? g.homeProb : 1 - g.homeProb);
  const upsets = games.filter(g => winnerProb(g) < 0.4).length;
  const shutouts = games.filter(g => Math.max(g.homePts, g.awayPts) >= LEAGUE.maxGamePoints && Math.min(g.homePts, g.awayPts) === 0).length;
  const favorites = games.filter(g => winnerProb(g) >= 0.5).length;
  const slMoves = allPlayers.filter(p => p.weekly.some(w => w.week === week) && p.sl !== p.startSl).length;
  const byes = allTeams.filter(t => !matches.some(m => m.home === t.id || m.away === t.id));
  const mineThisWeek = grid[week - 1];
  const topMatch = [...matches].sort((x, y) => (y.homePts + y.awayPts) - (x.homePts + x.awayPts))[0];
  return <>
    <section style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <span className="bc-kicker bc-amber">{LEAGUE.division.toUpperCase()} · {LEAGUE.season.toUpperCase()}</span>
      <h1 className="bc-h1">Results</h1>
      <nav className="bc-weeks" aria-label="Week">{weeks.map(w => <a key={w} href={`/showcase/results?week=${w}`} aria-current={w === week ? 'page' : undefined}>WK {w}</a>)}</nav>
    </section>

    <div className="bc-tiles">
      <div className="bc-tile"><span>WEEK {week} · LEAGUE AVG</span><b>{avg[week - 1].toFixed(2)}</b><small>points per team match</small></div>
      <div className="bc-tile"><span>FAVORITES WON</span><b>{favorites}/{games.length}</b><small>{pct0(favorites / gameCount)} of individual matches</small></div>
      <div className="bc-tile"><span>UPSETS</span><b>{upsets}</b><small>winner had under 40% going in</small></div>
      <div className="bc-tile"><span>SHUTOUTS</span><b>{shutouts}</b><small>{LEAGUE.maxGamePoints}-0 individual results</small></div>
      <div className="bc-tile"><span>{team(MY_TEAM).short} THIS WEEK</span><b>{mineThisWeek ?? 'BYE'}</b><small>{mineThisWeek == null ? 'no match this week' : `${mineThisWeek >= avg[week - 1] ? 'above' : 'below'} league average`}</small></div>
    </div>

    <Section title={`Week ${week} scoreboard`} kicker="Team points · individual matches">
      <div className="bc-grid-2" style={{ gridTemplateColumns: '1fr 1fr' }}>{matches.map(m => {
        const h = team(m.home), a = team(m.away);
        const homeWon = m.homePts > m.awayPts || (m.homePts === m.awayPts && m.homeWins > m.awayWins);
        return <article className="bc-result" key={`${m.home}-${m.away}`}>
          <div className="bc-result-head">
            <span className={`t ${homeWon ? 'win' : 'loss'}`}><TeamMark team={h} side="home" size="sm"/><span className="nm">{h.name}</span><strong>{m.homePts}</strong></span>
            <span className="fin">FINAL<br/>{m.homeWins}-{m.awayWins} IND</span>
            <span className={`t away ${homeWon ? 'loss' : 'win'}`}><strong>{m.awayPts}</strong><span className="nm">{a.name}</span><TeamMark team={a} side="away" size="sm"/></span>
          </div>
          <div className="bc-result-games">{m.games.map((g, i) => { const hp = player(g.home), ap = player(g.away); const hw = g.winner === g.home;
            return <div className="bc-game" key={i}>
              <span className={`p ${hw ? 'win' : 'loss'}`}><span className={`bc-sl bc-sl-${hp.sl}`}>{hp.sl}</span><span className="nm">{hp.name}</span></span>
              <span className="s">{g.homePts}–{g.awayPts}<small>{pct0(g.homeProb)} · {pct0(1 - g.homeProb)}</small></span>
              <span className={`p away ${hw ? 'loss' : 'win'}`}><span className={`bc-sl bc-sl-${ap.sl}`}>{ap.sl}</span><span className="nm">{ap.name}</span></span>
            </div>; })}</div>
          <div style={{ padding: '10px 18px', borderTop: '1px solid var(--line)', display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }} className="bc-muted"><span>Pre-match: {h.short} {pct0(m.homeProb)} · {a.short} {pct0(1 - m.homeProb)}</span>{(homeWon ? m.homeProb : 1 - m.homeProb) < 0.4 ? <Tag tone="coral">UPSET</Tag> : <Tag tone="grey">{(homeWon ? m.homeProb : 1 - m.homeProb) >= 0.6 ? 'AS EXPECTED' : 'CLOSE CALL'}</Tag>}</div>
        </article>;
      })}</div>
      {byes.length > 0 && <p className="bc-muted">On a bye in week {week}: {byes.map(t => t.name).join(', ')}.</p>}
    </Section>

    <div className="bc-grid-2">
      <Section title="Weekly scoring" kicker={`${team(MY_TEAM).name} vs league average`}>
        <div className="bc-chart">{weeks.map(w => { const v = grid[w - 1]; return <div key={w}><b>{v ?? 'BYE'}</b>{v != null && <i className="me" style={{ height: `${(v / Math.max(LEAGUE.maxMatchPoints, 1)) * 100}%` }}/>}<small>W{w}</small></div>; })}</div>
        {best && worst && <div className="bc-legend"><span><i style={{ background: 'var(--cyan)' }}/>{team(MY_TEAM).short} points</span><span>League average {(avg.reduce((a, b) => a + b, 0) / avg.length).toFixed(2)} · season high {best.v} (wk {best.w}) · low {worst.v} (wk {worst.w})</span></div>}
        <div className="bc-table-wrap"><table className="bc-table bc-compact">
          <thead><tr><th>WEEK</th>{weeks.map(w => <th key={w} className="n">{w}</th>)}</tr></thead>
          <tbody>
            <tr><td className="mono">{team(MY_TEAM).short}</td>{grid.map((v, i) => <td key={i} className="n mono"><b>{v ?? '—'}</b></td>)}</tr>
            <tr><td className="mono">LEAGUE AVG</td>{avg.map((v, i) => <td key={i} className="n mono">{v.toFixed(1)}</td>)}</tr>
            <tr><td className="mono">DIFF</td>{grid.map((v, i) => v == null ? <td key={i} className="n mono">—</td> : <td key={i} className={`n mono ${v - avg[i] >= 0 ? 'bc-trend-up' : 'bc-trend-down'}`}>{v - avg[i] >= 0 ? '+' : ''}{(v - avg[i]).toFixed(1)}</td>)}</tr>
          </tbody>
        </table></div>
      </Section>
      <Section title={`Week ${week} stars`} kicker="Highest-scoring winners, rating gain as tiebreak">
        <div className="bc-leader"><ol>{stars.map((s, i) => <li key={s.p.id}><span>{i + 1}</span><span><strong>{s.p.name}</strong><small>SL {s.p.sl} · {team(s.p.team).name} · def. {s.g!.opp}</small></span><b>{s.g!.points} PTS · {s.d >= 0 ? '+' : ''}{s.d}</b></li>)}</ol></div>
        <div className="bc-card">
          <span className="bc-kicker">WEEK {week} IN NUMBERS</span>
          <p className="bc-power-blurb" style={{ marginTop: 8 }}>{games.length} individual matches were played across {matches.length} team matches. Favorites won {favorites} of them ({pct0(favorites / gameCount)}), with {upsets} {upsets === 1 ? 'upset' : 'upsets'} and {shutouts} {shutouts === 1 ? 'shutout' : 'shutouts'}. {topMatch ? `The highest-scoring team match was ${team(topMatch.home).short} ${topMatch.homePts}–${topMatch.awayPts} ${team(topMatch.away).short}. ` : ''}{slMoves} {slMoves === 1 ? 'player who played this week has' : 'players who played this week have'} changed skill level this session.</p>
        </div>
      </Section>
    </div>
  </>;
}
