import Link from 'next/link';
import { Card, Notice, PageTitle } from '@/components/ui';
import { fixture } from '@/lib/demo';

export default function Home() { return <>
  <PageTitle eyebrow="Your match-night overview" title="See the night clearly.">One place for the matchup, the evidence and the tradeoffs. You make the call.</PageTitle>
  <section className="hero"><div><span className="pill light">DEMONSTRATION FIXTURE</span><p className="hero-label">{fixture.format} · {fixture.scope}</p><h2>{fixture.team}<span>vs</span>{fixture.opponent}</h2><p>{fixture.when} <span className="separator">/</span> {fixture.venue}</p><Link className="button" href="/match-night">Open Match Night <span aria-hidden="true">↗</span></Link></div>
    <div className="pool-motif" aria-hidden="true"><div className="ball">8</div><span className="orbit one"/><span className="orbit two"/></div></section>
  <div className="stat-grid"><div><span className="stat-label">OUR ROSTER</span><strong>3 <small>players</small></strong><p>Demo roster · presence unknown</p></div><div><span className="stat-label">DIRECT EVIDENCE</span><strong>20 <small>meetings</small></strong><p>8 of 9 possible pairs recorded</p></div><div><span className="stat-label">DATA STATUS</span><strong className="text-stat">Synthetic</strong><p>Fixture v1 · never refreshed</p></div></div>
  <div className="two-columns"><Card kicker="Start here" title="The matchup, with context"><p>Explore an answer to each opposing put-up. See meeting counts and what you spend by sending someone now.</p><Link className="text-link" href="/recommendations">Explore recommendations <span aria-hidden="true">→</span></Link></Card>
    <Card kicker="Keep in view" title="Thin evidence should look thin"><p>A 1–0 record and an 8–2 record tell different stories. This demo keeps the meeting count beside each record.</p><Link className="text-link" href="/threats">Review cautions <span aria-hidden="true">→</span></Link></Card></div>
  <Notice>This demo demonstrates the dashboard. Its choices are authored examples, not results from the production recommendation engine.</Notice>
</>; }
