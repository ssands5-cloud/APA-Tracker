import { LEAGUE, MY_TEAM, standings, teamPointsByWeek, teamPointsGrid, upcoming, team, player, allResults } from '@/lib/showcase/league';
import { TeamMark, Form, Section, Sparkline, Trend, pct0, rankCell } from '@/components/showcase/ui';

export const metadata = { title: 'Standings' };

export default function Standings() {
  const spots = LEAGUE.playoffSpots;
  const real = LEAGUE.mode === 'local-real';
  const leader = standings[0];
  const runnerUp = standings[1];
  const weeksLeft = LEAGUE.totalWeeks - LEAGUE.currentWeek + 1;
  const bestWin = [...standings].sort((a, b) => b.winPct - a.winPct)[0];
  const streakValue = (s: string) => Number(s.slice(1)) * (s[0] === 'W' ? 1 : -1);
  const hottest = [...standings].sort((a, b) => streakValue(b.streak) - streakValue(a.streak))[0];
  const ahead = leader.points - runnerUp.points;
  return <>
    <section style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <span className="bc-kicker bc-amber">{LEAGUE.season.toUpperCase()} · {LEAGUE.division.toUpperCase()} · THROUGH WEEK {LEAGUE.currentWeek - 1}</span>
      <h1 className="bc-h1">Standings</h1>
      <p style={{ font: '500 16px var(--display)', color: 'var(--text-2)' }}>
        {leader.team.name} {ahead === 0 ? `are level on points with ${runnerUp.team.name}` : `lead by ${ahead} ${ahead === 1 ? 'point' : 'points'}`} with {weeksLeft} {weeksLeft === 1 ? 'week' : 'weeks'} to play.
        {spots != null && ` Top ${spots} qualify for the session playoff.`}
      </p>
    </section>

    <div className="bc-tiles">
      <div className="bc-tile"><span>DIVISION LEADER</span><b>{leader.team.short}</b><small>{leader.w}-{leader.l} · {leader.points} pts</small></div>
      <div className="bc-tile"><span>BEST INDIVIDUAL WIN %</span><b>{pct0(bestWin.winPct)}</b><small>{bestWin.team.name}</small></div>
      <div className="bc-tile"><span>HOTTEST TEAM</span><b>{hottest.streak}</b><small>{hottest.team.name}</small></div>
      {spots != null && <div className="bc-tile"><span>PLAYOFF CUT ({spots}TH)</span><b>{standings[spots - 1].points}</b><small>{standings[spots - 1].team.name} · {standings[spots].team.short} {standings[spots - 1].points - standings[spots].points} back</small></div>}
      <div className="bc-tile"><span>WEEKS REMAINING</span><b>{weeksLeft}</b><small>{real ? `highest team score so far: ${LEAGUE.maxMatchPoints}` : `${weeksLeft * LEAGUE.maxMatchPoints} points available per team`}</small></div>
    </div>

    <Section title="Division table" kicker={real ? 'Ranked by APA session points' : 'Sorted by points, then match wins, then individual win %'}>
      <div className="bc-table-wrap"><table className="bc-table bc-compact">
        <thead><tr><th>#</th><th>TEAM</th><th className="n">W-L</th><th className="n">PTS</th><th className="n">GB</th><th className="n">PTS/WK</th><th className="n">IND W-L</th><th>STREAK</th><th>LAST 5</th><th>TREND</th><th>NEXT</th></tr></thead>
        <tbody>{standings.map((r, i) => {
          const next = upcoming.find(u => u.fixture.home === r.team.id || u.fixture.away === r.team.id);
          const homeSide = next?.fixture.home === r.team.id;
          const opp = next ? team(homeSide ? next.fixture.away : next.fixture.home) : null;
          const prob = next ? (homeSide ? next.homeProb : 1 - next.homeProb) : 0;
          return <tr key={r.team.id} className={`${r.team.id === MY_TEAM ? 'mine' : ''} ${spots != null && i === spots ? 'cut' : ''}`}>
            <td className="rank">{rankCell(r.rank, r.tied)}</td>
            <td><span className="team"><TeamMark team={r.team} side={r.team.id === MY_TEAM ? 'home' : 'neutral'} size="sm"/>{r.team.name}</span></td>
            <td className="n mono">{r.w}-{r.l}</td><td className="n mono"><b>{r.points}</b></td>
            <td className="n mono">{r.behind === 0 ? '—' : r.behind}</td><td className="n mono">{r.pointsPerWeek.toFixed(1)}</td>
            <td className="n mono">{r.indivW}-{r.indivL} · {pct0(r.winPct)}</td>
            <td className="mono">{r.streak}</td><td><Form seq={r.last5}/></td>
            <td><Sparkline values={teamPointsByWeek(r.team.id)} width={90} height={26} tone={r.team.id === MY_TEAM ? 'cyan' : 'amber'}/></td>
            <td className="mono">{opp ? `${homeSide ? 'vs' : 'at'} ${opp.short} · ${pct0(prob)}` : 'BYE'}</td>
          </tr>;
        })}</tbody>
      </table></div>
      <p className="bc-muted">{real
        ? `Rank and PTS are APA’s own session standings, which include bye-week points; ties share a rank. W-L, individual records and the trend line are computed from the ${allResults.length} published scoresheets. GB counts points behind the leader.`
        : `${spots != null ? 'Dashed line marks the playoff cut. ' : ''}GB counts points behind the leader; ${LEAGUE.maxMatchPoints} points are available in each team match (3 per individual match, plus bonus points).`}</p>
    </Section>

    <Section title="Points by week" kicker="Every team, every week · — is a bye">
      <div className="bc-table-wrap"><table className="bc-table bc-heat">
        <thead><tr><th>TEAM</th>{[...Array(LEAGUE.currentWeek - 1).keys()].map(i => <th key={i} className="n">W{i + 1}</th>)}<th className="n">AVG</th><th className="n">HIGH</th><th className="n">LOW</th></tr></thead>
        <tbody>{standings.map(r => {
          const grid = teamPointsGrid(r.team.id); const pts = grid.filter((v): v is number => v != null);
          return <tr key={r.team.id} className={r.team.id === MY_TEAM ? 'mine' : ''}>
            <td><span className="team"><TeamMark team={r.team} side={r.team.id === MY_TEAM ? 'home' : 'neutral'} size="sm"/>{r.team.short}</span></td>
            {grid.map((p, i) => p == null ? <td key={i} className="h" style={{ background: 'var(--surface-3)', color: 'var(--text-3)' }}>—</td> : <td key={i} className="h" style={{ background: heat(p, LEAGUE.maxMatchPoints) }}>{p}</td>)}
            <td className="n mono">{pts.length ? (pts.reduce((a, b) => a + b, 0) / pts.length).toFixed(1) : '—'}</td><td className="n mono">{pts.length ? Math.max(...pts) : '—'}</td><td className="n mono">{pts.length ? Math.min(...pts) : '—'}</td>
          </tr>;
        })}</tbody>
      </table></div>
    </Section>

    <Section title="Roster strength" kicker="Average rating and skill level per team">
      <div className="bc-tiles">{standings.map(r => { const ps = r.team.roster.map(player); const avg = Math.round(ps.reduce((s, p) => s + p.rating, 0) / Math.max(ps.length, 1)); const top = [...ps].sort((a, b) => b.rating - a.rating)[0];
        return <div className="bc-tile" key={r.team.id}><span>{r.team.short} · RANK {rankCell(r.rank, r.tied)}</span><b>{avg}</b><small>avg rating · SL {(ps.reduce((s, p) => s + p.sl, 0) / Math.max(ps.length, 1)).toFixed(1)} · best {top.name.split(' ').slice(-1)[0]} {top.rating}</small><Trend delta={avg - 1500}/></div>; })}</div>
    </Section>
  </>;
}

function heat(p: number, max: number): string {
  const t = Math.min(Math.max((p - 3) / Math.max(max - 3, 1), 0), 1);
  return `oklch(${0.55 + t * 0.3} ${0.06 + t * 0.09} ${205 - t * 10})`;
}
