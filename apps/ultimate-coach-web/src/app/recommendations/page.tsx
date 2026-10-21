import { PageTitle, Card, Notice } from '@/components/ui';
import { OpponentView } from '@/components/opponent-view';

export default function Recommendations() { return <>
  <PageTitle eyebrow="Reasons before certainty" title="Recommendations">Understand why a choice is shown, how much evidence supports it and what remains unknown.</PageTitle>
  <div className="two-columns"><OpponentView/><div><Card kicker="The 1–0 vs 8–2 example" title="A thin edge is still thin"><div className="comparison"><div><strong>Quinn</strong><span>1–0</span><small>1 meeting · small sample</small></div><div><strong>Jordan</strong><span>8–2</span><small>10 meetings · deeper record</small></div></div><p>The example answer is Jordan against Xeno. A favorable single result is visible without being presented as stronger support.</p></Card><Card title="Not considered in this demo"><ul className="clean-list"><li>Overall or shared-opponent records</li><li>Recency and skill-level changes</li><li>Current availability and played marks</li><li>Handicap budgets or tournament rules</li></ul></Card></div></div>
  <Notice>These are static, illustrative choices. Production ranking and engine integration have not been added to this website.</Notice>
</>; }
