import { LEAGUE, MY_TEAM, featured, upcoming, standings, powerRankings, feed, team, teamRecord, weekStars, allPlayers, ratingTrend, allResults, teamPointsByWeek, byeTeams, myTeamOnBye } from '@/lib/showcase/league';
import { TeamMark, Tag, Trend, ProbBar, Form, Section, Pairing, Sparkline, pct, pct0, two, rankText, rankCell } from '@/components/showcase/ui';

const KIND: Record<string, { tone: 'cyan' | 'coral' | 'amber' | 'grey' | 'green'; label: string }> = {
  upset: { tone: 'coral', label: 'UPSET' }, shutout: { tone: 'cyan', label: 'SHUTOUT' }, streak: { tone: 'amber', label: 'STREAK' },
  skill: { tone: 'green', label: 'SL MOVE' }, sweep: { tone: 'cyan', label: 'SWEEP' }, milestone: { tone: 'grey', label: 'MILESTONE' }, clinch: { tone: 'amber', label: 'CLINCH' },
};

export default function ShowcaseHome() {
  const home = team(featured.fixture.home), away = team(featured.fixture.away);
  const hr = teamRecord(home.id), ar = teamRecord(away.id);
  const stars = weekStars(LEAGUE.currentWeek - 1);
  const risers = [...allPlayers].sort((a, b) => ratingTrend(b) - ratingTrend(a)).slice(0, 3);
  const mine = standings.find(s => s.team.id === MY_TEAM)!;
  return <>
    <h1 className="bc-sr">Ultimate Coach showcase · Week {LEAGUE.currentWeek} matchup</h1>
    <section className="bc-board" aria-label="Featured matchup">
      <div className="bc-board-grid">
        <div className="bc-board-side home">
          <span className="bc-kicker home">{featured.fixture.home === MY_TEAM ? 'HOME · YOUR TEAM' : 'HOME'}</span>
          <TeamMark team={home} side="home" size="xl"/>
          <span className="bc-board-name">{home.name}</span>
          <span className="bc-board-record">{hr.w}-{hr.l} · {hr.points} PTS · {rankText(hr.rank, hr.tied).toUpperCase()} · {hr.streak}</span>
        </div>
        <div className="bc-board-center">
          <Tag tone="amber">PRE-MATCH</Tag>
          <span className="bc-vs">VS</span>
          <span className="bc-board-when">{LEAGUE.matchDate.toUpperCase()} · {LEAGUE.matchTime.toUpperCase()}</span>
        </div>
        <div className="bc-board-side away">
          <span className="bc-kicker away">{featured.fixture.away === MY_TEAM ? 'AWAY · YOUR TEAM' : 'AWAY · OPPONENT'}</span>
          <TeamMark team={away} side="away" size="xl"/>
          <span className="bc-board-name">{away.name}</span>
          <span className="bc-board-record">{ar.w}-{ar.l} · {ar.points} PTS · {rankText(ar.rank, ar.tied).toUpperCase()} · {ar.streak}</span>
        </div>
      </div>
      <div className="bc-board-prob">
        <div className="bc-board-prob-row">
          <span><small>WIN PROBABILITY</small>{pct(featured.homeProb)}</span>
          <span><small>PROJECTED {featured.projHome.toFixed(1)} – {featured.projAway.toFixed(1)}</small>{pct(1 - featured.homeProb)}</span>
        </div>
        <ProbBar home={featured.homeProb} away={1 - featured.homeProb} thick/>
      </div>
      <div className="bc-facts">
        <div><span>MATCH DATE</span><span>{LEAGUE.matchDate.replace(', 2026', '')}</span></div>
        <div><span>FORMAT</span><span>{LEAGUE.format}</span></div>
        <div><span>SKILL CAP</span><span>{LEAGUE.cap}</span></div>
        <div><span>VENUE</span><span>{home.venue ?? 'Not captured'}</span></div>
        <div><span>SEASON SERIES</span><span>{seriesText(home.id, away.id)}</span></div>
      </div>
    </section>

    <Section title="Key matchups" kicker={`Projected lineups · ${home.short} vs ${away.short}`} action={{ href: '/showcase/matchup', label: 'FULL MATCHUP' }}>
      <div className="bc-pairs">{featured.homeLineup.map((id, i) => <Pairing key={id} no={i + 1} homeId={id} awayId={featured.awayLineup[i]} href={`/showcase/matchup?pick=${i}`}/>)}</div>
      <p className="bc-muted">{LEAGUE.mode === 'local-real'
        ? 'Win probabilities are a rating-model estimate replayed from this division’s real results, not calibrated. Lineups assume each captain plays the best-rated legal five among players who appeared in their last five matches, paired in rating order; real pairings are set at the table.'
        : 'Probabilities come from the showcase rating model fed by this simulated season. Pairings assume each captain plays the projected five in rating order.'}
        {myTeamOnBye && ` ${team(MY_TEAM).name} are on a bye this week, so the featured matchup is the first on the slate.`}</p>
    </Section>

    <div className="bc-grid-2">
      <Section title={`Week ${LEAGUE.currentWeek} slate`} kicker="All division matchups">
        <div className="bc-slate">{upcoming.map(u => {
          const h = team(u.fixture.home), a = team(u.fixture.away), hrr = teamRecord(h.id), arr = teamRecord(a.id);
          const isFeatured = u === featured;
          return <a key={h.id} href={isFeatured ? '/showcase/matchup' : `/showcase/matchup?game=${u.fixture.home}`} className={isFeatured ? 'featured' : ''}>
            <div className="row"><span className="row"><TeamMark team={a} side="away" size="sm"/><strong>{a.name}</strong></span><span className="pr bc-coral">{pct0(1 - u.homeProb)}</span></div>
            <div className="row"><span className="row"><TeamMark team={h} side="home" size="sm"/><strong>{h.name}</strong></span><span className="pr bc-cyan">{pct0(u.homeProb)}</span></div>
            <ProbBar home={u.homeProb} away={1 - u.homeProb}/>
            <div className="row"><small>{arr.w}-{arr.l} at {hrr.w}-{hrr.l}{h.venue ? ` · ${h.venue}` : ''}</small><small>PROJ {u.projAway.toFixed(1)}–{u.projHome.toFixed(1)}</small></div>
          </a>;
        })}</div>
        {byeTeams.length > 0 && <p className="bc-muted">On a bye: {byeTeams.map(t => t.name).join(', ')}.</p>}
      </Section>
      <Section title="Standings" kicker={`${LEAGUE.division} · through week ${LEAGUE.currentWeek - 1}`} action={{ href: '/showcase/standings', label: 'FULL TABLE' }}>
        <div className="bc-table-wrap"><table className="bc-table bc-compact">
          <thead><tr><th>#</th><th>TEAM</th><th className="n">W-L</th><th className="n">PTS</th><th>LAST 5</th></tr></thead>
          <tbody>{standings.map(r => <tr key={r.team.id} className={r.team.id === MY_TEAM ? 'mine' : ''}>
            <td className="rank">{rankCell(r.rank, r.tied)}</td>
            <td><span className="team"><TeamMark team={r.team} side={r.team.id === MY_TEAM ? 'home' : 'neutral'} size="sm"/><span className="team-name">{r.team.name}</span></span></td>
            <td className="n mono">{r.w}-{r.l}</td><td className="n mono"><b>{r.points}</b></td><td><Form seq={r.last5}/></td>
          </tr>)}</tbody>
        </table></div>
      </Section>
    </div>

    <div className="bc-grid-2">
      <Section title="Power rankings" kicker="Ultimate Coach index · weekly" action={{ href: '/showcase/rankings', label: `ALL ${powerRankings.length}` }}>
        <div className="bc-power">{powerRankings.slice(0, 5).map(r => <div className="bc-power-row" key={r.team.id}>
          <span className="bc-power-rank bc-num">{two(r.rank)}</span>
          <TeamMark team={r.team} side={r.team.id === MY_TEAM ? 'home' : 'neutral'} size="sm"/>
          <div><p className="bc-power-name">{r.team.name}</p><p className="bc-power-meta">{teamRecord(r.team.id).w}-{teamRecord(r.team.id).l} · <Trend delta={r.prev - r.rank}/></p></div>
          <p className="bc-power-blurb">{r.blurb}</p>
          <div className="bc-power-stats"><b>{r.score.toFixed(1)}</b><span>{r.recentPts.toFixed(1)} PTS / WK (L3)</span><span>{Math.round(r.avgRating)} AVG RTG</span></div>
        </div>)}</div>
      </Section>
      <Section title="League activity" kicker={`Weeks ${LEAGUE.currentWeek - 3}–${LEAGUE.currentWeek - 1}`} action={{ href: '/showcase/results', label: 'RESULTS' }}>
        <div className="bc-feed">{feed.map((f, i) => <div className="bc-feed-item" key={i}>
          <Tag tone={KIND[f.kind].tone}>{KIND[f.kind].label}</Tag>
          <div>{f.text}<small>WEEK {f.week} · {team(f.team).name.toUpperCase()}</small></div>
        </div>)}</div>
      </Section>
    </div>

    <div className="bc-grid-3">
      <Section title={`Week ${LEAGUE.currentWeek - 1} stars`} kicker="Top individual performances">
        <div className="bc-leader"><ol>{stars.map((s, i) => <li key={s.p.id}><span>{i + 1}</span><span><strong>{s.p.name}</strong><small>SL {s.p.sl} · {team(s.p.team).short} · beat {s.g!.opp}</small></span><b>{s.g!.points} PTS</b></li>)}</ol></div>
      </Section>
      <Section title="Rating risers" kicker="Last 3 weeks" action={{ href: '/showcase/players', label: 'PLAYERS' }}>
        <div className="bc-leader"><ol>{risers.map((p, i) => <li key={p.id}><span>{i + 1}</span><span><strong>{p.name}</strong><small>SL {p.sl} · {team(p.team).short} · {p.rating} rtg</small></span><b className="bc-trend bc-trend-up">▲ {ratingTrend(p)}</b></li>)}</ol></div>
      </Section>
      <Section title="Your season" kicker={`${mine.team.name} · points by week`}>
        <div className="bc-leader">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
            <div><b style={{ font: '900 30px/1 var(--display)' }}>{mine.w}-{mine.l}</b><small className="bc-muted" style={{ display: 'block' }}>{mine.points} pts · {mine.pointsPerWeek.toFixed(1)} per week · {mine.behind === 0 ? 'division lead' : `${mine.behind} back`}</small></div>
            <Sparkline values={teamPointsByWeek(MY_TEAM)} width={140} height={40}/>
          </div>
          <div className="bc-muted">Individual matches {mine.indivW}-{mine.indivL} ({pct0(mine.winPct)}). Streak {mine.streak}. {myTeamOnBye ? 'On a bye this week.' : `Next: ${featured.fixture.home === MY_TEAM ? away.name : home.name} (${pct0(featured.fixture.home === MY_TEAM ? featured.homeProb : 1 - featured.homeProb)} to win).`}</div>
          <Form seq={mine.last5}/>
        </div>
      </Section>
    </div>
  </>;
}

function seriesText(a: number, b: number): string {
  const ms = allResults.filter(m => (m.home === a && m.away === b) || (m.home === b && m.away === a));
  if (!ms.length) return 'First meeting';
  const m = ms[ms.length - 1];
  const aPts = m.home === a ? m.homePts : m.awayPts, bPts = m.home === a ? m.awayPts : m.homePts;
  return `${aPts > bPts ? team(a).short : team(b).short} won ${Math.max(aPts, bPts)}-${Math.min(aPts, bPts)} wk ${m.week}`;
}
