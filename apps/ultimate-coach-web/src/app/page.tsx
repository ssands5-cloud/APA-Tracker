import { Card, Notice, PageTitle } from '@/components/ui';
import { fixture } from '@/lib/demo';
import { DecisionBrief } from '@/components/decision-brief';

export default function Home() { return <>
  <PageTitle eyebrow="Your match-night overview" title="See the night clearly.">One place for the matchup, the evidence and the tradeoffs. You make the call.</PageTitle>
  <section className="hero"><div><span className="pill light">DEMONSTRATION FIXTURE</span><p className="hero-label">{fixture.format} · {fixture.scope}</p><h2>{fixture.team}<span>vs</span>{fixture.opponent}</h2><p>{fixture.when} <span className="separator">/</span> {fixture.venue}</p><a className="button" href="/match-night">Open Match Night <span aria-hidden="true">↗</span></a></div>
    <div className="pool-motif" aria-hidden="true"><div className="ball">8</div><span className="orbit one"/><span className="orbit two"/></div></section>
  <DecisionBrief action="Explore the response before the put-up." why="In this example, Jordan has a deeper direct record against Xeno than Quinn." tradeoff="Sending Jordan now uses an available option against Zane; that record is based on one meeting." href="/match-night" link="Open the example plan"/>
  <div className="two-columns"><Card kicker="Start here" title="The matchup, with context"><p>Explore an answer to each opposing put-up. See meeting counts and what you spend by sending someone now.</p><a className="text-link" href="/recommendations">Explore recommendations <span aria-hidden="true">→</span></a></Card>
    <Card kicker="Keep in view" title="Thin evidence should look thin"><p>A 1–0 record and an 8–2 record tell different stories. This demo keeps the meeting count beside each record.</p><a className="text-link" href="/threats">Review cautions <span aria-hidden="true">→</span></a></Card></div>
  <Notice>This demo demonstrates the dashboard. Its choices are authored examples, not results from the production recommendation engine.</Notice>
</>; }
