import { PageTitle, Card, Notice } from '@/components/ui';
import { DecisionBrief } from '@/components/decision-brief';

export default function Threats() { return <>
  <PageTitle eyebrow="Cautions in context" title="Threats">A recorded loss is a reason to look closer. It is not a prediction of the next result.</PageTitle>
  <DecisionBrief action="Scout Yara before choosing a response." why="The example records one win each against Quinn and Jordan." tradeoff="Each pairing has only one meeting, and Alex has no direct record; neither establishes what happens next." href="/match-night" link="Compare responses"/>
  <div className="two-columns"><Card kicker="Roster coverage · 2 of 3 players" title="Yara"><span className="pill caution">2 wins against us · 2 meetings</span><p>Beat Quinn once and Jordan once. Neither pair has a repeat meeting.</p><div className="callout"><strong>One meeting per player</strong><p>Two thin pair records do not establish a proven roster-wide threat.</p></div><p className="muted">Alex has no direct record with Yara. Missing evidence is not clearance.</p></Card>
    <Card kicker="Pair-specific caution" title="Alex vs Xeno"><span className="pill caution">Lost once · 1 meeting</span><p>Alex is 0–1 in this pair. Keep the caution proportional to the evidence.</p><div className="callout"><strong>Other players have different records</strong><p>Quinn is 1–0; Jordan is 8–2 against Xeno. This is not a whole-roster conclusion.</p></div></Card></div>
  <Notice>Coverage assumes all three demo players remain in scope. Actual availability, recency and current skill levels have not been verified.</Notice>
</>; }
