import type { ReactNode } from 'react';
import { player, playerWinProb, type Player, type Team } from '@/lib/showcase/league';

export const pct = (p: number) => `${(p * 100).toFixed(1)}%`;
export const pct0 = (p: number) => `${Math.round(p * 100)}%`;
export const signed = (n: number) => (n > 0 ? `+${n}` : `${n}`);
export const two = (n: number) => (n < 10 ? `0${n}` : `${n}`);

export function TeamMark({ team, side, size = 'md' }: { team: Team; side: 'home' | 'away' | 'neutral'; size?: 'sm' | 'md' | 'xl' }) {
  return <span className={`bc-mark bc-mark-${side} bc-mark-${size}`} aria-hidden="true">{team.short}</span>;
}

export function Tag({ tone, children }: { tone: 'cyan' | 'coral' | 'amber' | 'grey' | 'green'; children: ReactNode }) {
  return <span className={`bc-tag bc-tag-${tone}`}>{children}</span>;
}

export function Trend({ delta, suffix = '' }: { delta: number; suffix?: string }) {
  const dir = delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat';
  const arrow = delta > 0 ? '▲' : delta < 0 ? '▼' : '■';
  return <span className={`bc-trend bc-trend-${dir}`}><span aria-hidden="true">{arrow}</span> {delta === 0 ? 'even' : `${Math.abs(delta)}${suffix}`}</span>;
}

export function ProbBar({ home, away, thick = false }: { home: number; away: number; thick?: boolean }) {
  return <span className={`bc-bar${thick ? ' bc-bar-thick' : ''}`} role="img" aria-label={`${pct(home)} to ${pct(away)}`}>
    <span style={{ flex: Math.max(home * 100, 2) }} className="bc-bar-home"/>
    <span style={{ flex: Math.max(away * 100, 2) }} className="bc-bar-away"/>
  </span>;
}

export function Form({ seq, n = 5 }: { seq: ('W' | 'L')[]; n?: number }) {
  const last = seq.slice(-n);
  return <span className="bc-form" aria-label={`Last ${last.length}: ${last.join(' ')}`}>{last.map((r, i) => <i key={i} className={r === 'W' ? 'w' : 'l'}>{r}</i>)}</span>;
}

export function Sparkline({ values, width = 120, height = 32, tone = 'cyan' }: { values: number[]; width?: number; height?: number; tone?: 'cyan' | 'coral' | 'amber' }) {
  if (!values.length) return <svg className={`bc-spark bc-spark-${tone}`} viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-hidden="true"/>;
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const pts = values.map((v, i) => `${(i / Math.max(values.length - 1, 1)) * (width - 4) + 2},${height - 3 - ((v - min) / span) * (height - 6)}`);
  const last = pts[pts.length - 1].split(',');
  return <svg className={`bc-spark bc-spark-${tone}`} viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-hidden="true">
    <polyline fill="none" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" points={pts.join(' ')}/>
    <circle cx={last[0]} cy={last[1]} r="2.6"/>
  </svg>;
}

export function Section({ title, kicker, action, children, className = '' }: { title: string; kicker?: string; action?: { href: string; label: string }; children: ReactNode; className?: string }) {
  return <section className={`bc-section ${className}`}>
    <div className="bc-section-head">
      <div>{kicker && <p className="bc-kicker">{kicker}</p>}<h2 className="bc-h2">{title}</h2></div>
      {action && <a className="bc-link" href={action.href}>{action.label} →</a>}
    </div>
    {children}
  </section>;
}

export function PlayerLine({ p, side, meta }: { p: Player; side: 'home' | 'away'; meta?: string }) {
  return <span className={`bc-player bc-player-${side}`}>
    <span className={`bc-sl bc-sl-${p.sl}`} aria-label={`Skill level ${p.sl}`}>{p.sl}</span>
    <span className="bc-player-text"><strong>{p.name}</strong><small>{meta ?? `${p.wins}-${p.losses} · ${p.rating} rtg`}</small></span>
  </span>;
}

/** One lineup pairing with its model win probability. */
export function Pairing({ no, homeId, awayId, href }: { no: number; homeId: string; awayId: string; href?: string }) {
  const a = player(homeId), b = player(awayId);
  const p = playerWinProb(a, b);
  const edge = Math.abs(p - 0.5);
  const tone = edge < 0.04 ? 'grey' : p > 0.5 ? 'cyan' : 'coral';
  const label = edge < 0.04 ? 'TOSS-UP' : edge < 0.1 ? 'LEAN' : edge < 0.18 ? 'EDGE' : 'STRONG';
  const body = <>
    <span className="bc-no">{two(no)}</span>
    <PlayerLine p={a} side="home"/>
    <span className="bc-pair-mid"><span className="bc-pair-pcts"><span>{pct(p)}</span><span>{pct(1 - p)}</span></span><ProbBar home={p} away={1 - p}/></span>
    <PlayerLine p={b} side="away"/>
    <Tag tone={tone}>{label}</Tag>
  </>;
  return href ? <a className="bc-pair bc-pair-link" href={href}>{body}</a> : <div className="bc-pair">{body}</div>;
}

export function Ticker({ items }: { items: string[] }) {
  const row = items.flatMap((t, i) => [<span key={`t${i}`}>{t}</span>, <span key={`d${i}`} className="bc-diamond" aria-hidden="true">◆</span>]);
  return <div className="bc-ticker" aria-label="League ticker"><div className="bc-ticker-track"><div>{row}</div><div aria-hidden="true">{row}</div></div></div>;
}

/** "1st", "2nd" ... with a leading T when APA lists the team as tied at that rank. */
export function rankText(rank: number, tied: boolean): string {
  const suffix = rank % 100 >= 11 && rank % 100 <= 13 ? 'th' : (['th', 'st', 'nd', 'rd'][rank % 10] ?? 'th');
  return `${tied ? 'T' : ''}${rank}${suffix}`;
}
export function rankCell(rank: number, tied: boolean): string { return `${tied ? 'T' : ''}${rank}`; }
