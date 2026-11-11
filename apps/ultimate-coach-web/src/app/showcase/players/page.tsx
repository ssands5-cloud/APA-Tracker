import { LEAGUE, MY_TEAM, allPlayers, team, winPct, ppm, ratingTrend } from '@/lib/showcase/league';
import { Form, Section, Sparkline, Trend, Tag, pct0 } from '@/components/showcase/ui';

export const metadata = { title: 'Players' };

export default function Players() {
  const byRating = [...allPlayers].sort((a, b) => b.rating - a.rating);
  const qualified = allPlayers.filter(p => p.played >= 5);
  const leaders = {
    'WIN PERCENTAGE': [...qualified].sort((a, b) => winPct(b) - winPct(a) || b.wins - a.wins).slice(0, 5).map(p => [p, pct0(winPct(p))] as const),
    'POINTS PER MATCH': [...qualified].sort((a, b) => ppm(b) - ppm(a)).slice(0, 5).map(p => [p, ppm(p).toFixed(2)] as const),
    'TOTAL POINTS': [...allPlayers].sort((a, b) => b.points - a.points).slice(0, 5).map(p => [p, String(p.points)] as const),
    'SHUTOUTS (3-0)': [...allPlayers].sort((a, b) => b.shutouts - a.shutouts || b.wins - a.wins).slice(0, 5).map(p => [p, String(p.shutouts)] as const),
    'RATING RISERS · 3 WKS': [...allPlayers].sort((a, b) => ratingTrend(b) - ratingTrend(a)).slice(0, 5).map(p => [p, `+${ratingTrend(p)}`] as const),
    'RATING FALLERS · 3 WKS': [...allPlayers].sort((a, b) => ratingTrend(a) - ratingTrend(b)).slice(0, 5).map(p => [p, String(ratingTrend(p))] as const),
  };
  const moved = allPlayers.filter(p => p.sl !== p.startSl);
  return <>
    <section style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <span className="bc-kicker bc-amber">{allPlayers.length} PLAYERS · {LEAGUE.division.toUpperCase()} · THROUGH WEEK {LEAGUE.currentWeek - 1}</span>
      <h1 className="bc-h1">Players</h1>
      <p style={{ font: '500 16px var(--display)', color: 'var(--text-2)', maxWidth: 820 }}>{byRating[0].name} ({team(byRating[0].team).name}) tops the rating board at {byRating[0].rating} after a {byRating[0].wins}-{byRating[0].losses} start. {moved.length} players have changed skill level this session.</p>
    </section>

    <Section title="Category leaders" kicker="Minimum five matches for rate stats">
      <div className="bc-leaders">{Object.entries(leaders).map(([title, rows]) => <div className="bc-leader" key={title}>
        <span className="bc-kicker">{title}</span>
        <ol>{rows.map(([p, v], i) => <li key={p.id}><span>{i + 1}</span><span><strong>{p.name}</strong><small>SL {p.sl} · {team(p.team).short} · {p.wins}-{p.losses}</small></span><b className={title.includes('FALLERS') ? 'bc-coral' : title.includes('RISERS') ? 'bc-trend bc-trend-up' : ''}>{v}</b></li>)}</ol>
      </div>)}</div>
    </Section>

    <Section title="Rating board" kicker={`All ${allPlayers.length} players · rating replayed from week 1, everyone starts at 1500, K=28`}>
      <div className="bc-table-wrap"><table className="bc-table">
        <thead><tr><th>#</th><th>PLAYER</th><th>TEAM</th><th className="n">SL</th><th className="n">RTG</th><th>3-WK</th><th className="n">W-L</th><th className="n">WIN %</th><th className="n">PTS</th><th className="n">PTS/M</th><th className="n">3-0s</th><th>FORM</th><th>SEASON</th></tr></thead>
        <tbody>{byRating.map((p, i) => <tr key={p.id} className={p.team === MY_TEAM ? 'mine' : ''}>
          <td className="rank">{i + 1}</td>
          <td><span className="team" style={{ fontSize: 13 }}>{p.name}{p.sl !== p.startSl && <Tag tone="green">SL {p.startSl}→{p.sl}</Tag>}</span></td>
          <td className="mono">{team(p.team).short}</td>
          <td className="n"><span className={`bc-sl bc-sl-${p.sl}`}>{p.sl}</span></td>
          <td className="n mono"><b>{p.rating}</b></td><td><Trend delta={ratingTrend(p)}/></td>
          <td className="n mono">{p.wins}-{p.losses}</td><td className="n mono">{pct0(winPct(p))}</td><td className="n mono">{p.points}</td><td className="n mono">{ppm(p).toFixed(2)}</td><td className="n mono">{p.shutouts}</td>
          <td><Form seq={p.form}/></td>
          <td><Sparkline values={p.ratingHistory} width={90} height={24} tone={p.team === MY_TEAM ? 'cyan' : 'amber'}/></td>
        </tr>)}</tbody>
      </table></div>
    </Section>
  </>;
}
