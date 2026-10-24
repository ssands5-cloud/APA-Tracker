import { PageTitle, Card, Notice } from '@/components/ui';
import { fixture } from '@/lib/demo';
import { DecisionBrief } from '@/components/decision-brief';

export default function Summary() { return <>
  <PageTitle eyebrow="The captain’s briefing" title="Summary">What the example shows, what it leaves open and what to check before making a real decision.</PageTitle>
  <DecisionBrief action="Review the opening and prepare a response." why="The example pairs a deeper record against Xeno with a caution about saving Jordan for later." tradeoff="Without confirmed attendance and rules, the example cannot establish a legal or current lineup." href="/match-night" link="Open the example plan"/>
  <Card className="briefing" kicker="Illustrative fixture" title={`${fixture.team} vs ${fixture.opponent}`}><ol className="briefing-list"><li><div><h3>Look at the depth</h3><p>Jordan’s 8–2 against Xeno has 10 meetings. Quinn’s favorable 1–0 has only one.</p></div></li><li><div><h3>Keep the future cost visible</h3><p>Using Jordan against Xeno spends the 1–0 Zane opportunity. That future edge is thin, too.</p></div></li><li><div><h3>Read the caution at pair level</h3><p>Yara beat two players once each. Alex has no meeting with Yara; unknown is not safe.</p></div></li><li><div><h3>Confirm the night in front of you</h3><p>Check attendance, played players, current skill levels and applicable rules. This website has none of those live inputs.</p></div></li></ol></Card>
  <div className="two-columns"><Card title="What this demo shows"><p>These public pages use an invented fixture and illustrative records. They do not display your team’s historical snapshot.</p></Card><Card title="Review historical data"><p>Authorized users can sign in to view the protected historical dashboard. Its snapshot is a saved export, not a live APA feed.</p><a className="text-link" href="/dashboard">Open the historical dashboard →</a></Card></div>
  <Notice>No projected winning lineup or safest board is claimed by this demo. Confirm current attendance and rules before making a decision.</Notice>
</>; }
