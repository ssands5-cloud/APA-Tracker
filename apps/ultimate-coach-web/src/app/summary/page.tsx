import { PageTitle, Card, Notice } from '@/components/ui';
import { fixture } from '@/lib/demo';

export default function Summary() { return <>
  <PageTitle eyebrow="The captain’s briefing" title="Summary">What the example shows, what it leaves open and what to check before making a real decision.</PageTitle>
  <Card className="briefing" kicker="Illustrative fixture" title={`${fixture.team} vs ${fixture.opponent}`}><ol className="briefing-list"><li><div><h3>Look at the depth</h3><p>Jordan’s 8–2 against Xeno has 10 meetings. Quinn’s favorable 1–0 has only one.</p></div></li><li><div><h3>Keep the future cost visible</h3><p>Using Jordan against Xeno spends the 1–0 Zane opportunity. That future edge is thin, too.</p></div></li><li><div><h3>Read the caution at pair level</h3><p>Yara beat two players once each. Alex has no meeting with Yara; unknown is not safe.</p></div></li><li><div><h3>Confirm the night in front of you</h3><p>Check attendance, played players, current skill levels and applicable rules. This website has none of those live inputs.</p></div></li></ol></Card>
  <div className="two-columns"><Card title="What is connected"><p>Only the bundled synthetic demonstration fixture. All six sections use the same records.</p></Card><Card title="What comes later"><p>Authentication, assigned-team access and an authorized admin panel are Phase 2. APA refresh and database integration are not connected.</p></Card></div>
  <Notice>No projected winning lineup or safest board is claimed by this demo. It is a read-only dashboard foundation.</Notice>
</>; }
