import { LEAGUE, MY_TEAM, powerRankings, teamRecord, teamPointsByWeek, player, upcoming, team } from '@/lib/showcase/league';
import { TeamMark, Trend, Section, Sparkline, Form, Tag, pct0, two, rankCell } from '@/components/showcase/ui';

export const metadata = { title: 'Power Rankings' };

export default function Rankings() {
  const biggestMove = [...powerRankings].sort((a, b) => Math.abs(b.prev - b.rank) - Math.abs(a.prev - a.rank))[0];
  return <>
    <section style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <span className="bc-kicker bc-amber">ULTIMATE COACH POWER INDEX · UPDATED AFTER WEEK {LEAGUE.currentWeek - 1}</span>
      <h1 className="bc-h1">Power rankings</h1>
      <p style={{ font: '500 16px var(--display)', color: 'var(--text-2)', maxWidth: 820 }}>The index blends season points per week (×5), the last three weeks of points (×3) and roster rating above 1500. {biggestMove.prev !== biggestMove.rank ? `${biggestMove.team.name} made the biggest move this week, ${biggestMove.prev > biggestMove.rank ? 'climbing' : 'falling'} from ${biggestMove.prev} to ${biggestMove.rank}.` : 'No team moved this week.'}</p>
    </section>

    <div className="bc-power">{powerRankings.map(r => {
      const rec = teamRecord(r.team.id);
      const ps = r.team.roster.map(player).sort((a, b) => b.rating - a.rating);
      const next = upcoming.find(u => u.fixture.home === r.team.id || u.fixture.away === r.team.id);
      const homeSide = next?.fixture.home === r.team.id;
      const prob = next ? (homeSide ? next.homeProb : 1 - next.homeProb) : 0;
      const spots = LEAGUE.playoffSpots;
      return <article className="bc-power-row wide" key={r.team.id}>
        <span className={`bc-power-rank bc-num ${r.rank === 1 ? 'bc-amber' : ''}`}>{two(r.rank)}</span>
        <TeamMark team={r.team} side={r.team.id === MY_TEAM ? 'home' : 'neutral'} size="sm"/>
        <div>
          <p className="bc-power-name">{r.team.name}</p>
          <p className="bc-power-meta">{rec.w}-{rec.l} · {rec.points} PTS · STANDINGS #{rankCell(rec.rank, rec.tied)} ·<Trend delta={r.prev - r.rank} suffix={r.prev - r.rank !== 0 ? ` (was ${r.prev})` : ''}/></p>
          <div style={{ marginTop: 8, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}><Form seq={rec.last5}/><Sparkline values={teamPointsByWeek(r.team.id)} width={110} height={28} tone={r.team.id === MY_TEAM ? 'cyan' : 'amber'}/></div>
        </div>
        <div className="bc-power-body">
          <p className="bc-power-blurb">{r.blurb}</p>
          <p className="bc-power-blurb" style={{ marginTop: 8 }}><strong style={{ color: 'var(--text)' }}>Top three:</strong> {ps.slice(0, 3).map(p => `${p.name} (SL ${p.sl}, ${p.wins}-${p.losses})`).join(' · ')}. <strong style={{ color: 'var(--text)' }}>Next:</strong> {next ? `${homeSide ? 'vs' : 'at'} ${team(homeSide ? next.fixture.away : next.fixture.home).name}, ${pct0(prob)} to win.` : 'on a bye this week.'}</p>
        </div>
        <div className="bc-power-stats"><b>{r.score.toFixed(1)}</b><span>INDEX</span><span>{r.recentPts.toFixed(1)} PTS/WK · L3</span><span>{Math.round(r.avgRating)} AVG RTG</span>{r.rank === 1 && <Tag tone="amber">{spots != null ? 'TITLE FAVORITE' : 'TOP OF THE INDEX'}</Tag>}{spots != null && r.rank > 1 && r.rank <= spots && <Tag tone="cyan">PLAYOFF PACE</Tag>}</div>
      </article>;
    })}</div>
  </>;
}
