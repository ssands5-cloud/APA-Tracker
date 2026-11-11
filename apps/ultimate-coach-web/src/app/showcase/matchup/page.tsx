import { LEAGUE, MY_TEAM, featured, upcoming, team, teamRecord, player, playerWinProb, headToHead, winPct, ppm, ratingTrend, allResults } from '@/lib/showcase/league';
import { TeamMark, Tag, Trend, ProbBar, Form, Section, Pairing, Sparkline, pct, pct0, rankText } from '@/components/showcase/ui';

export const metadata = { title: 'Matchup' };

export default async function Matchup({ searchParams }: { searchParams: Promise<{ pick?: string; game?: string }> }) {
  const sp = await searchParams;
  const preview = upcoming.find(u => String(u.fixture.home) === sp.game) ?? featured;
  const home = team(preview.fixture.home), away = team(preview.fixture.away);
  const hr = teamRecord(home.id), ar = teamRecord(away.id);
  const n = preview.homeLineup.length;
  const pickIndex = Math.min(Math.max(Number(sp.pick ?? 0) || 0, 0), Math.max(n - 1, 0));
  const a = player(preview.homeLineup[pickIndex]), b = player(preview.awayLineup[pickIndex]);
  const p = playerWinProb(a, b);
  const h2h = headToHead(a, b);
  const edge = Math.abs(p - 0.5);
  const lean = p > 0.5 ? 'cyan' as const : 'coral' as const;
  const tag = edge < 0.04 ? { tone: 'grey' as const, label: 'TOSS-UP' } : edge < 0.1 ? { tone: lean, label: 'LEAN' } : edge < 0.18 ? { tone: lean, label: 'EDGE' } : { tone: lean, label: 'STRONG' };
  const lastMeeting = allResults.filter(m => (m.home === home.id && m.away === away.id) || (m.home === away.id && m.away === home.id)).at(-1);
  const roster = (t: number) => team(t).roster.map(player);
  const avgRating = (t: number) => Math.round(roster(t).reduce((s, x) => s + x.rating, 0) / Math.max(roster(t).length, 1));
  const avgSl = (t: number) => (roster(t).reduce((s, x) => s + x.sl, 0) / Math.max(roster(t).length, 1)).toFixed(1);
  const shutouts = (t: number) => roster(t).reduce((s, x) => s + x.shutouts, 0);
  const query = sp.game ? `&game=${sp.game}` : '';
  // The "put up" buttons list the other team's players from our team's point of view.
  const mineIsAway = away.id === MY_TEAM;
  const theirLineup = mineIsAway ? preview.homeLineup : preview.awayLineup;
  const theirName = mineIsAway ? home.name : away.name;
  const hVenue = home.venue ? ` · ${home.venue.toUpperCase()}` : '';
  const real = LEAGUE.mode === 'local-real';
  return <>
    <section style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 20, flexWrap: 'wrap' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <span className="bc-kicker bc-amber">WEEK {LEAGUE.currentWeek} · {LEAGUE.format} · CAP {LEAGUE.cap}{hVenue}</span>
        <h1 className="bc-h1">Matchup</h1>
      </div>
      <span style={{ font: '500 16px var(--display)', color: 'var(--text-2)' }}>{away.name} ({ar.w}-{ar.l}) at {home.name} ({hr.w}-{hr.l}) · {LEAGUE.matchDate} · {LEAGUE.matchTime}</span>
    </section>

    <section className="bc-board" aria-label="Team win probability">
      <div className="bc-board-grid" style={{ padding: '26px 48px' }}>
        <div className="bc-board-side home"><span className="bc-kicker home">HOME{home.id === MY_TEAM ? ' · YOUR TEAM' : ''}</span><span className="bc-board-name">{home.name}</span><span className="bc-board-record">{hr.w}-{hr.l} · {hr.points} PTS · {hr.streak} · {rankText(hr.rank, hr.tied).toUpperCase()}</span></div>
        <div className="bc-board-center"><span className="bc-vs">VS</span></div>
        <div className="bc-board-side away"><span className="bc-kicker away">AWAY{away.id === MY_TEAM ? ' · YOUR TEAM' : ''}</span><span className="bc-board-name">{away.name}</span><span className="bc-board-record">{ar.w}-{ar.l} · {ar.points} PTS · {ar.streak} · {rankText(ar.rank, ar.tied).toUpperCase()}</span></div>
      </div>
      <div className="bc-board-prob">
        <div className="bc-board-prob-row"><span><small>WIN PROBABILITY</small>{pct(preview.homeProb)}</span><span><small>PROJECTED SCORE {preview.projHome.toFixed(1)} – {preview.projAway.toFixed(1)}</small>{pct(1 - preview.homeProb)}</span></div>
        <ProbBar home={preview.homeProb} away={1 - preview.homeProb} thick/>
      </div>
      <div className="bc-facts">
        <div><span>LAST MEETING</span><span>{lastMeeting ? `${lastMeeting.home === home.id ? lastMeeting.homePts : lastMeeting.awayPts}-${lastMeeting.home === home.id ? lastMeeting.awayPts : lastMeeting.homePts} WK ${lastMeeting.week}` : 'First meeting'}</span></div>
        <div><span>AVG RATING</span><span>{avgRating(home.id)} · {avgRating(away.id)}</span></div>
        <div><span>AVG SKILL LEVEL</span><span>{avgSl(home.id)} · {avgSl(away.id)}</span></div>
        <div><span>SHUTOUTS</span><span>{shutouts(home.id)} · {shutouts(away.id)}</span></div>
      </div>
    </section>

    <Section title="If they put up" kicker={`Pick ${theirName}'s player to see the projected pairing`}>
      <div className="bc-putups">{theirLineup.map((id, i) => { const o = player(id); return <a key={id} href={`/showcase/matchup?pick=${i}${query}`} aria-current={i === pickIndex ? 'true' : undefined}><strong>{o.name}</strong><span>SL {o.sl} · {o.wins}-{o.losses}</span></a>; })}</div>
    </Section>

    <section className="bc-h2h" aria-label="Head to head">
      <div className="bc-h2h-head"><span className="bc-kicker">HEAD TO HEAD · MATCH {pickIndex + 1} OF {n}</span><Tag tone={tag.tone}>{tag.label}</Tag></div>
      <div className="bc-h2h-grid">
        <div className="bc-h2h-side home"><span className="bc-kicker bc-cyan">{home.short} SENDS · SL {a.sl}</span><span className="bc-h2h-name">{a.name}</span><span className="bc-h2h-pct">{pct(p)}</span><span className="bc-h2h-rec">{a.wins}-{a.losses} season · {a.rating} rtg (<Trend delta={ratingTrend(a)}/>) · {ppm(a).toFixed(2)} pts/match</span><Form seq={a.form} n={8}/></div>
        <div className="bc-h2h-side away"><span className="bc-kicker bc-coral">{away.short} SENDS · SL {b.sl}</span><span className="bc-h2h-name">{b.name}</span><span className="bc-h2h-pct">{pct(1 - p)}</span><span className="bc-h2h-rec">{b.wins}-{b.losses} season · {b.rating} rtg (<Trend delta={ratingTrend(b)}/>) · {ppm(b).toFixed(2)} pts/match</span><Form seq={b.form} n={8}/></div>
      </div>
      <div className="bc-h2h-bar"><ProbBar home={p} away={1 - p} thick/></div>
      <div className="bc-h2h-notes">
        <div><strong>The read.</strong> {read(a.name, b.name, p, a.rating - b.rating, winPct(a), winPct(b))}</div>
        <div><strong>Head to head.</strong> {meetingText(a.name, b.name, h2h.aWins, h2h.bWins)}</div>
        <div><strong>Trend.</strong> {a.name} is {ratingTrend(a) >= 0 ? 'up' : 'down'} {Math.abs(ratingTrend(a))} rating points over three weeks; {b.name} is {ratingTrend(b) >= 0 ? 'up' : 'down'} {Math.abs(ratingTrend(b))}. {a.form.slice(-3).length === 3 && a.form.slice(-3).every(r => r === 'W') ? `${a.name} has won three straight.` : b.form.slice(-3).length === 3 && b.form.slice(-3).every(r => r === 'W') ? `${b.name} has won three straight.` : 'Neither player carries a three-match streak into this one.'}</div>
      </div>
    </section>

    <div className="bc-grid-2">
      <Section title="Projected lineups" kicker={`${n} pairings · rating order under the cap`}>
        <div className="bc-pairs">{preview.homeLineup.map((id, i) => <Pairing key={id} no={i + 1} homeId={id} awayId={preview.awayLineup[i]} href={`/showcase/matchup?pick=${i}${query}`}/>)}</div>
        <div className="bc-muted">Skill levels used: {home.short} {preview.homeLineup.reduce((s, id) => s + player(id).sl, 0)} of {LEAGUE.cap} · {away.short} {preview.awayLineup.reduce((s, id) => s + player(id).sl, 0)} of {LEAGUE.cap}.{real && ' Captains choose the real order at the table; this is the model’s best-rated legal five among each team’s recent regulars.'}</div>
      </Section>
      <Section title="Team comparison" kicker="Season to date">
        <div className="bc-compare">
          {[
            ['RECORD', `${hr.w}-${hr.l}`, `${ar.w}-${ar.l}`], ['POINTS', hr.points, ar.points], ['PTS / WEEK', hr.pointsPerWeek.toFixed(1), ar.pointsPerWeek.toFixed(1)],
            ['INDIVIDUAL W-L', `${hr.indivW}-${hr.indivL}`, `${ar.indivW}-${ar.indivL}`], ['INDIVIDUAL WIN %', pct0(hr.winPct), pct0(ar.winPct)],
            ['AVG RATING', avgRating(home.id), avgRating(away.id)], ['AVG SKILL LEVEL', avgSl(home.id), avgSl(away.id)], ['SHUTOUTS', shutouts(home.id), shutouts(away.id)], ['STREAK', hr.streak, ar.streak],
          ].map(([k, h, aw]) => <Fragmentish key={String(k)} k={String(k)} h={String(h)} a={String(aw)}/>)}
        </div>
        <div className="bc-card" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div><span className="bc-kicker bc-cyan">{home.short} POINTS BY WEEK</span><br/><Sparkline values={pointsByWeek(home.id)} width={200} height={44}/></div>
          <div><span className="bc-kicker bc-coral">{away.short} POINTS BY WEEK</span><br/><Sparkline values={pointsByWeek(away.id)} width={200} height={44} tone="coral"/></div>
        </div>
      </Section>
    </div>

    <Section title="Full rosters" kicker="Everyone on the roster · IN marks the projected five">
      <div className="bc-grid-2" style={{ gridTemplateColumns: '1fr 1fr' }}>
        {[home, away].map((t, side) => <div className="bc-table-wrap" key={t.id}><table className="bc-table bc-compact">
          <thead><tr><th>{t.name.toUpperCase()}</th><th className="n">SL</th><th className="n">W-L</th><th className="n">RTG</th><th>FORM</th></tr></thead>
          <tbody>{roster(t.id).sort((x, y) => y.rating - x.rating).map(pl => <tr key={pl.id}><td><span className="team" style={{ fontSize: 13 }}>{pl.name}{(side ? preview.awayLineup : preview.homeLineup).includes(pl.id) && <Tag tone={side ? 'coral' : 'cyan'}>IN</Tag>}</span></td><td className="n mono">{pl.sl}</td><td className="n mono">{pl.wins}-{pl.losses}</td><td className="n mono">{pl.rating} <Trend delta={ratingTrend(pl)}/></td><td><Form seq={pl.form}/></td></tr>)}</tbody>
        </table></div>)}
      </div>
    </Section>
  </>;
}

function Fragmentish({ k, h, a }: { k: string; h: string; a: string }) {
  return <><span className="v home">{h}</span><span className="k">{k}</span><span className="v away">{a}</span></>;
}
function pointsByWeek(t: number): number[] {
  return allResults.filter(m => m.home === t || m.away === t).map(m => (m.home === t ? m.homePts : m.awayPts));
}
function meetingText(a: string, b: string, aw: number, bw: number): string {
  const total = aw + bw;
  if (!total) return 'No recorded meeting this season; the projection rests on each player’s rating and form.';
  const noun = total === 1 ? 'meeting' : 'meetings';
  if (aw === bw) return `${a} and ${b} are even at ${aw}-${bw} in ${total} recorded ${noun} this season.`;
  const [lead, trail] = aw > bw ? [a, b] : [b, a];
  return `${lead} leads ${Math.max(aw, bw)}-${Math.min(aw, bw)} over ${trail} in ${total} recorded ${noun} this season.`;
}
function read(a: string, b: string, p: number, diff: number, apct: number, bpct: number): string {
  const fav = p >= 0.5 ? a : b, dog = p >= 0.5 ? b : a, fp = Math.max(p, 1 - p);
  const size = fp < 0.54 ? 'a coin flip' : fp < 0.6 ? 'a slight edge' : fp < 0.68 ? 'a clear edge' : 'a strong favorite';
  const why = Math.abs(diff) < 25 ? 'the ratings are nearly level' : `${fav} holds a ${Math.abs(diff)}-point rating advantage`;
  return `${fav} is ${size} at ${pct0(fp)}: ${why}, and ${fav} is winning ${pct0(p >= 0.5 ? apct : bpct)} of matches this season against ${pct0(p >= 0.5 ? bpct : apct)} for ${dog}.`;
}
